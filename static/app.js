const $ = id => document.getElementById(id);

let currentFile = null;
let currentKB = null;


// Display notification message
function toast(msg) {
    const t = $("toast");

    t.textContent = msg;
    t.classList.add("show");

    setTimeout(() => {
        t.classList.remove("show");
    }, 2400);
}


// Navigation buttons
document.querySelectorAll(".nav").forEach(btn => {
    btn.addEventListener("click", () => {

        document.querySelectorAll(".nav").forEach(x => {
            x.classList.remove("active");
        });

        btn.classList.add("active");

        $(btn.dataset.target).scrollIntoView({
            behavior: "smooth"
        });
    });
});


// Select document
$("document").addEventListener("change", e => {

    currentFile = e.target.files[0];

    $("build-btn").disabled = !currentFile;

    if (currentFile) {
        $("file-name").textContent = currentFile.name;

        $("file-size").textContent =
            (currentFile.size / 1024).toFixed(1) + " KB";
    }
});


// Upload document and build knowledge base
$("build-btn").addEventListener("click", async () => {

    if (!currentFile) return;

    const fd = new FormData();
    fd.append("document", currentFile);

    $("build-btn").disabled = true;
    $("build-btn").textContent = "Building knowledge base…";

    $("upload-message").textContent =
        "Extracting document text and indexing facts.";

    try {

        const r = await fetch("/api/upload", {
            method: "POST",
            body: fd
        });

        const responseText = await r.text();
        let d;

        try {
            d = JSON.parse(responseText);
        } catch {
            throw new Error(
                "Server returned HTML instead of JSON. Check Vercel Runtime Logs."
            );
        }

        if (!r.ok) {
            throw new Error(d.error || "Document upload failed.");
        }

        currentKB = d.knowledge_base;

        $("metric-doc").textContent = d.filename;
        $("metric-facts").textContent = d.fact_count;
        $("metric-terms").textContent = d.keyword_count;

        $("fact-count-label").textContent =
            d.fact_count + " FACTS";

        $("upload-message").textContent = d.message;
        $("upload-message").className = "message";

        loadFacts(currentKB);

        toast("Knowledge base created successfully!");

    } catch (err) {

        $("upload-message").textContent = err.message;
        $("upload-message").className = "message error";

    } finally {

        $("build-btn").disabled = false;

        $("build-btn").innerHTML =
            'Build knowledge base <span>→</span>';
    }
});


// Display extracted facts
function loadFacts(kb) {

    if (!kb) return;

    $("facts-list").className = "fact-list";

    $("facts-list").innerHTML = kb.facts.map(f => `
        <div class="fact">
            <span class="fact-id">F${f.id}</span>
            <p>${escapeHtml(f.sentence)}</p>
        </div>
    `).join("");
}



// Prevent HTML injection when displaying text
function escapeHtml(s) {

    return String(s).replace(/[&<>"']/g, c => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    }[c]));
}


// Ask a question
async function ask() {
    const q = $("question-input").value.trim();

    if (!q) {
        return toast("Enter a question first");
    }

    $("ask-btn").disabled = true;

    try {
        const r = await fetch("/api/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                question: q
            })
        });

        const d = await r.json();

        if (!r.ok) {
            throw Error(d.error || "Unable to get an answer");
        }

        $("answer-area").innerHTML = `
            <div class="answer-card">
                <div class="answer-top">
                    <span>ANSWER GENERATED</span>
                    <span>${escapeHtml(d.type.toUpperCase())} QUESTION</span>
                </div>

                <h3>${escapeHtml(d.question)}</h3>
                <p>${escapeHtml(d.answer)}</p>

                ${d.evidence.length ? `
                    <div class="evidence">
                        <div class="evidence-title">SOURCE EVIDENCE</div>

                        ${d.evidence.map(e => `
                            <div class="evidence-item">
                                <b>FACT ${e.fact_id} · SCORE ${e.score}</b>
                                ${escapeHtml(e.sentence)}
                            </div>
                        `).join("")}
                    </div>
                ` : ""}
            </div>
        `;

    } catch (err) {
        toast(err.message);
    } finally {
        $("ask-btn").disabled = false;
    }
}

// Ask button
$("ask-btn").addEventListener("click", ask);


// Press Enter to ask a question
$("question-input").addEventListener("keydown", e => {

    if (e.key === "Enter") {
        ask();
    }
});


// Suggested questions
document.querySelectorAll(".suggestion").forEach(b => {

    b.addEventListener("click", () => {

        $("question-input").value = b.textContent;

        ask();
    });
});


// Evaluate the system

// Evaluate the system
$("eval-btn").addEventListener("click", async () => {

    const tests = $("eval-input").value
        .split("\n")
        .map(x => x.trim())
        .filter(Boolean)
        .map(line => {

            const parts = line.split("|");

            return {
                question: parts[0].trim(),
                expected_keywords: (parts[1] || "")
                    .split(",")
                    .map(x => x.trim())
                    .filter(Boolean)
            };
        });

    if (!tests.length) {
        return toast("Add evaluation questions");
    }

    $("eval-btn").disabled = true;

    try {

        const r = await fetch("/api/evaluate", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                questions: tests
            })
        });

        const d = await r.json();

        if (!r.ok) {
            throw Error(d.error || "Evaluation failed");
        }

        $("eval-results").innerHTML = `
            <div class="eval-summary">
                <div class="eval-stat">
                    <b>${d.retrieval_rate}%</b>
                    <span>RETRIEVAL RATE</span>
                </div>

                <div class="eval-stat">
                    <b>${d.keyword_accuracy}%</b>
                    <span>KEYWORD ACCURACY</span>
                </div>
            </div>
        ` + d.results.map(x => `
            <div class="eval-row">
                <b>${escapeHtml(x.question)}</b>

                <span class="${x.keyword_pass ? 'pass' : 'fail'}">
                    · ${x.keyword_pass ? 'PASS' : 'CHECK'}
                </span>

                <div>
                    ${x.retrieval_success
                        ? 'Evidence found'
                        : 'No evidence found'}
                    · ${x.matched_keywords}/${x.expected_keywords.length}
                    expected keywords matched
                </div>

                <div>${escapeHtml(x.answer)}</div>
            </div>
        `).join("");

    } catch (err) {
        toast(err.message);

    } finally {
        $("eval-btn").disabled = false;
    }
});


/* PAGE LOADING ANIMATION */

window.addEventListener("load", function () {
    const loader = document.getElementById("page-loader");

    if (loader) {
        setTimeout(function () {
            loader.classList.add("loader-hidden");
        }, 500);
    }
});
