# KnowQA - AI Document Question Answering Website

## Project Overview

KnowQA is a document question-answering website.
It accepts TXT, PDF and DOCX documents.

The system extracts sentences, creates a knowledge base,
builds an inverted index and retrieves relevant facts
to answer user questions.

It also includes a manual evaluation section.

## Requirements

- Python 3.9 or later
- Flask
- pypdf
- python-docx

## Installation

Open the VS Code terminal in the project folder.

Run:

pip install -r requirements.txt

## Run the Website

Run:

python app.py

Open this address in your browser:

http://127.0.0.1:5000

## How to Use

1. Upload a TXT, PDF or DOCX document.
2. Click Build Knowledge Base.
3. View the extracted facts.
4. Enter a question in the Ask Questions section.
5. View the answer and source evidence.
6. Use the Evaluation section to test the system.

## Limitations

- Scanned PDFs are not supported.
- The system uses keyword-based retrieval.
- Answers depend on the uploaded document.