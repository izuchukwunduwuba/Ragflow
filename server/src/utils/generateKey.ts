import { randomUUID } from "node:crypto";

type GenerateParamsForFile = {
  originalFileName: string;
};

export function generateFileKey({
  originalFileName,
}: GenerateParamsForFile): string {
  const fileName = originalFileName.replace(/\s+/g, "-");
  const documentId = randomUUID();

  return `upload/raw/${documentId}/${fileName}`;
}
