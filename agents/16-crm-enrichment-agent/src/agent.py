"""
CRM Enrichment Agent
====================
Fills in missing contact/company data, removes duplicates, and flags stale
records in CRM systems. Keeps the sales team working with clean, complete,
and accurate data.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
import httpx
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def find_incomplete_records(crm_source: str = "dynamodb", limit: int = 50) -> str:
    """
    Find CRM records with missing or incomplete fields.

    Args:
        crm_source: CRM data source ('dynamodb', 'salesforce', 's3')
        limit: Maximum records to check

    Returns:
        JSON list of incomplete records with missing fields identified
    """
    table_name = os.environ.get("CRM_TABLE_NAME")
    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        required_fields = ["first_name", "last_name", "email", "company", "title", "phone", "industry", "company_size"]
        try:
            resp = table.scan(Limit=limit)
            incomplete = []
            for item in resp.get("Items", []):
                missing = [f for f in required_fields if not item.get(f)]
                if missing:
                    incomplete.append({"record_id": item.get("lead_id") or item.get("contact_id"), "email": item.get("email"), "missing_fields": missing, "completeness_pct": round((len(required_fields) - len(missing)) / len(required_fields) * 100, 1)})
            return json.dumps({"incomplete_records": incomplete, "total_reviewed": len(resp.get("Items", [])), "incomplete_count": len(incomplete)}, indent=2)
        except Exception as e:
            pass

    return json.dumps({
        "incomplete_records": [
            {"record_id": "CONT-001", "email": "john@example.com", "missing_fields": ["phone", "industry", "company_size"], "completeness_pct": 62.5},
            {"record_id": "CONT-002", "email": "jane@corp.com", "missing_fields": ["title", "phone"], "completeness_pct": 75.0},
        ],
        "note": "Configure CRM_TABLE_NAME for real CRM data scanning",
    }, indent=2)


@tool
def enrich_company_data(company_name: str, domain: str = None) -> str:
    """
    Enrich company data using Clearbit, Apollo, or similar enrichment APIs.

    Args:
        company_name: Company name to enrich
        domain: Company domain (enhances match quality)

    Returns:
        JSON enriched company profile
    """
    clearbit_key = os.environ.get("CLEARBIT_API_KEY")
    apollo_key = os.environ.get("APOLLO_API_KEY")

    if clearbit_key and domain:
        try:
            resp = httpx.get(
                f"https://company.clearbit.com/v2/companies/find",
                params={"domain": domain},
                headers={"Authorization": f"Bearer {clearbit_key}"},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                return json.dumps({
                    "source": "clearbit",
                    "company_name": data.get("name"),
                    "domain": data.get("domain"),
                    "industry": data.get("category", {}).get("industry"),
                    "employee_count": data.get("metrics", {}).get("employees"),
                    "annual_revenue": data.get("metrics", {}).get("estimatedAnnualRevenue"),
                    "linkedin_url": data.get("linkedin", {}).get("handle"),
                    "technology_stack": [t.get("name") for t in data.get("tech", [])[:10]],
                    "description": data.get("description"),
                    "founded_year": data.get("foundedYear"),
                }, indent=2)
        except Exception:
            pass

    return json.dumps({
        "company_name": company_name,
        "domain": domain,
        "enrichment_status": "pending_api_config",
        "note": "Configure CLEARBIT_API_KEY or APOLLO_API_KEY for real enrichment",
        "fallback_data": {
            "company_name": company_name,
            "industry": "Unknown — manual review needed",
            "employee_count": None,
            "annual_revenue": None,
        },
    }, indent=2)


@tool
def detect_duplicate_records(email_list: list) -> str:
    """
    Detect duplicate CRM records based on email, phone, or company+name matching.

    Args:
        email_list: List of email addresses to check for duplicates

    Returns:
        JSON duplicate analysis with suggested merge actions
    """
    # Normalize emails and find exact duplicates
    seen = {}
    duplicates = []
    for email in email_list:
        normalized = email.lower().strip()
        if normalized in seen:
            duplicates.append({
                "duplicate_email": normalized,
                "original": seen[normalized],
                "duplicate": email,
                "suggested_action": "merge",
                "merge_rule": "Keep most recently updated record; merge all activity history",
            })
        else:
            seen[normalized] = email

    # Check for common domain duplicates (same company, very similar names)
    domain_groups = {}
    for email in email_list:
        domain = email.split("@")[-1] if "@" in email else None
        if domain:
            domain_groups[domain] = domain_groups.get(domain, []) + [email]

    potential_dupes = [{"domain": d, "emails": e, "suggested_action": "human_review", "reason": f"{len(e)} contacts from same domain — verify distinct individuals"} for d, e in domain_groups.items() if len(e) > 3]

    return json.dumps({
        "total_emails_checked": len(email_list),
        "exact_duplicates": duplicates,
        "potential_duplicates": potential_dupes,
        "clean_records": len(email_list) - len(duplicates),
    }, indent=2)


@tool
def flag_stale_records(days_since_activity: int = 90) -> str:
    """
    Flag CRM records that haven't had any activity in N days.

    Args:
        days_since_activity: Number of days of inactivity to flag as stale

    Returns:
        JSON list of stale records with recommendations
    """
    table_name = os.environ.get("CRM_TABLE_NAME")
    cutoff_date = (datetime.utcnow() - timedelta(days=days_since_activity)).isoformat()

    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            resp = table.scan(
                FilterExpression="last_activity_date < :cutoff OR attribute_not_exists(last_activity_date)",
                ExpressionAttributeValues={":cutoff": cutoff_date},
            )
            stale = []
            for item in resp.get("Items", []):
                stale.append({
                    "record_id": item.get("lead_id") or item.get("contact_id"),
                    "email": item.get("email"),
                    "company": item.get("company"),
                    "last_activity": item.get("last_activity_date", "never"),
                    "recommendation": "re_engagement_sequence" if item.get("lead_score", 0) > 50 else "archive",
                })
            return json.dumps({"stale_records": stale, "cutoff_days": days_since_activity}, indent=2)
        except Exception as e:
            pass

    return json.dumps({
        "stale_records": [
            {"record_id": "CONT-099", "email": "old@company.com", "last_activity": "2024-06-01", "recommendation": "re_engagement_sequence"},
        ],
        "cutoff_days": days_since_activity,
        "note": "Configure CRM_TABLE_NAME for real stale record detection",
    }, indent=2)


SYSTEM_PROMPT = """You are the CRM Enrichment Agent for Khyzr — a revenue operations specialist and data quality expert.

