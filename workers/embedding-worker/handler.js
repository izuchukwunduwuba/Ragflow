const { S3Client, GetObjectCommand } = require("@aws-sdk/client-s3");
const {
  BedrockRuntimeClient,
  InvokeModelCommand,
} = require("@aws-sdk/client-bedrock-runtime");
const { Pool } = require("pg");

const s3 = new S3Client({ region: process.env.AWS_REGION ?? "eu-west-2" });

const bedrock = new BedrockRuntimeClient({
  region: process.env.AWS_REGION ?? "eu-west-2",
});

let pool = null;
function getPool() {
  if (!pool) pool = new Pool({ connectionString: process.env.SUPABASE_DB_URL });
  return pool;
}

exports.handler = async (event) => {
  for (const sqsRecord of event.Records) {
    const s3Event = JSON.parse(sqsRecord.body);

    for (const s3Record of s3Event.Records ?? []) {
      const bucket = s3Record.s3.bucket.name;
      const key = decodeURIComponent(
        s3Record.s3.object.key.replace(/\+/g, " "),
      );
      console.log(`Processing: s3://${bucket}/${key}`);
      await processChunksFile(bucket, key);
    }
  }
};

async function processChunksFile(bucket, key) {
  const response = await s3.send(
    new GetObjectCommand({ Bucket: bucket, Key: key }),
  );

  const raw = await response.Body?.transformToString();
  if (!raw) throw new Error(`Empty S3 response: s3://${bucket}/${key}`);

  const payload = JSON.parse(raw);
  const { chunks } = payload;

  if (!chunks?.length) {
    console.warn(`No chunks found in ${key}`);
    return;
  }

  console.log(
    `Embedding ${chunks.length} chunks for document ${payload.document_id}`,
  );

  const embedded = await embedConcurrently(chunks);
  await upsertChunks(embedded, payload);

  console.log(
    `Indexed ${embedded.length} chunks for document ${payload.document_id}`,
  );
}

async function embedConcurrently(chunks) {
  const concurrency = parseInt(process.env.CONCURRENCY ?? "10");
  const results = [];

  for (let i = 0; i < chunks.length; i += concurrency) {
    const batch = chunks.slice(i, i + concurrency);
    const batchResults = await Promise.all(
      batch.map(async (chunk) => ({
        ...chunk,
        embedding: await getEmbedding(chunk.text),
      })),
    );
    results.push(...batchResults);
  }

  return results;
}

async function getEmbedding(text) {
  const command = new InvokeModelCommand({
    modelId: process.env.BEDROCK_MODEL_ID ?? "amazon.titan-embed-text-v2:0",
    body: JSON.stringify({
      inputText: text,
      dimensions: parseInt(process.env.EMBEDDING_DIMENSIONS ?? "1024"),
      normalize: true,
    }),
    contentType: "application/json",
    accept: "application/json",
  });

  const response = await bedrock.send(command);
  const result = JSON.parse(new TextDecoder().decode(response.body));
  return result.embedding;
}

async function upsertChunks(chunks, payload) {
  if (!chunks.length) return;

  const db = getPool();

  const COLUMNS = [
    "chunk_id",
    "document_id",
    "text",
    "embedding",
    "chunk_type",
    "heading_path",
    "parent_heading",
    "sequence",
    "page_start",
    "page_end",
    "estimated_token_count",
    "source_bucket",
    "source_key",
    "processed_at",
  ];

  const values = [];

  const placeholders = chunks.map((chunk, i) => {
    const offset = i * COLUMNS.length;
    values.push(
      chunk.chunk_id,
      chunk.document_id,
      chunk.text,
      `[${chunk.embedding.join(",")}]`,
      chunk.chunk_type ?? null,
      chunk.heading_path ?? [],
      chunk.parent_heading ?? null,
      chunk.sequence ?? null,
      chunk.page_start ?? null,
      chunk.page_end ?? null,
      chunk.estimated_token_count ?? null,
      payload.source_bucket,
      payload.source_key,
      payload.processed_at,
    );
    return `(${COLUMNS.map((_, j) => `$${offset + j + 1}`).join(", ")})`;
  });

  const sql = `
    INSERT INTO document_chunks (${COLUMNS.join(", ")})
    VALUES ${placeholders.join(", ")}
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
  `;

  await db.query(sql, values);
}
