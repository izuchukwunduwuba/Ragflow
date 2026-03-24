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
