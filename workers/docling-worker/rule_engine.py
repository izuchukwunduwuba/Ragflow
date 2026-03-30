import logging

log = logging.getLogger(__name__)

REQUIRED_FIELDS = [
    "insured_name",
    "insured_address",
    "line_of_business",
    "region",
    "country",
    "annual_revenue",
    "coverage_limit",
    "inception_date",
    "expiry_date",
]

OPTIONAL_FIELDS = [
    "broker_name",
    "mga_name",
    "risk_description",
    "deductible",
    "premium",
    "prior_claims_count",
    "prior_claims_amount",
    "exclusions",
]


def run_rule_engine(document_id: str, canonical_data: dict) -> dict:
    log.info("Running rule engine for documentId=%s", document_id)
    flags = {}

    for field in REQUIRED_FIELDS:
        value = canonical_data.get(field, {}).get("value")
        if value is None or value == "" or value == []:
            flags[field] = {
                "severity": "critical",
                "message": f"{field.replace('_', ' ').title()} is missing",
            }

    for field in OPTIONAL_FIELDS:
        value = canonical_data.get(field, {}).get("value")
        if value is None or value == "" or value == []:
            flags[field] = {
                "severity": "warning",
                "message": f"{field.replace('_', ' ').title()} is missing",
            }

    log.info("Rule engine produced %d flag(s) for documentId=%s", len(flags), document_id)
    return flags
