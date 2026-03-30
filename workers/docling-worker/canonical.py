import json
import os
import logging
import boto3
import psycopg2
from datetime import datetime, timezone

log = logging.getLogger(__name__)

bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "eu-west-2"))

BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")
SUPABASE_DB_URL = os.environ["SUPABASE_DB_URL"]

CANONICAL_SCHEMA = {
    "insured_name":         {"value": None, "confidence": None, "source_page": None},
    "insured_address":      {"value": None, "confidence": None, "source_page": None},
    "broker_name":          {"value": None, "confidence": None, "source_page": None},
    "mga_name":             {"value": None, "confidence": None, "source_page": None},
    "line_of_business":     {"value": None, "confidence": None, "source_page": None},
    "risk_description":     {"value": None, "confidence": None, "source_page": None},
    "region":               {"value": None, "confidence": None, "source_page": None},
    "country":              {"value": None, "confidence": None, "source_page": None},
    "annual_revenue":       {"value": None, "confidence": None, "source_page": None},
    "coverage_limit":       {"value": None, "confidence": None, "source_page": None},
    "deductible":           {"value": None, "confidence": None, "source_page": None},
    "premium":              {"value": None, "confidence": None, "source_page": None},
    "inception_date":       {"value": None, "confidence": None, "source_page": None},
    "expiry_date":          {"value": None, "confidence": None, "source_page": None},
    "prior_claims_count":   {"value": None, "confidence": None, "source_page": None},
    "prior_claims_amount":  {"value": None, "confidence": None, "source_page": None},
    "exclusions":           {"value": [],   "confidence": None, "source_page": None},
}

EXTRACTION_PROMPT = """You are an expert insurance document analyst.

Extract the following fields from the insurance document below.
For each field return:
- value: the extracted value (null if not found)
- confidence: high | medium | low
- source_page: the page number where the value was found (null if unknown)

Fields to extract:
- insured_name
- insured_address
- broker_name
- mga_name
- line_of_business (e.g. property, liability, cargo, marine, professional indemnity)
- risk_description
- region
- country
- annual_revenue (numeric value only, strip currency symbols)
- coverage_limit (numeric value only)
- deductible (numeric value only)
- premium (numeric value only)
- inception_date (ISO 8601 format)
- expiry_date (ISO 8601 format)
- prior_claims_count (integer)
- prior_claims_amount (numeric value only)
- exclusions (array of strings)

Respond ONLY with a valid JSON object. No explanation. No markdown. No extra text.

Document:
{document_text}"""


def extract_canonical_fields(full_text: str, document_id: str) -> dict:
    log.info("Extracting canonical fields for documentId=%s", document_id)

    prompt = EXTRACTION_PROMPT.format(document_text=full_text[:12000])

    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    raw = json.loads(response["body"].read())
    extracted = json.loads(raw["content"][0]["text"])

    canonical = json.loads(json.dumps(CANONICAL_SCHEMA))
    for field in canonical:
        if field in extracted:
            canonical[field] = extracted[field]

    log.info("Canonical extraction complete for documentId=%s", document_id)
    return canonical


def save_canonical_to_supabase(document_id: str, source_key: str, canonical_data: dict, flags: dict):
    log.info("Saving canonical data to Supabase for documentId=%s", document_id)
    f = canonical_data

    # Split model response into flat values, confidence scores, and source pages
    values = {field: meta.get("value") for field, meta in f.items()}
    confidence_scores = {field: meta.get("confidence") for field, meta in f.items()}
    source_pages = {field: meta.get("source_page") for field, meta in f.items()}

    with psycopg2.connect(SUPABASE_DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO document_submissions (
                    document_id, source_key, extracted_at, model,
                    insured_name, insured_address, broker_name, mga_name,
                    line_of_business, risk_description, region, country,
                    annual_revenue, coverage_limit, deductible, premium,
                    inception_date, expiry_date,
                    prior_claims_count, prior_claims_amount,
                    exclusions, confidence_scores, source_pages, flags
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (document_id) DO UPDATE SET
                    extracted_at        = EXCLUDED.extracted_at,
                    insured_name        = EXCLUDED.insured_name,
                    insured_address     = EXCLUDED.insured_address,
                    broker_name         = EXCLUDED.broker_name,
                    mga_name            = EXCLUDED.mga_name,
                    line_of_business    = EXCLUDED.line_of_business,
                    risk_description    = EXCLUDED.risk_description,
                    region              = EXCLUDED.region,
                    country             = EXCLUDED.country,
                    annual_revenue      = EXCLUDED.annual_revenue,
                    coverage_limit      = EXCLUDED.coverage_limit,
                    deductible          = EXCLUDED.deductible,
                    premium             = EXCLUDED.premium,
                    inception_date      = EXCLUDED.inception_date,
                    expiry_date         = EXCLUDED.expiry_date,
                    prior_claims_count  = EXCLUDED.prior_claims_count,
                    prior_claims_amount = EXCLUDED.prior_claims_amount,
                    exclusions          = EXCLUDED.exclusions,
                    confidence_scores   = EXCLUDED.confidence_scores,
                    source_pages        = EXCLUDED.source_pages,
                    flags               = EXCLUDED.flags
            """, (
                document_id,
                source_key,
                datetime.now(timezone.utc).isoformat(),
                BEDROCK_MODEL_ID,
                values.get("insured_name"),
                values.get("insured_address"),
                values.get("broker_name"),
                values.get("mga_name"),
                values.get("line_of_business"),
                values.get("risk_description"),
                values.get("region"),
                values.get("country"),
                values.get("annual_revenue"),
                values.get("coverage_limit"),
                values.get("deductible"),
                values.get("premium"),
                values.get("inception_date"),
                values.get("expiry_date"),
                values.get("prior_claims_count"),
                values.get("prior_claims_amount"),
                json.dumps(values.get("exclusions", [])),
                json.dumps(confidence_scores),
                json.dumps(source_pages),
                json.dumps(flags),
            ))
        conn.commit()
    log.info("Canonical data saved for documentId=%s", document_id)
