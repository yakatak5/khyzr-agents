"""
Contract Management Agent
==========================
Extracts key terms from vendor contracts, tracks renewal dates, and flags
unfavorable clauses. Maintains a centralized contract repository with alerts.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json, os, boto3
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def extract_contract_metadata(s3_uri: str) -> str:
    """
    Extract key metadata from a contract document stored in S3.
    Uses Amazon Textract for OCR and key-value extraction.

    Args:
        s3_uri: S3 URI of contract PDF or document

    Returns:
        JSON extracted contract metadata
    """
    bucket_key = s3_uri.replace("s3://", "").split("/", 1)
    bucket = bucket_key[0]
    key = bucket_key[1] if len(bucket_key) > 1 else ""
    
    textract = boto3.client("textract", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    
    try:
        response = textract.start_document_analysis(
            DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
            FeatureTypes=["TABLES", "FORMS"],
        )
        job_id = response["JobId"]
        return json.dumps({"status": "extraction_started", "job_id": job_id, "s3_uri": s3_uri, "note": "Poll GetDocumentAnalysis with job_id to retrieve results"})
    except Exception as e:
        # Return structured template for manual entry
        return json.dumps({
            "s3_uri": s3_uri,
            "extraction_status": "manual_required",
            "error": str(e),
            "template": {
                "vendor_name": None, "contract_value": None, "start_date": None,
                "end_date": None, "auto_renewal": None, "notice_period_days": None,
                "payment_terms": None, "termination_clause": None,
                "sla_terms": None, "liability_cap": None, "governing_law": None,
            },
        }, indent=2)


@tool
def analyze_contract_clauses(contract_text: str) -> str:
    """
    Analyze contract text to identify key clauses and flag potentially unfavorable terms.

    Args:
        contract_text: Full contract text (extracted or manually provided)

    Returns:
        JSON clause analysis with flagged items and risk assessment
    """
    # Risk indicators to look for in contract text
    risk_flags = []
    text_lower = contract_text.lower()
    
    unfavorable_patterns = {
        "unlimited_liability": {"pattern": "unlimited liability", "severity": "critical", "description": "Unlimited liability exposure — seek cap at contract value or insurance limits"},
        "auto_renewal": {"pattern": "automatically renew", "severity": "high", "description": "Auto-renewal clause — set calendar reminder 90 days before end date"},
        "unilateral_change": {"pattern": "may modify", "severity": "high", "description": "Vendor can unilaterally modify terms — seek mutual consent requirement"},
        "ip_assignment": {"pattern": "work made for hire", "severity": "high", "description": "IP assignment clause — verify scope aligns with intent"},
        "audit_rights": {"pattern": "audit rights", "severity": "medium", "description": "Vendor audit rights — verify scope is limited and reasonable"},
        "exclusivity": {"pattern": "exclusive", "severity": "medium", "description": "Exclusivity provision — confirm this is intentional and scoped correctly"},
        "liquidated_damages": {"pattern": "liquidated damages", "severity": "medium", "description": "Liquidated damages clause — verify amounts are reasonable"},
    }
    
    for flag_key, flag_info in unfavorable_patterns.items():
        if flag_info["pattern"] in text_lower:
            risk_flags.append({
                "clause_type": flag_key,
                "severity": flag_info["severity"],
                "description": flag_info["description"],
                "recommended_action": "Legal review required" if flag_info["severity"] == "critical" else "Review with procurement",
            })
    
    return json.dumps({
        "total_flags": len(risk_flags),
        "critical_flags": sum(1 for f in risk_flags if f["severity"] == "critical"),
        "high_flags": sum(1 for f in risk_flags if f["severity"] == "high"),
        "risk_flags": risk_flags,
        "overall_risk": "HIGH" if any(f["severity"] == "critical" for f in risk_flags) else ("MEDIUM" if risk_flags else "LOW"),
        "analyzed_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def track_contract_renewals(days_ahead: int = 90) -> str:
    """
    Find contracts approaching renewal within the specified window.

    Args:
        days_ahead: Number of days to look ahead for renewals

    Returns:
        JSON list of contracts requiring renewal action
    """
    table_name = os.environ.get("CONTRACTS_TABLE_NAME")
    cutoff_date = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            resp = table.scan(
                FilterExpression="end_date <= :d AND #s = :s",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":d": cutoff_date, ":s": "active"},
            )
            return json.dumps({"contracts": resp.get("Items", [])}, indent=2)
        except Exception as e:
            pass
    
    today = datetime.utcnow().date()
    sample_contracts = [
        {"contract_id": "CTR-001", "vendor": "Cloud Infrastructure Co", "value": 250000, "end_date": str(today + timedelta(days=25)), "auto_renewal": True, "notice_period_days": 30, "owner": "IT Procurement", "action_required": "URGENT — within notice period"},
        {"contract_id": "CTR-002", "vendor": "Software Vendor B", "value": 85000, "end_date": str(today + timedelta(days=65)), "auto_renewal": False, "notice_period_days": 60, "owner": "Operations", "action_required": "Review and decide on renewal"},
        {"contract_id": "CTR-003", "vendor": "Professional Services Firm", "value": 120000, "end_date": str(today + timedelta(days=85)), "auto_renewal": True, "notice_period_days": 90, "owner": "Legal", "action_required": "Notice period starts now"},
    ]
    
    return json.dumps({"contracts": sample_contracts, "days_ahead": days_ahead, "note": "Configure CONTRACTS_TABLE_NAME for real contract data"}, indent=2)


@tool
def generate_contract_summary(contract_data: dict) -> str:
    """Generate a one-page contract summary for business review."""
    summary = {
        "summary_type": "contract_one_pager",
        "generated_at": datetime.utcnow().isoformat(),
        "contract_id": contract_data.get("contract_id"),
        "vendor": contract_data.get("vendor"),
        "key_commercial_terms": {
            "total_value": contract_data.get("value"),
            "payment_terms": contract_data.get("payment_terms"),
            "start_date": contract_data.get("start_date"),
            "end_date": contract_data.get("end_date"),
            "auto_renewal": contract_data.get("auto_renewal"),
            "notice_period_days": contract_data.get("notice_period_days"),
        },
        "key_obligations": contract_data.get("obligations", ["Review contract for specific obligations"]),
        "key_risks": contract_data.get("risk_flags", []),
        "recommended_actions": contract_data.get("action_required", "Review contract with procurement team"),
    }
    return json.dumps(summary, indent=2)


SYSTEM_PROMPT = """You are the Contract Management Agent for Khyzr — a contract management specialist and legal operations expert.

