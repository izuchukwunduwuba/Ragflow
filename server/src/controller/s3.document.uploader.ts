import { Request, Response } from "express";
import { generatePresignedurl } from "../services/s3.services";
import { createDocument } from "../services/dynamodb.service";
import { randomUUID } from "crypto";

type PresignedUrlContent = {
  fileName: string;
  contentType: string;
};

export const uploadDocument = async (
  req: Request<{}, {}, PresignedUrlContent>,
  res: Response,
): Promise<void> => {
  try {
    const { fileName, contentType } = req.body;

    if (!fileName || !contentType) {
      res.status(400).json({
        message: "Filename and ontentType is required",
      });
      return;
    }

    const result = await generatePresignedurl({
      fileName,
      contentType,
    });

    const documentId = result.fileKey.split("/")[2];
    const fileKey = result.fileKey;

    console.log(documentId);

    await createDocument({
      documentId,
      fileName,
      fileKey,
      contentType,
    });

    res.status(200).json({
      message: "Presigned upload URL generated successfully",
      data: result,
    });
  } catch (error) {
    console.error("Presign upload error:", error);
    res.status(500).json({
      message: "Failed to generate presigned upload URL",
    });
  }
};
