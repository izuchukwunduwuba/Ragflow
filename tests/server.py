"""
Test server — accepts document uploads from the frontend, runs Docling
conversion + OpenAI canonical extraction, and returns results as JSON.

Usage:
    cd /Users/ghodson/Desktop/Rag-Project
    source tests/.venv/bin/activate
    pip install flask flask-cors python-dotenv openai docling
    python tests/server.py
"""

import os
import re
import json
import tempfile
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from openai import OpenAI

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

MAX_TOKENS = 1024

CANONICAL_SCHEMA = {
    "insured_name":        {"value": None, "confidence": None, "source_page": None},
    "insured_address":     {"value": None, "confidence": None, "source_page": None},
    "broker_name":         {"value": None, "confidence": None, "source_page": None},
    "mga_name":            {"value": None, "confidence": None, "source_page": None},
    "line_of_business":    {"value": None, "confidence": None, "source_page": None},
    "risk_description":    {"value": None, "confidence": None, "source_page": None},
    "region":              {"value": None, "confidence": None, "source_page": None},
    "country":             {"value": None, "confidence": None, "source_page": None},
    "annual_revenue":      {"value": None, "confidence": None, "source_page": None},
    "coverage_limit":      {"value": None, "confidence": None, "source_page": None},
    "deductible":          {"value": None, "confidence": None, "source_page": None},
    "premium":             {"value": None, "confidence": None, "source_page": None},
    "inception_date":      {"value": None, "confidence": None, "source_page": None},
    "expiry_date":         {"value": None, "confidence": None, "source_page": None},
    "prior_claims_count":  {"value": None, "confidence": None, "source_page": None},
    "prior_claims_amount": {"value": None, "confidence": None, "source_page": None},
    "exclusions":          {"value": [],   "confidence": None, "source_page": None},
}

EXTRACTION_PROMPT = """You are an expert insurance document analyst.

Extract the following fields from the insurance document below.
For each field return:
- value: the extracted value (null if not found)
- confidence: high | medium | low
- source_page: the page number where the value was found (null if unknown)

Fields to extract:
- insured_name
- insured_address
- broker_name
- mga_name
- line_of_business (e.g. property, liability, cargo, marine, professional indemnity)
- risk_description
- region
- country
- annual_revenue (numeric value only, strip currency symbols)
- coverage_limit (numeric value only)
- deductible (numeric value only)
- premium (numeric value only)
- inception_date (ISO 8601 format)
- expiry_date (ISO 8601 format)
- prior_claims_count (integer)
- prior_claims_amount (numeric value only)
- exclusions (array of strings)

Respond ONLY with a valid JSON object. No explanation. No markdown. No extra text.

Document:
{document_text}"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_pages(chunk) -> list:
    pages = set()
    for item in getattr(chunk.meta, "doc_items", []) or []:
        for prov in getattr(item, "prov", []) or []:
            page_no = getattr(prov, "page_no", None)
            if page_no is not None:
                pages.add(page_no)
    return sorted(pages)


def infer_chunk_type(chunk) -> str:
    headings = getattr(chunk.meta, "headings", None) or []
    return "section_text" if headings else "unstructured"


def extract_canonical(full_text: str) -> dict:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    clean_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", full_text[:12000])

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(document_text=clean_text)}],
        temperature=0,
    )

    extracted = json.loads(response.choices[0].message.content)
    canonical = json.loads(json.dumps(CANONICAL_SCHEMA))
    for field in canonical:
        if field in extracted:
            canonical[field] = extracted[field]

    return canonical


def chunk_document(document, document_id: str) -> list:
    chunker = HybridChunker(max_tokens=MAX_TOKENS)
    chunks = []

    for i, chunk in enumerate(chunker.chunk(document)):
        text = (chunk.text or "").strip()
        if not text:
            continue

        pages = extract_pages(chunk)
        heading_path = chunk.meta.headings or []

        chunks.append({
            "chunk_id": f"{document_id}#{i}",
            "document_id": document_id,
            "text": text,
            "chunk_type": infer_chunk_type(chunk),
            "heading_path": heading_path,
            "parent_heading": (
                heading_path[-2] if len(heading_path) >= 2
                else (heading_path[0] if heading_path else None)
            ),
            "sequence": i,
            "page_start": min(pages) if pages else None,
            "page_end": max(pages) if pages else None,
            "estimated_token_count": len(text),
        })

    return chunks


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    suffix = os.path.splitext(file.filename)[1]

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        log.info("Converting: %s", file.filename)
        converter = DocumentConverter()
        result = converter.convert(tmp_path)
        full_text = result.document.export_to_markdown()

        log.info("Extracting canonical fields...")
        canonical = extract_canonical(full_text)

        log.info("Chunking document...")
        document_id = os.path.splitext(file.filename)[0].replace(" ", "-").lower()
        chunks = chunk_document(result.document, document_id)

        # Build confidence_scores and flags as flat maps for the frontend
        confidence_scores = {field: meta.get("confidence") for field, meta in canonical.items()}
        values = {field: meta.get("value") for field, meta in canonical.items()}

        return jsonify({
            "document_id": document_id,
            "file_name": file.filename,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "canonical": {
                **values,
                "confidence_scores": confidence_scores,
                "source_pages": {field: meta.get("source_page") for field, meta in canonical.items()},
                "flags": {},
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "model": "gpt-4o-mini",
            },
            "chunk_count": len(chunks),
            "chunks": chunks,
        })

    except Exception as e:
        log.error("Processing error: %s", e)
        return jsonify({"error": str(e)}), 500

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
