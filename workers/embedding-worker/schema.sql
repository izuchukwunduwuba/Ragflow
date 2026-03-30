-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Document chunks table
CREATE TABLE IF NOT EXISTS document_chunks (
    id              SERIAL PRIMARY KEY,
    chunk_id        TEXT UNIQUE NOT NULL,
    document_id     TEXT NOT NULL,
    text            TEXT NOT NULL,
    embedding       vector(1024),
    chunk_type      TEXT,
    heading_path    TEXT[],
    parent_heading  TEXT,
    sequence        INTEGER,
    page_start      INTEGER,
    page_end        INTEGER,
    estimated_token_count INTEGER,
    source_bucket   TEXT,
    source_key      TEXT,
    processed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Cosine similarity index for vector search
CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx
    ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Index for filtering by document
CREATE INDEX IF NOT EXISTS document_chunks_document_id_idx
    ON document_chunks (document_id);

-- Index for sibling retrieval — fetch all chunks in the same section
CREATE INDEX IF NOT EXISTS document_chunks_sibling_idx
    ON document_chunks (document_id, parent_heading, sequence);

-- Document submissions table — canonical extracted fields per document
CREATE TABLE IF NOT EXISTS document_submissions (
    document_id         TEXT PRIMARY KEY,
    source_key          TEXT,
    extracted_at        TIMESTAMPTZ,
    model               TEXT,

    -- Party
    insured_name        TEXT,
    insured_address     TEXT,
    broker_name         TEXT,
    mga_name            TEXT,

    -- Risk
    line_of_business    TEXT,
    risk_description    TEXT,
    region              TEXT,
    country             TEXT,

    -- Financial
    annual_revenue      NUMERIC,
    coverage_limit      NUMERIC,
    deductible          NUMERIC,
    premium             NUMERIC,

    -- Coverage period
    inception_date      TEXT,
    expiry_date         TEXT,

    -- Claims
    prior_claims_count  INTEGER,
    prior_claims_amount NUMERIC,

    -- Lists
    exclusions          JSONB,

    -- Extraction metadata
    confidence_scores   JSONB,
    source_pages        JSONB,

    -- Rule engine flags — keyed by field name
    -- e.g. {"annual_revenue": {"severity": "critical", "message": "Annual Revenue is missing"}}
    -- removed per field when broker manually inputs the value
    flags               JSONB DEFAULT '{}',

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Index for filtering by line of business and region (used in allocation engine)
CREATE INDEX IF NOT EXISTS document_submissions_lob_idx
    ON document_submissions (line_of_business, region);