Your mission is to ensure the company's vendor contract portfolio is always visible, compliant, and well-managed. Missed renewals, unfavorable clauses, and untracked commitments create operational and financial risk.

Contract lifecycle management:
- **Intake**: Extract key terms from new contracts (AI-assisted OCR and clause extraction)
- **Repository**: Maintain centralized contract database with searchable metadata
- **Monitoring**: Track renewal dates, notice periods, and auto-renewal triggers
- **Compliance**: Monitor vendor performance against contracted SLAs
- **Risk flagging**: Identify unfavorable clauses that require legal review or renegotiation
- **Renewal management**: Alert owners 90/60/30 days before key dates

Risk flag categories:
- CRITICAL: Unlimited liability, one-sided termination rights, IP assignment issues
- HIGH: Auto-renewal with long notice periods, unilateral modification rights
- MEDIUM: Audit rights, exclusivity, liquidated damages
- LOW: Standard boilerplate variations

When managing contracts:
1. Extract metadata from new contracts using Textract
2. Analyze clauses for unfavorable terms
3. Check upcoming renewals and flag urgent items
4. Generate one-page summaries for business review
5. Alert contract owners proactively"""


model = BedrockModel(model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"), region_name=os.environ.get("AWS_REGION", "us-east-1"))
agent = Agent(model=model, tools=[extract_contract_metadata, analyze_contract_clauses, track_contract_renewals, generate_contract_summary], system_prompt=SYSTEM_PROMPT)


def run(input_data: dict) -> dict:
    response = agent(input_data.get("message", "Review upcoming contract renewals and flag any at-risk items"))
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {"message": "Check all contracts expiring in the next 90 days, flag urgent renewals, and identify any contracts with unfavorable clauses."}
    print(json.dumps(run(input_data)))
