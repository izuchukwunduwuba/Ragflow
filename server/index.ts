import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import documentRoutes from "./src/routes/documentRoutes";

dotenv.config();

const PORT = process.env.PORT || 5005;
const app = express();

app.use(cors({ origin: process.env.CLIENT_URL || "http://localhost:5173" }));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use("/api/docs", documentRoutes);

app.get("/health", (_req, res) => {
  res.status(200).json({ message: "ok" });
});

app.listen(PORT, () => {
  console.log(`app is running in localhost:${PORT}`);
});
