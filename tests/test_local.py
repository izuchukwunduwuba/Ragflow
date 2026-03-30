"""
Local test script — runs Docling conversion + HybridChunker + OpenAI canonical extraction
on a local file and prints results to stdout. No AWS or Supabase required.

Usage:
    python tests/test_local.py <path-to-file>

Example:
    python tests/test_local.py tests/document.pdf

Requires:
    pip install docling openai
    export OPENAI_API_KEY=sk-...
"""

import sys
import json
import os
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from openai import OpenAI

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MAX_TOKENS = 1024
DOCUMENT_ID = "test-document-001"

CANONICAL_SCHEMA = {
    "name":         {"value": None, "confidence": None, "source_page": None},
    "phone_number": {"value": None, "confidence": None, "source_page": None},
    "email":        {"value": None, "confidence": None, "source_page": None},
    "address":      {"value": None, "confidence": None, "source_page": None},
    "country":      {"value": None, "confidence": None, "source_page": None},
}

EXTRACTION_PROMPT = """You are an expert document analyst.

Extract the following fields from the document below.
For each field return:
- value: the extracted value (null if not found)
- confidence: high | medium | low
- source_page: the page number where the value was found (null if unknown)

Fields to extract:
- name (person or company name)
- phone_number
- email
- address
- country

Respond ONLY with a valid JSON object. No explanation. No markdown. No extra text.

Example response format:
{{
  "name":         {{"value": "Acme Ltd",          "confidence": "high",   "source_page": 1}},
  "phone_number": {{"value": "+44 7700 900000",   "confidence": "high",   "source_page": 1}},
  "email":        {{"value": "info@acme.com",      "confidence": "medium", "source_page": 2}},
  "address":      {{"value": "12 Baker St, London","confidence": "high",   "source_page": 1}},
  "country":      {{"value": "United Kingdom",     "confidence": "high",   "source_page": 1}}
}}

Document:
{document_text}"""


# ── Canonical extraction ──────────────────────────────────────────────────────

def extract_canonical(full_text: str) -> dict:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Strip control characters that break JSON serialization
    import re
    clean_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", full_text[:12000])

    log.info("Extracting canonical fields via OpenAI...")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": EXTRACTION_PROMPT.format(document_text=clean_text),
            }
        ],
        temperature=0,
    )

    raw = response.choices[0].message.content
    extracted = json.loads(raw)

    canonical = json.loads(json.dumps(CANONICAL_SCHEMA))
    for field in canonical:
        if field in extracted:
            canonical[field] = extracted[field]

    return canonical


# ── Chunking helpers ──────────────────────────────────────────────────────────

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


# ── Main runner ───────────────────────────────────────────────────────────────

def run(file_path: str):
    log.info("Converting: %s", file_path)
    converter = DocumentConverter()
    result = converter.convert(file_path)

    full_text = result.document.export_to_markdown()

    print("\n" + "=" * 60)
    print("RAW MARKDOWN OUTPUT")
    print("=" * 60)
    print(full_text[:3000])
    if len(full_text) > 3000:
        print(f"\n... ({len(full_text) - 3000} more characters)")

    # ── Canonical extraction ──────────────────────────────────────────────────
    canonical = extract_canonical(full_text)

    print("\n" + "=" * 60)
    print("CANONICAL DATA")
    print("=" * 60)
    for field, meta in canonical.items():
        print(f"  {field:<15}: {meta['value']}  (confidence: {meta['confidence']}, page: {meta['source_page']})")

    # ── Chunking ──────────────────────────────────────────────────────────────
    log.info("Chunking document...")
    chunker = HybridChunker(max_tokens=MAX_TOKENS)
    chunks = []

    for i, chunk in enumerate(chunker.chunk(result.document)):
        text = (chunk.text or "").strip()
        if not text:
            continue

        pages = extract_pages(chunk)
        heading_path = chunk.meta.headings or []

        chunks.append({
            "chunk_id": f"{DOCUMENT_ID}#{i}",
            "document_id": DOCUMENT_ID,
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

    print("\n" + "=" * 60)
    print(f"CHUNKS PRODUCED: {len(chunks)}")
    print("=" * 60)

    for chunk in chunks:
        print(f"\n[{chunk['chunk_id']}]")
        print(f"  type          : {chunk['chunk_type']}")
        print(f"  heading_path  : {chunk['heading_path']}")
        print(f"  parent_heading: {chunk['parent_heading']}")
        print(f"  sequence      : {chunk['sequence']}")
        print(f"  page_start    : {chunk['page_start']}")
        print(f"  page_end      : {chunk['page_end']}")
        print(f"  tokens (est)  : {chunk['estimated_token_count']}")
        print(f"  text preview  : {chunk['text'][:120].replace(chr(10), ' ')}...")

    # ── Write output ──────────────────────────────────────────────────────────
    output = {
        "document_id": DOCUMENT_ID,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "canonical": canonical,
        "chunker": {"name": "HybridChunker", "max_tokens": MAX_TOKENS},
        "chunk_count": len(chunks),
        "chunks": chunks,
    }



    output_path = "tests/output.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n Full output written to: {output_path}")
    print(f" Total chunks: {len(chunks)}")


if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY environment variable not set")
        print("Run: export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    file_path = sys.argv[1] if len(sys.argv) > 1 else "tests/document2.pdf"
    run(file_path)
