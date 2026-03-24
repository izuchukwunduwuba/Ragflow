import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, PutCommand } from "@aws-sdk/lib-dynamodb";

const client = new DynamoDBClient({
  region: process.env.S3_BUCKET_REGION,
});

export const dynamo = DynamoDBDocumentClient.from(client);

const TABLE_NAME = process.env.DYNAMODB_TABLE_NAME;

type Metadata = {
  documentId: string;
  fileName: string;
  fileKey: string;
  contentType: string;
};

export const createDocument = async ({
  documentId,
  fileName,
  fileKey,
  contentType,
}: Metadata) => {
  await dynamo.send(
    new PutCommand({
      TableName: TABLE_NAME,
      Item: {
        documentId,
        fileName,
        fileKey,
        contentType,
        status: "PENDING",
        createdAt: new Date().toDateString(),
      },
    }),
  );
};
