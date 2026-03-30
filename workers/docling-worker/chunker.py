import json
import os
import logging
import boto3
from datetime import datetime, timezone
from docling.chunking import HybridChunker

log = logging.getLogger(__name__)

s3 = boto3.client("s3")

MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "512"))
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET")

chunker = HybridChunker(max_tokens=MAX_TOKENS)


def extract_pages(chunk) -> list[int]:
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


def chunk_and_upload(document, document_id: str, bucket: str, key: str):
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
            "parent_heading": heading_path[-2] if len(heading_path) >= 2 else (heading_path[0] if heading_path else None),
            "sequence": i,
            "page_start": min(pages) if pages else None,
            "page_end": max(pages) if pages else None,
            "estimated_token_count": len(text),
        })

    if not chunks:
        raise RuntimeError(f"No chunks produced for document {document_id}")

    output_bucket = PROCESSED_BUCKET or bucket
    chunks_key = f"processed/chunks/{document_id}/chunks.json"
    payload = {
        "document_id": document_id,
        "source_bucket": bucket,
        "source_key": key,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "chunker": {"name": "HybridChunker", "max_tokens": MAX_TOKENS},
        "chunk_count": len(chunks),
        "chunks": chunks,
    }

    log.info("Writing %d chunks to s3://%s/%s", len(chunks), output_bucket, chunks_key)
    s3.put_object(
        Bucket=output_bucket,
        Key=chunks_key,
        Body=json.dumps(payload, default=str).encode("utf-8"),
        ContentType="application/json",
    )

    return chunks_key
