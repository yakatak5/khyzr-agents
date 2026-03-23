"""
AR Collections Agent
====================
Monitors aging accounts receivable, scores collection risk by tier, generates
personalized collection emails, escalates overdue accounts, and updates statuses.

Built with AWS Strands Agents + AgentCore on AWS Bedrock (Claude Sonnet).
Deploys as an AWS Lambda function serving as a Bedrock Action Group executor.
"""

import json
import io
import os
import boto3
from datetime import datetime

# ---------------------------------------------------------------------------
# Optional strands imports — only needed for local run() mode
# ---------------------------------------------------------------------------
try:
    from strands import Agent, tool
    from strands.models import BedrockModel
    STRANDS_AVAILABLE = True
except ImportError:
    STRANDS_AVAILABLE = False
    def tool(fn): return fn

# ---------------------------------------------------------------------------
# Excel helpers
# ---------------------------------------------------------------------------

def _fetch_s3_bytes(s3_uri: str):
    """Fetch raw bytes from an S3 URI. Returns (bytes, key) or (None, '')."""
    try:
        parts = s3_uri[5:].split("/", 1)
        bucket, key = parts[0], parts[1]
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read(), key
    except Exception as e:
        return None, ""


def _parse_aging_report_excel(raw_bytes: bytes) -> dict:
    """
    Parse an Excel AR aging report workbook.

    Supports:
      - Single sheet with accounts as rows (header in row 1)
      - Multi-sheet: first sheet = summary, second = accounts

    Expected columns (flexible matching):
      Account ID, Company Name, Contact Name, Contact Email,
      Invoice Number, Invoice Date, Due Date, Days Overdue,
      Balance, Payment History, Last Payment Date
    """
    try:
        import openpyxl
    except ImportError:
        return {"error": "openpyxl not installed"}

    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True)

    # Find the sheet with account rows (has >2 columns)
    ws = None
    for sheet in wb.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        non_empty = [r for r in rows if any(c is not None for c in r)]
        if non_empty and len([c for c in non_empty[0] if c is not None]) > 3:
            ws = sheet
            break
    if ws is None:
        ws = wb.worksheets[0]

    all_rows = [
        [str(c).strip() if c is not None else "" for c in row]
        for row in ws.iter_rows(values_only=True)
        if any(c is not None for c in row)
    ]
    if not all_rows:
        return {"error": "Empty worksheet"}

    # Normalize header
    header = [h.lower().replace(" ", "_").replace("-", "_") for h in all_rows[0]]

    def col(row, *keys):
        for k in keys:
            for i, h in enumerate(header):
                if k in h and i < len(row):
                    v = row[i]
                    return v if v != "" else None
        return None

    accounts = []
    for row in all_rows[1:]:
        if not any(c for c in row if c):
            continue
        try:
            balance = float(str(col(row, "balance", "amount", "outstanding") or 0).replace(",", "").replace("$", ""))
            days = int(float(str(col(row, "days_overdue", "days_past", "overdue_days") or 0)))
        except (ValueError, TypeError):
            balance, days = 0.0, 0

        accounts.append({
            "account_id":        col(row, "account_id", "acct_id", "id") or f"ACC-{len(accounts)+1:05d}",
            "company_name":      col(row, "company_name", "company", "customer") or "",
            "contact_name":      col(row, "contact_name", "contact") or "",
            "contact_email":     col(row, "contact_email", "email") or "",
            "invoice_number":    col(row, "invoice_number", "invoice_no", "invoice") or "",
            "invoice_date":      col(row, "invoice_date", "issued") or "",
            "due_date":          col(row, "due_date", "due") or "",
            "days_overdue":      days,
            "balance":           balance,
            "payment_history":   col(row, "payment_history", "history", "pay_history") or "unknown",
            "last_payment_date": col(row, "last_payment", "last_paid") or "",
        })

    total = sum(a["balance"] for a in accounts)
    return {
        "report_date":   datetime.utcnow().strftime("%Y-%m-%d"),
        "currency":      "USD",
        "extraction_method": "excel_openpyxl",
        "summary": {
            "total_ar":     total,
            "current":      sum(a["balance"] for a in accounts if a["days_overdue"] == 0),
            "days_1_30":    sum(a["balance"] for a in accounts if 1 <= a["days_overdue"] <= 30),
            "days_31_60":   sum(a["balance"] for a in accounts if 31 <= a["days_overdue"] <= 60),
            "days_61_90":   sum(a["balance"] for a in accounts if 61 <= a["days_overdue"] <= 90),
            "days_91_plus": sum(a["balance"] for a in accounts if a["days_overdue"] > 90),
        },
        "accounts": accounts,
    }

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

