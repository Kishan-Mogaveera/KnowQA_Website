import os
import re
import uuid
from pathlib import Path

from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "knowqa-local-development-key")
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

@app.route("/api/health")
def health():
    return {
        "status": "success",
        "message": "KnowQA backend is running"
    }

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Store uploaded knowledge bases on the server
KNOWLEDGE_BASES = {}

ALLOWED = {".txt", ".pdf", ".docx"}

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "of", "to", "in", "on", "at", "for", "from", "by", "with", "and",
    "or", "but", "as", "it", "this", "that", "these", "those", "do",
    "does", "did", "can", "could", "would", "should", "will", "may",
    "might", "what", "which", "who", "whom", "whose", "when", "where",
    "why", "how", "tell", "me", "about", "explain", "give", "please",
    "describe", "define", "list", "find", "show", "there", "their",
    "its", "into", "than", "then", "also", "such", "has", "have", "had"
}


# Extract text from uploaded documents
def extract_text(path):
    ext = path.suffix.lower()

    if ext == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")

    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(
            page.extract_text() or "" for page in reader.pages
        )

    if ext == ".docx":
        from docx import Document

        doc = Document(str(path))
        pieces = [
            p.text for p in doc.paragraphs if p.text.strip()
        ]

        for table in doc.tables:
            for row in table.rows:
                pieces.append(
                    " | ".join(cell.text for cell in row.cells)
                )

        return "\n".join(pieces)

    raise ValueError("Only TXT, PDF and DOCX files are supported.")


# Split document into sentences
def split_sentences(text):
    cleaned = re.sub(r"\s+", " ", text).strip()

    if not cleaned:
        return []

    return [
        x.strip()
        for x in re.split(
            r"(?<=[.!?])\s+|(?<=;)\s+|\n+",
            cleaned
        )
        if x.strip()
    ]


# Remove common words and normalize text
def normalize(text):
    terms = re.findall(r"[a-zA-Z0-9]+", text.lower())

    return [
        t for t in terms
        if t not in STOP_WORDS and len(t) > 1
    ]


# Create knowledge base and inverted index
def build_kb(text, filename):
    facts = []
    index = {}

    for fid, sentence in enumerate(
        split_sentences(text), start=1
    ):
        keywords = sorted(set(normalize(sentence)))

        if not keywords:
            continue

        facts.append({
            "id": fid,
            "sentence": sentence,
            "source": filename,
            "keywords": keywords
        })

        for word in keywords:
            index.setdefault(word, []).append(fid)

    return {
        "source": filename,
        "fact_count": len(facts),
        "facts": facts,
        "inverted_index": index
    }


# Identify the question type
def classify_question(question):
    words = re.findall(r"[a-zA-Z]+", question.lower())

    if not words:
        return "general"

    first = words[0]

    if first in {
        "is", "are", "was", "were", "do", "does",
        "did", "can", "could", "has", "have", "had"
    }:
        return "yes/no"

    return {
        "who": "who",
        "when": "when",
        "where": "where",
        "why": "why",
        "how": "how"
    }.get(first, "general")


# Retrieve relevant facts using keyword matching
def retrieve(question, kb, threshold=0.10):
    query = sorted(set(normalize(question)))

    if not query:
        return [], query

    by_id = {
        f["id"]: f for f in kb["facts"]
    }

    candidates = set()

    for term in query:
        candidates.update(
            kb["inverted_index"].get(term, [])
        )

    ranked = []

    for fid in candidates:
        fact = by_id[fid]
        fact_terms = set(fact["keywords"])
        matched = set(query) & fact_terms

        coverage = len(matched) / len(query)

        precision = (
            len(matched) / len(fact_terms)
            if fact_terms else 0
        )

        score = 0.75 * coverage + 0.25 * precision

        if score >= threshold:
            ranked.append({
                "fact": fact,
                "score": round(score, 4),
                "matched": sorted(matched)
            })

    ranked.sort(
        key=lambda x: (-x["score"], x["fact"]["id"])
    )

    return ranked, query


