import express from "express";
import documentRoutes from "./src/routes/documentRoutes";
import dotenv from "dotenv";

dotenv.config();

const PORT = process.env.PORT || 5005;
const app = express();

app.use(express.json());

app.use("/api/docs", documentRoutes);
app.use(express.urlencoded({ extended: true }));

app.get("/health", (_req, res) => {
  res.status(200).json({ message: "ok" });
});

app.listen(PORT, () => {
  console.log(`app is running in localhost:${PORT}`);
});
