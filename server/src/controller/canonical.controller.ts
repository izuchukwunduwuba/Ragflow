import { Request, Response } from "express";
import { supabase } from "../config/supabase.config";

export const getCanonicalData = async (
  req: Request<{ documentId: string }>,
  res: Response,
): Promise<void> => {
  const { documentId } = req.params;

  try {
    const result = await supabase.query(
      `SELECT
        insured_name, insured_address, broker_name, mga_name,
        line_of_business, risk_description, region, country,
        annual_revenue, coverage_limit, deductible, premium,
        inception_date, expiry_date,
        prior_claims_count, prior_claims_amount,
        exclusions, confidence_scores, source_pages, flags,
        extracted_at, model
       FROM document_submissions
       WHERE document_id = $1`,
      [documentId],
    );

    if (result.rows.length === 0) {
      res.status(404).json({ message: "Canonical data not ready yet" });
      return;
    }

    res.status(200).json({ data: result.rows[0] });
  } catch (error) {
    console.error("Canonical fetch error:", error);
    res.status(500).json({ message: "Failed to fetch canonical data" });
  }
};