# Generate answer from retrieved facts
def answer_question(question, kb):
    kind = classify_question(question)
    ranked, query = retrieve(question, kb)

    if not ranked:
        return {
            "question": question,
            "type": kind,
            "answer": (
                "The answer is not available in the uploaded document."
            ),
            "evidence": [],
            "query_terms": query
        }

    selected = [ranked[0]]

    if kind == "general":
        for item in ranked[1:3]:
            if item["score"] >= ranked[0]["score"] * 0.70:
                selected.append(item)

    evidence = []

    for x in selected:
        evidence.append({
            "fact_id": x["fact"]["id"],
            "sentence": x["fact"]["sentence"],
            "score": x["score"],
            "matched_terms": x["matched"]
        })

    answer = " ".join(
        x["fact"]["sentence"] for x in selected
    )

    if kind == "yes/no":
        answer = (
            "The document contains the following relevant information: "
            + answer
        )

    return {
        "question": question,
        "type": kind,
        "answer": answer,
        "evidence": evidence,
        "query_terms": query
    }


# Evaluate the question-answering system
def evaluate(kb, tests):
    rows = []
    retrieval_hits = 0
    keyword_hits = 0

    for test in tests:
        result = answer_question(test["question"], kb)

        expected = [
            str(x).lower()
            for x in test.get("expected_keywords", [])
        ]

        answer_terms = set(normalize(result["answer"]))
        has_evidence = bool(result["evidence"])

        hits = sum(
            1 for term in expected
            if term in answer_terms
        )

        passed = (
            hits / len(expected) >= 0.5
            if expected else has_evidence
        )

        retrieval_hits += int(has_evidence)
        keyword_hits += int(passed)

        rows.append({
            "question": test["question"],
            "answer": result["answer"],
            "retrieval_success": has_evidence,
            "expected_keywords": expected,
            "matched_keywords": hits,
            "keyword_pass": passed,
            "evidence": result["evidence"]
        })

    total = len(tests)

    return {
        "total": total,
        "retrieval_rate": (
            round(100 * retrieval_hits / total, 2)
            if total else 0
        ),
        "keyword_accuracy": (
            round(100 * keyword_hits / total, 2)
            if total else 0
        ),
        "results": rows
    }


# Home page
@app.route("/")
def home():
    return render_template("index.html")


# Upload document API
@app.route("/api/upload", methods=["POST"])
def upload():
    file = request.files.get("document")

    if not file or not file.filename:
        return jsonify(
            error="Please choose a document first."
        ), 400

    filename = secure_filename(file.filename)
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED:
        return jsonify(
            error="Supported formats: TXT, PDF and DOCX."
        ), 400

    stored = UPLOAD_DIR / (uuid.uuid4().hex + ext)
    file.save(stored)

    try:
        text = extract_text(stored)
        kb = build_kb(text, filename)

        if not kb["facts"]:
            raise ValueError(
                "No readable text was found. "
                "Scanned/image-only PDFs are not supported."
            )

        kb_id = uuid.uuid4().hex

        KNOWLEDGE_BASES[kb_id] = kb

        session["kb_id"] = kb_id
        session["filename"] = filename

        return jsonify(
            filename=filename,
            fact_count=kb["fact_count"],
            keyword_count=len(kb["inverted_index"]),
            preview=text[:1800],
            message="Knowledge base created successfully."
        )

    except Exception as exc:
        stored.unlink(missing_ok=True)
        return jsonify(error=str(exc)), 400


# Ask question API
@app.route("/api/ask", methods=["POST"])
def ask():
    kb = KNOWLEDGE_BASES.get(session.get("kb_id"))

    if not kb:
        return jsonify(
            error="Upload a document and build its knowledge base first."
        ), 400

    question = request.json.get("question", "").strip()

    if not question:
        return jsonify(error="Enter a question."), 400

    return jsonify(answer_question(question, kb))


# Evaluation API
@app.route("/api/evaluate", methods=["POST"])
def evaluate_api():
    kb = KNOWLEDGE_BASES.get(session.get("kb_id"))

    if not kb:
        return jsonify(
            error="Upload a document first."
        ), 400

    tests = request.json.get("questions", [])

    if not tests:
        return jsonify(
            error="Add at least one question with expected keywords."
        ), 400

    return jsonify(evaluate(kb, tests))


# Display knowledge base
@app.route("/api/knowledge")
def knowledge():
    kb = KNOWLEDGE_BASES.get(session.get("kb_id"))

    if not kb:
        return jsonify(
            error="No knowledge base found."
        ), 400

    return jsonify({
        "source": kb["source"],
        "fact_count": kb["fact_count"],
        "facts": kb["facts"],
        "keyword_count": len(kb["inverted_index"])
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)