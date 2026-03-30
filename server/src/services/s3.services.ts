import { PutObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { s3, bucketName } from "../config/s3.config";
import { generateFileKey } from "../utils/generateKey";
import path from "node:path";

type generateUrlParams = {
  contentType: string;
};

type generateUrlResponse = {
  uploadUrl: string;
  fileKey: string;
  documentId: string;
};

const allowedTypes = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
  "text/csv",
  "application/json",
  "text/markdown",
  "text/x-markdown",
];

export const generatePresignedurl = async ({
  contentType,
}: generateUrlParams): Promise<generateUrlResponse> => {
  try {
    const { fileKey, documentId } = generateFileKey(contentType);

    if (!allowedTypes.includes(contentType.toLowerCase())) {
      throw new Error("File type is not accepted");
    }

    const command = new PutObjectCommand({
      Bucket: bucketName,
      Key: fileKey,
      ContentType: contentType,
    });

    const uploadUrl = await getSignedUrl(s3, command, {
      expiresIn: 60 * 60,
    });

    return {
      uploadUrl,
      fileKey,
      documentId,
    };
  } catch (error) {
    console.error("Full error:", JSON.stringify(error, null, 2));
    throw error;
  }
};
