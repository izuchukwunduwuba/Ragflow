import { Pool } from "pg";
import dotenv from "dotenv";

dotenv.config();

export const supabase = new Pool({
  connectionString: process.env.SUPABASE_DB_URL,
});
