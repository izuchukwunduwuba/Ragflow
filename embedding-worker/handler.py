import json
import os
import logging
import boto3
import psycopg2
import psycopg2.extras
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SUPABASE_DB_URL = os.environ["SUPABASE_DB_URL"]
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.titan-embed-text-v2:0")
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "10"))
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)


def lambda_handler(event, context):
    for record in event.get("Records", []):
        # SQS wraps the S3 event in the message body
        s3_event = json.loads(record["body"])

        for s3_record in s3_event.get("Records", []):
            bucket = s3_record["s3"]["bucket"]["name"]
            key = s3_record["s3"]["object"]["key"]

            log.info("Processing chunks file: s3://%s/%s", bucket, key)
            process_chunks_file(bucket, key)


def process_chunks_file(bucket: str, key: str):
    # Download and parse chunks.json
    response = s3.get_object(Bucket=bucket, Key=key)
    payload = json.loads(response["body"].read())

    chunks = payload.get("chunks", [])
    if not chunks:
        log.warning("No chunks found in %s", key)
        return

    log.info("Embedding %d chunks for document %s", len(chunks), payload["document_id"])

    # Embed all chunks concurrently
    embedded = embed_chunks(chunks)

    # Bulk insert into Supabase
    insert_chunks(embedded, payload)

    log.info("Indexed %d chunks for document %s", len(embedded), payload["document_id"])


def embed_chunks(chunks: list) -> list:
    results = [None] * len(chunks)

    def embed_one(index, chunk):
        embedding = get_embedding(chunk["text"])
        return index, {**chunk, "embedding": embedding}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(embed_one, i, chunk): i
            for i, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            index, result = future.result()
            results[index] = result

    return results


def get_embedding(text: str) -> list[float]:
    body = json.dumps({
        "inputText": text,
        "dimensions": EMBEDDING_DIMENSIONS,
        "normalize": True,
    })

    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=body,
        contentType="application/json",
        accept="application/json",
    )

    result = json.loads(response["body"].read())
    return result["embedding"]


def insert_chunks(chunks: list, payload: dict):
    rows = [
        (
            chunk["chunk_id"],
            chunk["document_id"],
            chunk["text"],
            chunk["embedding"],
            chunk.get("chunk_type"),
            chunk.get("heading_path", []),
            chunk.get("parent_heading"),
            chunk.get("sequence"),
            chunk.get("page_start"),
            chunk.get("page_end"),
            chunk.get("estimated_token_count"),
            payload.get("source_bucket"),
            payload.get("source_key"),
            payload.get("processed_at"),
        )
        for chunk in chunks
    ]

    sql = """
        INSERT INTO document_chunks (
            chunk_id, document_id, text, embedding,
            chunk_type, heading_path, parent_heading, sequence,
            page_start, page_end, estimated_token_count,
            source_bucket, source_key, processed_at
        )
        VALUES %s
        ON CONFLICT (chunk_id) DO UPDATE SET
            embedding             = EXCLUDED.embedding,
            text                  = EXCLUDED.text,
            chunk_type            = EXCLUDED.chunk_type,
            heading_path          = EXCLUDED.heading_path,
            parent_heading        = EXCLUDED.parent_heading,
            sequence              = EXCLUDED.sequence,
            page_start            = EXCLUDED.page_start,
            page_end              = EXCLUDED.page_end,
            estimated_token_count = EXCLUDED.estimated_token_count,
            processed_at          = EXCLUDED.processed_at
    """

    with psycopg2.connect(SUPABASE_DB_URL) as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, rows)
        conn.commit()
