import os
import logging
import boto3
from docling.document_converter import DocumentConverter

from canonical import extract_canonical_fields, save_canonical_to_supabase
from chunker import chunk_and_upload
from rule_engine import run_rule_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

s3 = boto3.client("s3")
converter = DocumentConverter()


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

    full_text = result.document.export_to_markdown()
    canonical_data = extract_canonical_fields(full_text, document_id)
    flags = run_rule_engine(document_id, canonical_data)
    save_canonical_to_supabase(document_id, key, canonical_data, flags)

    chunks_key = chunk_and_upload(result.document, document_id, bucket, key)
    log.info("Done. documentId=%s chunksKey=%s flags=%d", document_id, chunks_key, len(flags))


if __name__ == "__main__":
    run()