DEMO_ACCOUNTS = [
    {
        "account_id": "ACC-10021", "company_name": "Nexus Technologies Inc.",
        "contact_email": "ap@nexustech.com", "contact_name": "Sarah Chen",
        "invoice_number": "INV-2024-0891", "invoice_date": "2024-01-10",
        "due_date": "2024-02-09", "days_overdue": 32, "balance": 48500.00,
        "payment_history": "good", "last_payment_date": "2023-12-15",
    },
    {
        "account_id": "ACC-10045", "company_name": "Meridian Logistics Group",
        "contact_email": "finance@meridianlogistics.com", "contact_name": "Robert Okafor",
        "invoice_number": "INV-2024-0742", "invoice_date": "2023-12-20",
        "due_date": "2024-01-19", "days_overdue": 53, "balance": 127000.00,
        "payment_history": "slow_pay", "last_payment_date": "2023-10-08",
    },
    {
        "account_id": "ACC-10078", "company_name": "Cascade Retail Corp",
        "contact_email": "payments@cascaderetail.com", "contact_name": "Linda Park",
        "invoice_number": "INV-2024-0615", "invoice_date": "2023-11-15",
        "due_date": "2023-12-15", "days_overdue": 88, "balance": 89500.00,
        "payment_history": "poor", "last_payment_date": "2023-08-20",
    },
    {
        "account_id": "ACC-10092", "company_name": "Summit Healthcare Partners",
        "contact_email": "billing@summithealthcare.com", "contact_name": "Michael Torres",
        "invoice_number": "INV-2024-0582", "invoice_date": "2023-11-01",
        "due_date": "2023-12-01", "days_overdue": 102, "balance": 42000.00,
        "payment_history": "poor", "last_payment_date": "2023-07-15",
    },
]


@tool
def fetch_aging_report(as_of_date: str = "", min_days_overdue: int = 0, excel_source: str = "") -> str:
    """
    Fetch the AR aging report. Accepts an Excel file (.xlsx) from S3 or returns demo data.

    Args:
        as_of_date: Report date YYYY-MM-DD (defaults to today)
        min_days_overdue: Filter accounts overdue by at least this many days
        excel_source: Optional S3 URI (s3://bucket/key.xlsx) to parse a real Excel aging report

    Returns:
        JSON string with AR aging summary and individual account details
    """
    report_date = as_of_date or datetime.utcnow().strftime("%Y-%m-%d")

    # Parse Excel if provided
    if excel_source:
        raw_bytes, key = None, ""
        if excel_source.startswith("s3://"):
            raw_bytes, key = _fetch_s3_bytes(excel_source)
        elif excel_source.endswith((".xlsx", ".xls")):
            try:
                with open(excel_source, "rb") as f:
                    raw_bytes = f.read()
            except Exception:
                pass
        if raw_bytes:
            parsed = _parse_aging_report_excel(raw_bytes)
            if "error" not in parsed:
                if min_days_overdue > 0:
                    parsed["accounts"] = [a for a in parsed["accounts"] if a["days_overdue"] >= min_days_overdue]
                return json.dumps(parsed, indent=2)

    # Default: return demo data
    aging_data = {
        "report_date": report_date,
        "currency": "USD",
        "summary": {
            "total_ar": 1847500.00, "current": 820000.00,
            "days_1_30": 385000.00, "days_31_60": 312500.00,
            "days_61_90": 198000.00, "days_91_plus": 132000.00,
        },
        "accounts": DEMO_ACCOUNTS,
    }
    if min_days_overdue > 0:
        aging_data["accounts"] = [a for a in aging_data["accounts"] if a["days_overdue"] >= min_days_overdue]
    return json.dumps(aging_data, indent=2)


