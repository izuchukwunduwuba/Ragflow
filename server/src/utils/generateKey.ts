import { randomUUID } from "node:crypto";

const CONTENT_TYPE_EXTENSIONS: Record<string, string> = {
  "application/pdf": "pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
    "docx",
  "text/plain": "txt",
  "text/csv": "csv",
  "application/json": "json",
  "text/markdown": "md",
  "text/x-markdown": "md",
};

type FileKeyResult = {
  fileKey: string;
  documentId: string;
};

export function generateFileKey(contentType: string): FileKeyResult {
  const documentId = randomUUID(); // change to any ID generator in production
  const ext = CONTENT_TYPE_EXTENSIONS[contentType.toLowerCase()] ?? "bin";

  return {
    fileKey: `upload/raw/${documentId}/${documentId}.${ext}`,
    documentId,
  };
}
