# Document Ingestion Pipeline for Hierarchical RAG

## Overview

This project is a production-style document ingestion pipeline built to process PDF documents for retrieval-augmented generation systems.

The goal is not just to extract text.

The real goal is to preserve document structure so retrieval remains meaningful.

Instead of chopping documents into random text windows, this pipeline uses structure-aware chunking to keep headings, subheadings, and related paragraphs connected. That makes retrieval more accurate and reduces meaning loss.

This is especially useful for:

- policy documents
- handbooks
- contracts
- manuals
- reports
- knowledge base files

---

## Table of Contents

- [Why this system exists](#why-this-system-exists)
- [Core idea](#core-idea)
- [High-level architecture](#high-level-architecture)
- [Services](#services)
- [Design decisions](#design-decisions)
- [Hierarchical chunking](#hierarchical-chunking)
- [Sibling retrieval](#sibling-retrieval)
- [Processing flow](#processing-flow)
- [Chunk output schema](#chunk-output-schema)
- [Technologies](#technologies)
- [Environment variables](#environment-variables)
- [Project structure](#project-structure)
- [Future improvements](#future-improvements)
- [Summary](#summary)

---

## Why this system exists

A lot of RAG systems fail at ingestion.

They extract text.
They split by character count.
They embed chunks.
Then they wonder why answers come back half-baked.

That approach loses structure.

**Example:**

A document section like this:

- Return Policy
  - Eligibility
  - Time Limits
  - Refund Exceptions

can easily get broken into unrelated chunks.

So when retrieval finds one chunk, the answer may miss the next paragraph that actually explains the condition.

This pipeline fixes that.

It preserves hierarchy during chunking and keeps related chunks linked together so that when one chunk is retrieved, its siblings can also be pulled in.

That is the main value.

---

## Core idea

The ingestion system is designed around three principles:

- process documents asynchronously
- preserve structure during chunking
- retrieve related content together later

This means the pipeline is not just about file processing.

It is about preparing documents for better retrieval quality.

---

## High-level architecture

```text
                    ┌─────────────────────┐
                    │     Client/App      │
                    └──────────┬──────────┘
                               │
                               │ Upload PDF
                               ▼
                    ┌─────────────────────┐
                    │     S3 Raw Bucket   │
                    │ uploads/raw/...     │
                    └──────────┬──────────┘
                               │
                               │ Create clean job message
                               ▼
                    ┌─────────────────────┐
                    │    SQS Ingestion    │
                    │       Queue         │
                    └──────────┬──────────┘
                               │
                               │ Kickstart worker flow
                               ▼
                    ┌─────────────────────┐
                    │   Lambda Starter    │
                    │ polls / pulls SQS   │
                    │ starts ECS task     │
                    └──────────┬──────────┘
                               │
                               │ Run worker
                               ▼
                    ┌─────────────────────┐
                    │   ECS Fargate Task  │
                    │   Docling Worker    │
                    └──────────┬──────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
                │ download PDF │ parse layout │ chunk by hierarchy
                ▼              ▼              ▼
         ┌────────────┐  ┌──────────────┐  ┌──────────────────┐
         │   S3 Raw   │  │   Docling    │  │ HybridChunker /  │
         │   PDF      │  │  Converter   │  │ hierarchy logic  │
         └────────────┘  └──────────────┘  └──────────────────┘
                               │
                               │ write structured chunks
                               ▼
                    ┌─────────────────────┐
                    │ S3 Processed Bucket │
                    │ processed/chunks/...│
                    └──────────┬──────────┘
                               │
                               │ next stage
                               ▼
                    ┌─────────────────────┐
                    │ Embedding pipeline  │
                    │ vector DB / search  │
                    └─────────────────────┘
```

---

## Services

### `server/` — REST API

Built with **Node.js**, **Express**, and **TypeScript**.

| Responsibility                 | Detail                                   |
| ------------------------------ | ---------------------------------------- |
| Generate pre-signed upload URL | `POST /api/docs/presign-upload`          |
| Register document metadata     | Writes to DynamoDB with status `PENDING` |
| File key format                | `upload/raw/{documentId}/{fileName}`     |

**Accepted file types:** PDF, DOCX, TXT, CSV, JSON, Markdown

**Stack:** Express 5, AWS SDK v3 (S3, DynamoDB, SQS), `tsx`, TypeScript

---

### `ecs-trigger-lambda/` — ECS Trigger

AWS Lambda function triggered by SQS.

| Responsibility   | Detail                                                         |
| ---------------- | -------------------------------------------------------------- |
| Read SQS message | Extracts `bucket`, `key`, `documentId`                         |
| Start ECS task   | Calls `RunTask` on Fargate with per-document env var overrides |
| Error handling   | Raises on ECS failures — SQS retries / DLQ handles backoff     |

**Runtime:** Python 3.11, `boto3`

---

### `dockling/` — Document Processor (ECS Container)

Containerised Python worker that runs as a Fargate task per document.

| Responsibility               | Detail                                                                   |
| ---------------------------- | ------------------------------------------------------------------------ |
| Download document            | From S3 using env vars injected by Lambda                                |
| Convert to structured format | [Docling](https://github.com/DS4SD/docling) `DocumentConverter`          |
| Chunk document               | `HybridChunker` — respects document structure, max 512 tokens            |
| Enrich chunks                | Page numbers, heading path, chunk type (`section_text` / `unstructured`) |
| Write output                 | `chunks.json` → S3 at `processed/chunks/{documentId}/chunks.json`        |

**Stack:** Python 3.11, Docling, boto3, Docker (ECS Fargate)

---

## Design decisions

### Why Lambda is still in the design

The heavy document parsing does not run in Lambda.

Lambda is used as a kickstarter. Its job is simple:

- pull the clean job from SQS
- start an ECS Fargate task
- let ECS handle the actual document processing

This keeps Lambda small and cheap while avoiding Lambda limits for Docling and heavier PDF parsing.

So the split is:

```
Lambda  = orchestrator
ECS     = worker
Docling = parsing and chunking engine
```

That is a much cleaner design than trying to force the full document pipeline into Lambda.

---

### Why ECS Fargate is used for Docling

Docling is better suited to a containerized worker because document parsing can be heavy.

Using ECS Fargate gives you:

- better control over CPU and memory
- fewer packaging limitations
- cleaner dependency management
- better fit for long-running or heavy jobs
- easier scaling for larger ingestion volume

For a real ingestion pipeline, this is the sane path.

---

### What Docling is doing here

Docling is the core document intelligence layer inside the ECS worker.

It handles:

- PDF parsing
- structure detection
- headings and subheadings
- reading order
- relationship-aware chunking

That matters because the ingestion pipeline is not trying to extract plain text only.

It is trying to preserve the structure of the document so that downstream retrieval is better.

---

### Why not use naive chunking

Naive chunking usually means:

- fixed token windows
- blind overlaps
- no document hierarchy
- no section awareness

That leads to bad retrieval.

This system avoids that by preserving document relationships from the start.

That is the real point of the ingestion pipeline.

---

## Hierarchical chunking

This is the most important part of the pipeline.

Instead of splitting documents into flat chunks, the pipeline preserves structure.

**Example document:**

```
1. Return Policy
   1.1 Eligibility
   1.2 Time Limits
   1.3 Refund Exceptions

2. Shipping Policy
   2.1 Delivery Times
   2.2 Lost Orders
```

A naive chunker may split that by token count alone. That causes problems:

- heading in one chunk
- explanation in another
- exception rule in a third
- retrieval misses context

Hierarchical chunking fixes that by grouping content based on document relationships.

So instead of random chunks, you get structure-aware chunks like:

```
1 → 1.1 → 1.2 → 1.3
2 → 2.1 → 2.2
```

If a subsection is too large, it can still be split, but the relationship is preserved:

```
1.2.a → 1.2.b → 1.2.c
```

This means the chunk still belongs to section 1.2.

That is the difference between basic chunking and ingestion that is actually useful.

### Why hierarchical chunking matters

Hierarchical chunking improves retrieval because it preserves meaning.

Benefits:

- headings stay tied to their content
- subheadings keep their local context
- related paragraphs remain grouped
- large sections can be split without losing identity
- retrieval becomes more precise
- context reconstruction becomes easier

This is a big deal in policy-heavy and rule-heavy documents.

Without it, retrieval often returns fragments.

With it, retrieval returns structured context.

---

## Sibling retrieval

This is one of the most useful retrieval improvements enabled by this pipeline.

When a chunk is retrieved, the system does not have to stop there.

Because the ingestion step preserved relationships, the retrieval layer can also fetch sibling chunks.

**Example:**

If vector search retrieves `1.2.b`, the system can also pull `1.2.a` and `1.2.c`, and even the parent heading for `1.2`.

Why this matters:

- the matched chunk may contain only part of the answer
- the previous or next chunk may contain the condition, exception, or explanation
- pulling siblings keeps the meaning intact

This is where Docling-style structure becomes valuable.

The parser and chunker do not just split text. They preserve enough document relationship for downstream retrieval expansion.

That gives you better answers because the model receives the surrounding context, not just one isolated fragment.

### Example retrieval benefit

Say a user asks:

> What are the exceptions to the return policy?

Vector search may match a chunk from `1.3.b Refund Exceptions`.

If you only return that one chunk, the answer may miss the clause introduced in `1.3.a` or the limitation described in `1.3.c`.

With sibling retrieval, the system can expand the result to include adjacent chunks in the same section.

That gives the language model a more complete view.

- Less guessing.
- Less hallucination.
- Better answers.

---

## Processing flow

**1. File upload**

A PDF is uploaded to the raw S3 bucket.

```
uploads/raw/doc_123/policy.pdf
```

**2. Queue message**

A clean job is pushed to SQS with:

```json
{
  "bucket": "my-raw-bucket",
  "key": "uploads/raw/doc_123/policy.pdf",
  "documentId": "doc_123"
}
```

The worker only needs to know where the file is and what the document id is. No extra event-unwrapping mess.

**3. Lambda kickstarts ECS**

Lambda reads the job and starts an ECS Fargate task.

**4. ECS worker processes the document**

The worker:

- downloads the PDF from S3
- parses it with Docling
- chunks it with hierarchical awareness
- builds chunk metadata
- stores the result in the processed bucket

**5. Processed JSON is stored**

Output is written to the processed bucket:

```
processed/chunks/doc_123/chunks.json
```

**6. Next stage**

The next stage can:

- embed the chunks
- store them in a vector database
- use chunk relationships for sibling retrieval

---

## Chunk output schema

Each document produces a `chunks.json` with the following structure:

```json
{
  "document_id": "doc_123",
  "source_bucket": "my-raw-bucket",
  "source_key": "uploads/raw/doc_123/policy.pdf",
  "processed_at": "2026-03-24T10:00:00+00:00",
  "chunker": { "name": "HybridChunker", "max_tokens": 512 },
  "chunk_count": 3,
  "chunks": [
    {
      "chunk_id": "doc_123#0",
      "document_id": "doc_123",
      "text": "Return Policy\nCustomers may return eligible products within 30 days...",
      "chunk_type": "section_text",
      "heading_path": ["Return Policy"],
      "page_start": 1,
      "page_end": 1,
      "estimated_token_count": 312,
      "sequence": 0
    },
    {
      "chunk_id": "doc_123#1",
      "document_id": "doc_123",
      "text": "Return Policy\nRefund Exceptions\nFinal-sale items are not eligible...",
      "chunk_type": "section_text",
      "heading_path": ["Return Policy", "Refund Exceptions"],
      "page_start": 2,
      "page_end": 2,
      "estimated_token_count": 198,
      "sequence": 1
    }
  ]
}
```

This output preserves:

- document identity
- heading hierarchy
- ordering
- page range
- chunk sequence

That is what later enables sibling-aware retrieval.

---

## Benefits of this ingestion system

| Benefit                     | Why                                                                             |
| --------------------------- | ------------------------------------------------------------------------------- |
| Better retrieval quality    | Documents are chunked with structure in mind, not just token count              |
| Better context preservation | Related sections remain connected through hierarchy and chunk metadata          |
| Better downstream answers   | The LLM gets more complete and relevant context                                 |
| Cleaner scaling model       | S3, SQS, Lambda, and ECS each handle a separate responsibility                  |
| Easier retries              | Failed jobs can be retried through SQS without blocking the whole system        |
| Production-friendly design  | Heavy document parsing is isolated in ECS instead of being squeezed into Lambda |

---

## Technologies

| Layer               | Technology                                  |
| ------------------- | ------------------------------------------- |
| API Server          | Node.js, Express 5, TypeScript              |
| Document Storage    | Amazon S3                                   |
| Document Registry   | Amazon DynamoDB                             |
| Queue               | Amazon SQS                                  |
| Pipeline Trigger    | AWS Lambda (Python 3.11)                    |
| Document Processing | Amazon ECS / AWS Fargate                    |
| Containerisation    | Docker                                      |
| PDF / DOCX Parsing  | [Docling](https://github.com/DS4SD/docling) |
| Chunking            | Docling HybridChunker                       |
| AWS SDK (Node)      | AWS SDK v3                                  |
| AWS SDK (Python)    | boto3                                       |

---

## Environment variables

### `server/`

| Variable              | Description                          |
| --------------------- | ------------------------------------ |
| `PORT`                | Server port (default `5005`)         |
| `S3_BUCKET_NAME`      | S3 bucket for raw uploads            |
| `S3_BUCKET_REGION`    | AWS region                           |
| `DYNAMODB_TABLE_NAME` | DynamoDB table for document metadata |

### `ecs-trigger-lambda/`

| Variable              | Description                           |
| --------------------- | ------------------------------------- |
| `ECS_CLUSTER`         | ECS cluster name or ARN               |
| `ECS_TASK_DEFINITION` | Task definition name/ARN              |
| `ECS_CONTAINER_NAME`  | Container name in the task definition |
| `SUBNETS`             | Comma-separated subnet IDs            |
| `SECURITY_GROUPS`     | Comma-separated security group IDs    |
| `AWS_REGION`          | AWS region (default `eu-west-2`)      |

### `dockling/` (ECS container)

| Variable           | Description                                        |
| ------------------ | -------------------------------------------------- |
| `BUCKET`           | Source S3 bucket (injected by Lambda)              |
| `KEY`              | S3 object key of the document (injected by Lambda) |
| `DOCUMENT_ID`      | Unique document ID (injected by Lambda)            |
| `PROCESSED_BUCKET` | Output bucket (defaults to source bucket)          |
| `MAX_TOKENS`       | Max tokens per chunk (default `512`)               |

---

## Project structure

```
Rag-Project/
├── server/                    # REST API — Node.js / TypeScript
│   ├── src/
│   │   ├── config/
│   │   ├── controller/
│   │   ├── middleware/
│   │   ├── routes/
│   │   ├── services/
│   │   └── utils/
│   ├── index.ts
│   └── package.json
├── ecs-trigger-lambda/        # Lambda — SQS consumer, ECS kickstarter
│   ├── handler.py
│   └── requirements.txt
├── dockling/                  # ECS container — Docling document processor
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
└── README.md
```

---

## Summary

This ingestion pipeline was built to prepare documents for high-quality RAG retrieval.

Its value is not just extracting text.

Its value is preserving structure.

By using Docling inside ECS and keeping chunk relationships intact, the pipeline makes it possible to retrieve not only the matching chunk, but also the related sibling chunks that complete the meaning.

That leads to better retrieval, better context, and better answers.
