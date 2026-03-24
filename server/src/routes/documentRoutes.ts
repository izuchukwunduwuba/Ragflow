import express from "express";
import { uploadDocument } from "../controller/s3.document.uploader";

const router = express.Router();

router.post("/presign-upload", uploadDocument);

export default router;