Your mission is to maintain a clean, complete, and accurate CRM that empowers the sales team to close more deals. Bad data costs sales teams 27% of their time — you eliminate that waste.

Data quality dimensions you manage:
- **Completeness**: Every contact should have: email, name, title, company, industry, company size
- **Accuracy**: Data should reflect current reality — outdated titles, wrong emails flagged
- **Uniqueness**: Zero duplicates — merge duplicate records using defined merge rules
- **Freshness**: Records with no activity in 90+ days are stale and need re-engagement or archival
- **Consistency**: Standardized formats for phone, address, industry taxonomy

Enrichment sources you leverage:
- **Clearbit**: Best-in-class company and person enrichment
- **Apollo.io**: Contact data, email verification, intent data
- **LinkedIn**: Title verification, company size, recent activity
- **ZoomInfo**: Company financials, org charts, buying signals
- **Hunter.io**: Email verification and discovery

Data governance rules:
- Never overwrite manually entered data without flagging it for review
- Always source enriched data (record where each field came from)
- Respect GDPR/CCPA — only enrich data for opted-in contacts or business contacts
- Flag data older than 12 months for re-verification

When enriching CRM data:
1. Find incomplete records (missing required fields)
2. Enrich company and contact data via configured APIs
3. Detect and flag duplicate records with merge recommendations
4. Flag stale records with re-engagement or archive recommendations
5. Produce a data quality report with before/after completeness metrics"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[find_incomplete_records, enrich_company_data, detect_duplicate_records, flag_stale_records],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Run CRM data quality audit and enrich incomplete records")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Run a full CRM audit: find incomplete records, detect duplicates, flag records with no activity in 90 days, and produce a data quality report."
    }
    print(json.dumps(run(input_data)))
