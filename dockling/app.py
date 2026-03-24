import json
import os
import logging
import boto3
from datetime import datetime, timezone
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

s3 = boto3.client("s3")

PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "512"))

converter = DocumentConverter()
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


def run():
    bucket = os.environ["BUCKET"]
    key = os.environ["KEY"]
    document_id = os.environ["DOCUMENT_ID"]

    file_name = key.split("/")[-1]
    file_path = f"/tmp/{document_id}_{file_name}"

    try:
        log.info("Downloading s3://%s/%s", bucket, key)
        s3.download_file(bucket, key, file_path)
        result = converter.convert(file_path)
    except Exception as e:
        raise RuntimeError(f"Conversion failed for {document_id}: {e}") from e
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    chunks = []
    for i, chunk in enumerate(chunker.chunk(result.document)):
        text = (chunk.text or "").strip()
        if not text:
            continue

        pages = extract_pages(chunk)
        chunks.append({
            "chunk_id": f"{document_id}#{i}",
            "document_id": document_id,
            "text": text,
            "chunk_type": infer_chunk_type(chunk),
            "heading_path": chunk.meta.headings or [],
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

    log.info("Done. documentId=%s chunkCount=%d", document_id, len(chunks))


if __name__ == "__main__":
    run()
