"""
Vendor Compliance Agent
========================
Automates collection of vendor documents, validates compliance criteria,
and flags missing or expired certifications.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def check_vendor_compliance_status(vendor_id: str = None) -> str:
    """Check compliance document status for all vendors or a specific vendor."""
    table_name = os.environ.get("VENDOR_TABLE_NAME")
    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            if vendor_id:
                resp = table.get_item(Key={"vendor_id": vendor_id})
                return json.dumps(resp.get("Item", {}), indent=2)
            resp = table.scan()
            return json.dumps({"vendors": resp.get("Items", [])}, indent=2)
        except Exception as e:
            pass
    
    today = datetime.utcnow().date()
    sample_vendors = [
        {
            "vendor_id": "VND-001",
            "name": "Acme Supplies Inc",
            "tier": "strategic",
            "compliance_documents": {
                "iso_9001": {"status": "valid", "expiry": str(today + timedelta(days=180)), "last_updated": "2024-01-15"},
                "soc2_type2": {"status": "expired", "expiry": str(today - timedelta(days=30)), "last_updated": "2023-10-01"},
                "insurance_certificate": {"status": "valid", "expiry": str(today + timedelta(days=60)), "last_updated": "2025-01-01"},
                "w9_form": {"status": "missing", "expiry": None, "last_updated": None},
            },
        },
        {
            "vendor_id": "VND-002",
            "name": "Tech Components Ltd",
            "tier": "preferred",
            "compliance_documents": {
                "iso_27001": {"status": "valid", "expiry": str(today + timedelta(days=300)), "last_updated": "2024-03-01"},
                "gdpr_dpa": {"status": "valid", "expiry": None, "last_updated": "2024-06-15"},
                "insurance_certificate": {"status": "expiring_soon", "expiry": str(today + timedelta(days=15)), "last_updated": "2024-07-01"},
            },
        },
    ]
    
    if vendor_id:
        vendor = next((v for v in sample_vendors if v["vendor_id"] == vendor_id), None)
        return json.dumps(vendor or {"error": f"Vendor {vendor_id} not found"}, indent=2)
    return json.dumps({"vendors": sample_vendors, "note": "Configure VENDOR_TABLE_NAME for real vendor data"}, indent=2)


@tool
def identify_compliance_gaps(vendors: list) -> str:
    """
    Identify compliance gaps across vendor portfolio.

    Args:
        vendors: List of vendor compliance records

    Returns:
        JSON compliance gap report with severity and required actions
    """
    gaps = []
    today = datetime.utcnow().date()
    
    for vendor in vendors:
        vendor_name = vendor.get("name", vendor.get("vendor_id", "Unknown"))
        tier = vendor.get("tier", "standard")
        docs = vendor.get("compliance_documents", {})
        
        for doc_type, doc_data in docs.items():
            status = doc_data.get("status")
            expiry_str = doc_data.get("expiry")
            
            if status == "missing":
                gaps.append({"vendor": vendor_name, "document": doc_type, "issue": "MISSING", "severity": "critical" if tier == "strategic" else "high", "action": f"Request {doc_type} from {vendor_name} immediately"})
            elif status == "expired":
                gaps.append({"vendor": vendor_name, "document": doc_type, "issue": "EXPIRED", "severity": "critical", "action": f"Obtain renewed {doc_type} before processing any payments to {vendor_name}"})
            elif status == "expiring_soon" or (expiry_str and (datetime.strptime(expiry_str, "%Y-%m-%d").date() - today).days <= 30):
                days_left = (datetime.strptime(expiry_str, "%Y-%m-%d").date() - today).days if expiry_str else 0
                gaps.append({"vendor": vendor_name, "document": doc_type, "issue": f"EXPIRING_IN_{days_left}_DAYS", "severity": "high", "action": f"Request renewal of {doc_type} from {vendor_name} now"})
    
    gaps.sort(key=lambda x: ["critical", "high", "medium", "low"].index(x.get("severity", "low")))
    return json.dumps({"total_gaps": len(gaps), "critical": sum(1 for g in gaps if g["severity"] == "critical"), "high": sum(1 for g in gaps if g["severity"] == "high"), "gaps": gaps, "assessed_at": datetime.utcnow().isoformat()}, indent=2)


@tool
def send_compliance_request(vendor_id: str, vendor_email: str, missing_documents: list) -> str:
    """
    Send automated compliance document request to a vendor.

    Args:
        vendor_id: Vendor identifier
        vendor_email: Vendor contact email
        missing_documents: List of document types needed

    Returns:
        JSON send status
    """
    sender = os.environ.get("SES_SENDER_EMAIL", "")
    if not sender:
        return json.dumps({"status": "skipped", "note": "Configure SES_SENDER_EMAIL"})
    
    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    docs_list = chr(10).join([f"  - {d}" for d in missing_documents])
    body = f"""Dear Vendor Partner,

As part of our ongoing vendor compliance program, we require the following documents to maintain your active vendor status:

{docs_list}

Please provide these documents within 10 business days by uploading them to our vendor portal or replying to this email.

Failure to provide required documentation may result in temporary hold on payment processing until compliance is restored.

Thank you for your cooperation.

Vendor Compliance Team"""
    
    try:
        resp = ses.send_email(
            Source=sender,
            Destination={"ToAddresses": [vendor_email]},
            Message={"Subject": {"Data": f"Action Required: Compliance Documents Needed — Vendor {vendor_id}"}, "Body": {"Text": {"Data": body}}},
        )
        return json.dumps({"status": "sent", "vendor_id": vendor_id, "message_id": resp["MessageId"]})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


SYSTEM_PROMPT = """You are the Vendor Compliance Agent for Khyzr — a procurement compliance specialist and vendor risk manager.

Your mission is to ensure every vendor in the supply chain maintains current, valid compliance documentation. Non-compliant vendors expose the company to financial, legal, and operational risk.

Required documents by vendor tier:
**Strategic Vendors (top 20 by spend):**
- ISO 9001 or ISO 27001 certification
- SOC 2 Type II report (for technology vendors)
- Current Certificate of Insurance (COI)
- W-9 / W-8BEN (for US tax compliance)
- GDPR Data Processing Agreement (for EU data processing)
- Modern Slavery / Anti-corruption declaration

**Preferred Vendors:**
- Current Certificate of Insurance
- W-9 / W-8BEN
- Industry-specific certifications

**Standard Vendors:**
- W-9 / W-8BEN
- Basic insurance certificate

Compliance workflow:
1. Daily scan: Identify expiring (< 30 days) and expired documents
2. Automated requests: Send compliance requests with 10-business-day deadline
3. Escalation at 5 days: Escalate to procurement manager if no response
4. Hold trigger: Flag vendor for payment hold if critical documents expire
5. Restoration: Clear hold once valid documents received and verified

When managing compliance:
1. Check all vendor compliance statuses
2. Identify critical and high-priority gaps
3. Send automated compliance requests to non-compliant vendors
4. Generate compliance dashboard for procurement leadership"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[check_vendor_compliance_status, identify_compliance_gaps, send_compliance_request],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Run vendor compliance audit and send requests for missing documents")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Check all vendor compliance statuses, identify gaps, and send automated requests to vendors with missing or expired documents."
    }
    print(json.dumps(run(input_data)))