@tool
def score_collection_risk(account_data: str) -> str:
    """
    Score each account by collection risk tier based on days overdue, balance, and payment history.

    Args:
        account_data: JSON string from fetch_aging_report

    Returns:
        JSON string with accounts ranked by risk tier (Critical/High/Medium/Low)
    """
    try:
        data = json.loads(account_data)
        accounts = data.get("accounts", [])
    except Exception:
        return json.dumps({"error": "Invalid account data"})

    scored = []
    for acct in accounts:
        days    = acct.get("days_overdue", 0)
        balance = acct.get("balance", 0)
        history = acct.get("payment_history", "good")

        days_score    = min(100, days * 1.0)
        balance_score = min(100, balance / 2000)
        history_score = {"good": 0, "slow_pay": 30, "poor": 60, "collections": 90}.get(history, 20)
        risk_score    = int((days_score * 0.4) + (balance_score * 0.35) + (history_score * 0.25))

        if risk_score >= 70 or days >= 90:
            tier, action = "Critical", "Escalate to collections attorney or agency"
        elif risk_score >= 45 or days >= 60:
            tier, action = "High", "Senior collections rep — direct phone call required"
        elif risk_score >= 20 or days >= 30:
            tier, action = "Medium", "Send formal collection notice with payment plan offer"
        else:
            tier, action = "Low", "Send friendly payment reminder"

        scored.append({
            "account_id": acct.get("account_id"), "company_name": acct.get("company_name"),
            "balance": balance, "days_overdue": days, "risk_score": risk_score,
            "risk_tier": tier, "recommended_action": action,
            "contact_email": acct.get("contact_email"), "contact_name": acct.get("contact_name"),
        })

    scored.sort(key=lambda x: x["risk_score"], reverse=True)
    return json.dumps({
        "scored_accounts": scored,
        "tier_summary": {t: sum(1 for a in scored if a["risk_tier"] == t) for t in ["Critical", "High", "Medium", "Low"]},
        "total_at_risk": sum(a["balance"] for a in scored),
        "scored_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def draft_collection_email(account_id: str, company_name: str, contact_name: str,
                            days_overdue: int, balance: float, risk_tier: str) -> str:
    """
    Draft a personalized collection email appropriate to the risk tier.

    Args:
        account_id: Account identifier
        company_name: Customer company name
        contact_name: AP contact name
        days_overdue: Days the invoice is overdue
        balance: Outstanding balance
        risk_tier: Low / Medium / High / Critical

    Returns:
        JSON string with drafted email subject and body
    """
    company_from = os.environ.get("COMPANY_NAME", "Khyzr")

    templates = {
        "Low": (
            "Friendly Payment Reminder — Invoice Outstanding",
            f"Dear {contact_name},\n\nI hope this message finds you well. This is a friendly reminder that an invoice of ${balance:,.2f} is now {days_overdue} days past due.\n\nWe value our partnership with {company_name} and want to make this as easy as possible. Please arrange payment at your earliest convenience.\n\nThank you for your continued business!"
        ),
        "Medium": (
            f"Payment Required — ${balance:,.2f} Overdue ({days_overdue} Days)",
            f"Dear {contact_name},\n\nThis is a formal notice that ${balance:,.2f} from {company_name} is now {days_overdue} days overdue.\n\nPlease remit payment immediately or contact us within 5 business days to discuss a payment arrangement. We are open to a structured payment plan if needed."
        ),
        "High": (
            f"URGENT: Overdue Account — ${balance:,.2f} — Immediate Action Required",
            f"Dear {contact_name},\n\nYour account with {company_from} has a seriously overdue balance of ${balance:,.2f} now {days_overdue} days past due.\n\nFailure to remit payment or contact us within 48 hours will result in account suspension and referral to our senior collections team. Please call us immediately to resolve this."
        ),
        "Critical": (
            f"FINAL NOTICE — ${balance:,.2f} — Account Referred for Collections",
            f"Dear {contact_name},\n\nThis is a final demand for payment of ${balance:,.2f}, now {days_overdue} days overdue.\n\nYour account is being referred to our external collections agency unless payment is received within 24 hours. Pay immediately via our secure portal or contact our collections department at once."
        ),
    }
    subject, body = templates.get(risk_tier, templates["Medium"])
    tones = {"Low": "friendly", "Medium": "formal", "High": "urgent", "Critical": "critical"}

    return json.dumps({
        "account_id": account_id, "email_subject": subject, "email_body": body,
        "tone": tones.get(risk_tier, "formal"), "risk_tier": risk_tier,
        "drafted_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def escalate_account(account_id: str, risk_tier: str, balance: float,
                     days_overdue: int, company_name: str, email_draft: str) -> str:
    """
    Escalate an overdue account — notify internal team based on risk tier.

    Args:
        account_id: Account identifier
        risk_tier: Low / Medium / High / Critical
        balance: Outstanding balance
        days_overdue: Days overdue
        company_name: Customer company name
        email_draft: JSON string of the drafted collection email

    Returns:
        JSON string with escalation actions taken
    """
    ar_manager = os.environ.get("AR_MANAGER_EMAIL", "ar-manager@company.com")
    cfo_email  = os.environ.get("CFO_EMAIL", "cfo@company.com")

    routing = {
        "Critical": {"recipients": [ar_manager, cfo_email], "level": "External collections referral"},
        "High":     {"recipients": [ar_manager],             "level": "Senior collections rep assigned"},
        "Medium":   {"recipients": [ar_manager],             "level": "Formal notice sent"},
        "Low":      {"recipients": [],                       "level": "Automated reminder sent"},
    }
    r = routing.get(risk_tier, routing["Medium"])
    actions = [{"action": "internal_notification", "recipients": r["recipients"],
                "escalation_level": r["level"], "status": "queued"}]
    if risk_tier in ("Critical", "High"):
        actions.append({"action": "service_suspension_review", "account_id": account_id, "status": "flagged"})

    return json.dumps({
        "account_id": account_id, "company_name": company_name,
        "risk_tier": risk_tier, "balance": balance, "days_overdue": days_overdue,
        "escalation_level": r["level"], "actions_taken": actions,
        "escalated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def update_collection_status(account_id: str, new_status: str, notes: str = "") -> str:
    """
    Update the collection status for an account and record it in DynamoDB.

    Args:
        account_id: Account identifier
        new_status: reminder_sent / escalated / payment_plan / in_collections / paid / disputed
        notes: Optional notes about the collection activity

    Returns:
        JSON string with update confirmation and next scheduled action
    """
    valid = ["reminder_sent", "escalated", "payment_plan", "in_collections", "paid", "disputed"]
    if new_status not in valid:
        return json.dumps({"error": f"Invalid status. Must be one of: {valid}"})

    next_actions = {
        "reminder_sent":  {"action": "Follow-up call",          "in_days": 5},
        "escalated":      {"action": "Review escalation",        "in_days": 2},
        "payment_plan":   {"action": "Monitor first payment",    "in_days": 30},
        "in_collections": {"action": "Agency status check",      "in_days": 14},
        "paid":           {"action": "None — account cleared",   "in_days": None},
        "disputed":       {"action": "Legal review",             "in_days": 3},
    }
    entry = {
        "account_id":   account_id,
        "updated_at":   datetime.utcnow().isoformat(),
        "new_status":   new_status,
        "notes":        notes,
        "updated_by":   "AR Collections Agent",
        "next_action":  next_actions.get(new_status, {}),
    }

    dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    table_name = os.environ.get("AR_COLLECTIONS_TABLE", "khyzr-ar-collections-demo")
    try:
        table = dynamodb.Table(table_name)
        table.put_item(Item=entry)
        return json.dumps({"status": "recorded", "entry": entry})
    except Exception as e:
        return json.dumps({"status": "simulated", "note": str(e), "entry": entry})

# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the AR Collections Agent for Khyzr — an expert accounts receivable specialist with deep knowledge of collections best practices, cash flow management, and customer relationship preservation.

Your mission is to monitor the aging AR portfolio, score collection risk, generate personalized outreach, escalate overdue accounts appropriately, and update collection statuses to keep cash flowing.

When working the collections queue:
1. Fetch the aging AR report using fetch_aging_report (optionally pass an excel_source S3 URI for real Excel reports)
2. Score each account by risk tier using score_collection_risk (Critical/High/Medium/Low)
3. Draft tier-appropriate collection emails using draft_collection_email
4. Escalate accounts using escalate_account
5. Update collection status using update_collection_status

Risk tier framework:
- Low (1-30 days, good history): Friendly automated reminder
- Medium (31-60 days or slow-pay): Formal notice + payment plan offer
- High (61-90 days or large balance): Senior collector + direct call
- Critical (90+ days or poor history): External collections agency

Flag 🚨 any account where overdue balance exceeds $100K. Monitor DSO — alert if >60 days.
Preserve customer relationships wherever possible — most late payments are cash flow issues, not bad faith."""

if STRANDS_AVAILABLE:
    model = BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )
    agent = Agent(
        model=model,
        tools=[fetch_aging_report, score_collection_risk, draft_collection_email,
               escalate_account, update_collection_status],
        system_prompt=SYSTEM_PROMPT,
    )

# ---------------------------------------------------------------------------
# Bedrock Action Group entry point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """Route Bedrock Action Group invocations to the correct tool."""
    action_group = event.get("actionGroup", "")
    api_path     = event.get("apiPath", "")

    # Parse parameters from both formats
    params = {}
    for p in event.get("parameters", []):
        params[p["name"]] = p["value"]
    rb = event.get("requestBody", {})
    for _, media in rb.get("content", {}).items():
        for prop in media.get("properties", []):
            params[prop["name"]] = prop["value"]

    def p(key, default=""):   return params.get(key, default)
    def pi(key, default=0):
        try: return int(float(params.get(key, default)))
        except: return default
    def pf(key, default=0.0):
        try: return float(params.get(key, default))
        except: return default

    if api_path == "/fetch-aging-report":
        result = fetch_aging_report(p("as_of_date"), pi("min_days_overdue"), p("excel_source"))
    elif api_path == "/score-collection-risk":
        result = score_collection_risk(p("account_data"))
    elif api_path == "/draft-collection-email":
        result = draft_collection_email(
            p("account_id"), p("company_name"), p("contact_name"),
            pi("days_overdue"), pf("balance"), p("risk_tier")
        )
    elif api_path == "/escalate-account":
        result = escalate_account(
            p("account_id"), p("risk_tier"), pf("balance"),
            pi("days_overdue"), p("company_name"), p("email_draft")
        )
    elif api_path == "/update-collection-status":
        result = update_collection_status(p("account_id"), p("new_status"), p("notes"))
    else:
        result = json.dumps({"error": f"Unknown api_path: {api_path}"})

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "apiPath": api_path,
            "httpMethod": event.get("httpMethod", "POST"),
            "httpStatusCode": 200,
            "responseBody": {"application/json": {"body": result}},
        },
    }

# ---------------------------------------------------------------------------
# Local entry point
# ---------------------------------------------------------------------------

def run(input_data: dict) -> dict:
    """Main entry point for local testing."""
    message = input_data.get("message", "Work the collections queue — fetch aging AR, score all overdue accounts, draft emails, escalate, and update statuses.")
    if STRANDS_AVAILABLE:
        response = agent(message)
        return {"result": str(response)}
    return {"result": "Strands not available — use lambda_handler for Action Group mode"}


if __name__ == "__main__":
    import sys
    data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Run the daily collections workflow: fetch aging AR, score all overdue accounts, draft and send collection emails, escalate high-risk accounts, and update statuses."
    }
    print(json.dumps(run(data)))
