# Konduit

A production-grade document ingestion pipeline for insurance and financial services that extracts structured data and prepares documents for retrieval-augmented generation.

Konduit does two things most RAG systems skip:

1. Extracts a **canonical data model** from each document — a validated, confidence-scored set of structured fields specific to insurance and financial documents.
2. Chunks documents **hierarchically** — preserving section relationships so that retrieval is accurate and context-complete, not just text-matched.

---

## Table of Contents

- [Running locally](#running-locally)
- [Why Konduit exists](#why-konduit-exists)
- [The canonical data model](#the-canonical-data-model)
- [Architecture](#architecture)
- [Services](#services)
- [Processing flow](#processing-flow)
- [Hierarchical chunking](#hierarchical-chunking)
- [Chunk schema](#chunk-schema)
- [Vector storage and sibling retrieval](#vector-storage-and-sibling-retrieval)
- [Technologies](#technologies)
- [Environment variables](#environment-variables)
- [Project structure](#project-structure)

---

## Running locally

The local test setup requires no AWS account, no database, and no deployed infrastructure. Everything runs on your machine.

You need:
- **Python 3.11+** — [download here](https://www.python.org/downloads/)
- **Node.js 20+** — [download here](https://nodejs.org/)
- An **OpenAI API key** — [get one here](https://platform.openai.com/api-keys)

---

### Step 1 — Add your OpenAI API key

Open the file `tests/.env` and add your key:

```
OPENAI_API_KEY=sk-...your-key-here...
```

---

### Step 2 — Set up the test server

Open a terminal and run the following commands one at a time:

```bash
cd /path/to/Rag-Project

# Create a Python virtual environment
python3 -m venv tests/.venv

# Activate it
source tests/.venv/bin/activate

# Install dependencies
pip install flask flask-cors python-dotenv openai docling
```

> **Note:** The `docling` package downloads machine learning models on first install. This can take a few minutes depending on your internet connection.

Then start the server:

```bash
python tests/server.py
```

You should see:

```
Running on http://0.0.0.0:8000
```

Leave this terminal running.

---

### Step 3 — Start the frontend

Open a **second terminal** and run:

```bash
cd /path/to/Rag-Project/client

npm install

npm run dev
```

You should see:

```
Local: http://localhost:5173/
```

---

### Step 4 — Open the app

Go to [http://localhost:5173](http://localhost:5173) in your browser.

Upload a PDF, DOCX, or other supported document. The app will:

1. Send the file to the local test server
2. Parse and convert it using Docling
3. Extract the canonical fields using GPT-4o-mini
4. Chunk the document hierarchically
5. Return everything to the frontend for display

Processing typically takes 10–30 seconds depending on document size.

---

### Supported file types

PDF, DOCX, TXT, CSV, JSON, Markdown

---

### Stopping the servers

Press `Ctrl+C` in each terminal to stop the test server and the frontend.

---

## Why Konduit exists

Most RAG pipelines fail at ingestion.

They extract flat text, split it by token count, embed the chunks, and call it done. That approach works for simple documents. It falls apart on insurance policies, loan agreements, and regulatory filings — where structure carries meaning.

A clause that sits under a sub-condition of an exception is not the same as a standalone clause. A coverage limit that applies only to a specific endorsement is not the same as the primary limit. If your chunker doesn't understand that, your retrieval system doesn't either.

Konduit solves this in two ways:

**First**, it extracts a canonical data model from each document using Claude. Instead of hoping retrieval finds the right answer, Konduit pulls known fields — insured name, coverage limit, inception date, exclusions — and validates them. You get structured data immediately, with confidence scores per field.

**Second**, it preserves document hierarchy during chunking. Headings, subheadings, and their relationships survive the processing step. When a chunk is retrieved, its sibling chunks — the adjacent sections under the same heading — can be pulled in alongside it. The model gets context, not fragments.

---

## The canonical data model

The canonical data model is Konduit's core output for each processed document.

It is a fixed schema of fields that matter in insurance and financial documents. Every document that enters the pipeline produces a canonical record. Each field has a value, a confidence level, and the source page it was drawn from.

### Fields

**Party information**

| Field | Description |
| ----- | ----------- |
| `insured_name` | Full legal name of the insured entity |
| `insured_address` | Registered or principal address |
| `broker_name` | Name of the placing broker |
| `mga_name` | Managing general agent, if applicable |

**Risk attributes**

| Field | Description |
| ----- | ----------- |
| `line_of_business` | Policy class — property, liability, cargo, marine, professional indemnity, etc. |
| `risk_description` | Summary of the risk being underwritten |
| `region` | Geographic region of the risk |
| `country` | Country of the insured |

**Financial terms**

| Field | Description |
| ----- | ----------- |
| `annual_revenue` | Annual revenue of the insured entity |
| `coverage_limit` | Maximum indemnity amount |
| `deductible` | Deductible or excess amount |
| `premium` | Policy premium |

**Coverage period**

| Field | Description |
| ----- | ----------- |
| `inception_date` | Policy start date (ISO 8601) |
| `expiry_date` | Policy end date (ISO 8601) |

**Claims history**

| Field | Description |
| ----- | ----------- |
| `prior_claims_count` | Number of prior claims |
| `prior_claims_amount` | Total value of prior claims |

**Coverage terms**

| Field | Description |
| ----- | ----------- |
| `exclusions` | List of named exclusions from the policy |

### Confidence scores

Every extracted field carries a confidence level: `high`, `medium`, or `low`. These are produced by the extraction model and stored alongside the value.

This matters in underwriting. A `coverage_limit` with `low` confidence should be reviewed. A `high` confidence `insured_name` can be trusted downstream.

### Validation flags

The rule engine runs after extraction. It checks which required fields are missing or empty and assigns severity levels:

- **Critical** — field is required for underwriting and is absent: `insured_name`, `insured_address`, `line_of_business`, `region`, `country`, `annual_revenue`, `coverage_limit`, `inception_date`, `expiry_date`
- **Warning** — field is optional but commonly expected: `broker_name`, `mga_name`, `risk_description`, `deductible`, `premium`, `prior_claims_count`, `prior_claims_amount`, `exclusions`

Flags are stored with the canonical record and surfaced in the client.

### Extraction model

Canonical extraction uses **AWS Bedrock Claude 3.5 Sonnet**. The worker converts the document to Markdown using Docling, takes the first 12,000 characters, and sends it to Claude with a structured extraction prompt. Claude returns a JSON object matching the canonical schema. The result is stored in Supabase.

---

## Architecture

```
┌─────────────────────┐
│        Client       │  React + Vite frontend
│  DocumentUpload     │
│  CanonicalDataCard  │
└──────────┬──────────┘
           │ POST /api/docs/presign-upload
           ▼
┌─────────────────────┐
│    Express Server   │  Node.js / TypeScript
│  Presign + register │
└──────────┬──────────┘
           │ Write metadata to DynamoDB (PENDING)
           │ Client uploads directly to S3
           ▼
┌─────────────────────┐
│   S3 Raw Bucket     │  upload/raw/{documentId}/{file}
└──────────┬──────────┘
           │ SQS message: { bucket, key, documentId }
           ▼
┌─────────────────────┐
│  Lambda Kickstarter │  Reads SQS, starts ECS task
└──────────┬──────────┘
           │ RunTask with injected env vars
           ▼
┌─────────────────────┐
│   Docling Worker    │  ECS Fargate container
│   (Python)          │
│  ┌───────────────┐  │
│  │ canonical.py  │  │  Claude extracts canonical fields
│  │ rule_engine   │  │  Validates required fields
│  │ chunker.py    │  │  Hierarchical chunking via Docling
│  └───────────────┘  │
└──────────┬──────────┘
           ├─── Canonical record → Supabase document_submissions
           └─── chunks.json → S3 processed/chunks/{documentId}/
                     │
                     │ S3 event → SQS
                     ▼
          ┌─────────────────────┐
          │  Embedding Worker   │  Lambda (Node.js)
          │  Bedrock Titan v2   │  1024-dim cosine embeddings
          └──────────┬──────────┘
                     │ Bulk upsert
                     ▼
          ┌─────────────────────┐
          │      Supabase       │  PostgreSQL + pgvector
          │  document_chunks    │  Vectors + hierarchy metadata
          │  document_submissions│  Canonical records
          └─────────────────────┘
```

---

## Services

### `server/` — REST API

Built with Node.js, Express 5, and TypeScript.

| Endpoint | Responsibility |
| -------- | -------------- |
| `POST /api/docs/presign-upload` | Generate pre-signed S3 URL, register document in DynamoDB with status `PENDING` |
| `GET /api/docs/:documentId/canonical` | Retrieve canonical record from Supabase once extraction is complete |
| `GET /health` | Health check |

Accepted file types: PDF, DOCX, TXT, CSV, JSON, Markdown.

---

### `workers/lambda-kickstarter/` — ECS Trigger

AWS Lambda function that consumes SQS messages and starts ECS Fargate tasks.

Reads `{ bucket, key, documentId }` from the queue and calls `RunTask` with those values as environment variables injected into the container. Does not do any document processing itself.

---

### `workers/docling-worker/` — Document Processor

Containerised Python worker that runs as a Fargate task per document.

| File | Responsibility |
| ---- | -------------- |
| `app.py` | Orchestrator — downloads from S3, runs extraction, chunking, and upload |
| `canonical.py` | Calls Bedrock Claude, parses response, stores canonical record in Supabase |
| `rule_engine.py` | Validates extracted fields, assigns severity flags |
| `chunker.py` | Runs Docling HybridChunker, builds chunk metadata, writes `chunks.json` to S3 |

---

### `workers/embedding-worker/` — Embedding Lambda

AWS Lambda function triggered by S3 event (via SQS) when `chunks.json` is written.

Reads `chunks.json`, calls Bedrock Titan Embed v2 for each chunk concurrently, and bulk-upserts the results into Supabase `document_chunks`.

---

### `client/` — Frontend

React + Vite + Tailwind CSS.

| Component | Responsibility |
| --------- | -------------- |
| `DocumentUpload.tsx` | Drag-and-drop upload, calls presign endpoint, uploads directly to S3 |
| `CanonicalDataCard.tsx` | Displays canonical fields, confidence badges, validation flags |

---

## Processing flow

**1. Upload**

Client requests a pre-signed URL from the server. Server registers the document in DynamoDB with status `PENDING` and returns `{ uploadUrl, fileKey, documentId }`. Client uploads the file directly to S3.

```
upload/raw/{documentId}/{documentId}.pdf
```

**2. Queue**

A message is pushed to SQS:

```json
{
  "bucket": "konduit-raw",
  "key": "upload/raw/doc_123/doc_123.pdf",
  "documentId": "doc_123"
}
```

**3. Lambda kickstarts ECS**

Lambda reads the message and calls `RunTask` on Fargate, injecting `BUCKET`, `KEY`, and `DOCUMENT_ID` as environment variables.

**4. Docling worker processes the document**

The worker:

- Downloads the PDF from S3
- Converts it with Docling `DocumentConverter`
- Exports to Markdown and sends to Claude for canonical extraction
- Runs the rule engine to validate required fields
- Stores the canonical record in Supabase `document_submissions`
- Chunks the document hierarchically with `HybridChunker`
- Writes `chunks.json` to S3

```
processed/chunks/doc_123/chunks.json
```

**5. Embedding Lambda**

S3 fires an event when `chunks.json` lands. Lambda reads the file, embeds each chunk with Bedrock Titan, and upserts the vectors into Supabase `document_chunks`.

**6. Results available**

The client can now fetch the canonical record via `GET /api/docs/:documentId/canonical` and display it in `CanonicalDataCard`.

---

## Hierarchical chunking

Documents are not chunked by token count. They are chunked by structure.

The Docling `HybridChunker` respects heading hierarchy, reading order, and section boundaries. Each chunk carries:

- `heading_path` — full ancestry from root to this chunk, e.g. `["Claims Procedure", "Eligibility Criteria"]`
- `parent_heading` — immediate parent section, used for sibling retrieval queries
- `sequence` — position in the document for ordered retrieval
- `page_start`, `page_end` — page numbers

This means a chunk from `1.3 Refund Exceptions` knows it belongs to `1. Return Policy`. It is not an orphan fragment.

If a section is too long to fit in a single chunk (max 512 tokens by default), it is split — but each resulting chunk still carries the full `heading_path`, so its context is preserved.

---

## Chunk schema

Each document produces a `chunks.json` with the following structure:

```json
{
  "document_id": "doc_123",
  "source_bucket": "konduit-raw",
  "source_key": "upload/raw/doc_123/doc_123.pdf",
  "processed_at": "2026-03-30T10:00:00+00:00",
  "chunker": { "name": "HybridChunker", "max_tokens": 512 },
  "chunk_count": 3,
  "chunks": [
    {
      "chunk_id": "doc_123#0",
      "document_id": "doc_123",
      "text": "Claims Procedure\nInsured must notify the broker within 30 days...",
      "chunk_type": "section_text",
      "heading_path": ["Claims Procedure"],
      "parent_heading": null,
      "page_start": 4,
      "page_end": 4,
      "estimated_token_count": 287,
      "sequence": 0
    },
    {
      "chunk_id": "doc_123#1",
      "document_id": "doc_123",
      "text": "Claims Procedure\nEligibility Criteria\nOnly claims arising from...",
      "chunk_type": "section_text",
      "heading_path": ["Claims Procedure", "Eligibility Criteria"],
      "parent_heading": "Claims Procedure",
      "page_start": 4,
      "page_end": 5,
      "estimated_token_count": 341,
      "sequence": 1
    }
  ]
}
```

---

## Vector storage and sibling retrieval

Embedded chunks are stored in Supabase with pgvector.

### `document_chunks` table

| Column | Type | Purpose |
| ------ | ---- | ------- |
| `chunk_id` | TEXT | Unique identifier — `{documentId}#{sequence}` |
| `document_id` | TEXT | Groups all chunks for a document |
| `text` | TEXT | Raw chunk text |
| `embedding` | vector(1024) | Bedrock Titan embedding |
| `chunk_type` | TEXT | `section_text` or `unstructured` |
| `heading_path` | TEXT[] | Full heading ancestry |
| `parent_heading` | TEXT | Immediate parent section |
| `sequence` | INTEGER | Position in document |
| `page_start` | INTEGER | Start page |
| `page_end` | INTEGER | End page |

### Indexes

- `ivfflat` cosine index on `embedding` — approximate nearest-neighbour search
- Composite index on `(document_id, parent_heading, sequence)` — sibling retrieval

### Sibling retrieval

When vector search returns a chunk, the retrieval layer can expand context by fetching sibling chunks from the same section:

```sql
SELECT * FROM document_chunks
WHERE document_id = 'doc_123'
AND parent_heading = 'Claims Procedure'
ORDER BY sequence;
```

This gives the language model surrounding context — not just the matched fragment, but the full section it belongs to.

### `document_submissions` table

Stores the canonical record per document.

| Column | Type | Purpose |
| ------ | ---- | ------- |
| `document_id` | TEXT | Primary key |
| `insured_name` | TEXT | Extracted field |
| `coverage_limit` | TEXT | Extracted field |
| `... (15 fields)` | TEXT | All canonical fields |
| `confidence_scores` | JSONB | `{ "field": "high|medium|low" }` |
| `source_pages` | JSONB | `{ "field": page_number }` |
| `flags` | JSONB | Rule engine output with severity levels |
| `extracted_at` | TIMESTAMPTZ | Extraction timestamp |
| `model` | TEXT | Bedrock model ID used |

---

## Technologies

| Layer | Technology |
| ----- | ---------- |
| Frontend | React 19, Vite, TypeScript, Tailwind CSS |
| API server | Node.js, Express 5, TypeScript |
| Document storage | Amazon S3 |
| Document registry | Amazon DynamoDB |
| Message queue | Amazon SQS |
| Pipeline trigger | AWS Lambda (Node.js) |
| Document processing | Amazon ECS / AWS Fargate |
| Containerisation | Docker |
| PDF / DOCX parsing | Docling (DS4SD) |
| Chunking | Docling HybridChunker |
| Canonical extraction | AWS Bedrock Claude 3.5 Sonnet |
| Embedding | AWS Bedrock Titan Embed v2 (1024 dims) |
| Vector store | Supabase (PostgreSQL + pgvector) |
| AWS SDK (Node.js) | AWS SDK v3 |
| AWS SDK (Python) | boto3 |

---

## Environment variables

### `server/`

| Variable | Description |
| -------- | ----------- |
| `PORT` | Server port (default `5005`) |
| `S3_BUCKET_NAME` | S3 bucket for raw uploads |
| `S3_BUCKET_REGION` | AWS region |
| `S3_ACCESS_KEY` | AWS access key |
| `S3_SECRET_KEY` | AWS secret key |
| `DYNAMODB_TABLE_NAME` | DynamoDB table for document metadata |
| `SUPABASE_DB_URL` | Postgres connection string from Supabase |

### `workers/lambda-kickstarter/`

| Variable | Description |
| -------- | ----------- |
| `ECS_CLUSTER` | ECS cluster name or ARN |
| `ECS_TASK_DEFINITION` | Task definition name or ARN |
| `ECS_CONTAINER_NAME` | Container name in the task definition |
| `SUBNETS` | Comma-separated subnet IDs |
| `SECURITY_GROUPS` | Comma-separated security group IDs |
| `AWS_REGION` | AWS region (default `eu-west-2`) |

### `workers/docling-worker/` (ECS container)

| Variable | Description |
| -------- | ----------- |
| `BUCKET` | Source S3 bucket (injected by Lambda) |
| `KEY` | S3 object key of the document (injected by Lambda) |
| `DOCUMENT_ID` | Unique document ID (injected by Lambda) |
| `PROCESSED_BUCKET` | Output bucket (defaults to source bucket) |
| `MAX_TOKENS` | Max tokens per chunk (default `512`) |
| `BEDROCK_MODEL_ID` | Claude model for extraction (default `anthropic.claude-3-5-sonnet-20241022-v2:0`) |
| `AWS_REGION` | AWS region |
| `SUPABASE_DB_URL` | Postgres connection string from Supabase |

### `workers/embedding-worker/`

| Variable | Description |
| -------- | ----------- |
| `SUPABASE_DB_URL` | Postgres connection string from Supabase |
| `BEDROCK_MODEL_ID` | Embedding model (default `amazon.titan-embed-text-v2:0`) |
| `EMBEDDING_DIMENSIONS` | Vector dimensions (default `1024`) |
| `MAX_WORKERS` | Concurrent embedding threads (default `10`) |
| `AWS_REGION` | AWS region (default `eu-west-2`) |

---

## Project structure

```
Rag-Project/
├── client/                        # React frontend
│   └── src/
│       └── components/
│           ├── DocumentUpload.tsx
│           └── CanonicalDataCard.tsx
│
├── server/                        # REST API — Node.js / TypeScript
│   └── src/
│       ├── config/                # S3 and Supabase connection setup
│       ├── controller/            # presign + canonical endpoints
│       ├── routes/
│       ├── services/              # S3, DynamoDB logic
│       └── utils/
│
├── workers/
│   ├── docling-worker/            # ECS Fargate container — Python
│   │   ├── app.py                 # Orchestrator
│   │   ├── canonical.py           # Claude extraction + Supabase write
│   │   ├── rule_engine.py         # Field validation
│   │   ├── chunker.py             # Hierarchical chunking
│   │   └── Dockerfile
│   │
│   ├── embedding-worker/          # Lambda — Bedrock embeddings + Supabase
│   │   ├── handler.js
│   │   └── schema.sql
│   │
│   └── lambda-kickstarter/        # Lambda — SQS consumer, ECS trigger
│       └── handler.js
│
└── README.md
```
