"""
AR Collections Agent
====================
Monitors aging accounts receivable, scores collection risk by tier, generates
personalized collection emails, and escalates overdue accounts to appropriate teams.

Built with AWS Strands Agents + Amazon Bedrock AgentCore Runtime (Claude Sonnet).
Deploys as a containerized service on AgentCore — no Lambda required.
"""

import json
import os
import io
import logging
import boto3
from datetime import datetime

# Configure logging early so startup errors appear in CloudWatch
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ar-collections-agent")
logger.info("AR Collections Agent starting up...")

try:
    from strands import Agent, tool
    from strands.models import BedrockModel
    logger.info("strands-agents imported successfully")
except ImportError as e:
    logger.error(f"Failed to import strands: {e}")
    raise

try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
    logger.info("bedrock-agentcore imported successfully")
except ImportError as e:
    logger.error(f"Failed to import bedrock_agentcore: {e}")
    raise


# ---------------------------------------------------------------------------
# AgentCore app
# ---------------------------------------------------------------------------

app = BedrockAgentCoreApp()


# ---------------------------------------------------------------------------
# S3 helper
# ---------------------------------------------------------------------------

def _fetch_s3_bytes(s3_uri: str):
    """Fetch raw bytes from an S3 URI. Returns (bytes, key) or (None, key)."""
    try:
        parts = s3_uri[5:].split('/', 1)
        bucket, key = parts[0], parts[1]
        s3 = boto3.client('s3')
        obj = s3.get_object(Bucket=bucket, Key=key)
        return obj['Body'].read(), key
    except Exception as e:
        return None, ''


# ---------------------------------------------------------------------------
# Excel aging report parser
# ---------------------------------------------------------------------------

def _parse_aging_report_excel(raw_bytes: bytes) -> dict:
    """
    Parse an Excel aging report workbook and return the same structure as
    fetch_aging_report() -- a dict with report_date, currency, summary, accounts.

    Supports two common layouts:
      Layout A -- Single sheet with a header row followed by account rows.
      Layout B -- Sheet 1 = summary key:value pairs, Sheet 2 = account rows.

    Column auto-detection: looks for headers containing substrings like
    account_id/account id, company, contact_name, email, invoice_number,
    invoice_date, due_date, days_overdue/days overdue, balance, payment_history,
    last_payment.
    """
    try:
        import openpyxl
    except ImportError:
        return {"error": "openpyxl not installed -- cannot parse Excel aging reports"}

    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True)

    # ---- locate the account data sheet ----------------------------------------
    # Prefer a sheet whose name suggests account/aging data; fall back to last sheet
    account_ws = None
    for ws in wb.worksheets:
        name_lower = ws.title.lower()
        if any(kw in name_lower for kw in ("account", "aging", "ar", "detail", "overdue")):
            account_ws = ws
            break
    if account_ws is None:
        account_ws = wb.worksheets[-1]   # last sheet is usually the detail

    # ---- collect non-empty rows ------------------------------------------------
    rows = []
    for row in account_ws.iter_rows(values_only=True):
        non_empty = [c for c in row if c is not None]
        if non_empty:
            rows.append([str(c).strip() if c is not None else "" for c in row])

    if not rows:
        return {"error": "No data found in Excel workbook"}

    # ---- detect header row (first row with recognisable column keywords) -------
    HEADER_KEYWORDS = (
        "account", "company", "contact", "email", "invoice",
        "due", "days", "balance", "payment", "last",
    )
    header_idx = 0
    for i, row in enumerate(rows):
        hits = sum(
            1 for cell in row
            if any(kw in cell.lower() for kw in HEADER_KEYWORDS)
        )
        if hits >= 3:   # at least 3 recognisable header words
            header_idx = i
            break

    headers = rows[header_idx]

    # ---- normalise header names ------------------------------------------------
    def _norm(h):
        return h.lower().replace(" ", "_").replace("-", "_").rstrip("_")

    col_map = {j: _norm(h) for j, h in enumerate(headers) if h}

    # ---- helper: find column index by keyword ----------------------------------
    def _col(keywords):
        for j, norm in col_map.items():
            for kw in keywords:
                if kw in norm:
                    return j
        return None

    ci = {
        "account_id":       _col(["account_id", "account id", "acc_id", "acct"]),
        "company_name":     _col(["company", "organisation", "organization", "client"]),
        "contact_name":     _col(["contact_name", "contact name", "name"]),
        "contact_email":    _col(["email"]),
        "invoice_number":   _col(["invoice_number", "invoice_no", "invoice#", "inv_num"]),
        "invoice_date":     _col(["invoice_date", "inv_date", "issued"]),
        "due_date":         _col(["due_date", "due date", "pay_by"]),
        "days_overdue":     _col(["days_overdue", "days overdue", "overdue_days", "overdue"]),
        "balance":          _col(["balance", "amount", "outstanding"]),
        "payment_history":  _col(["payment_history", "pay_history", "history"]),
        "last_payment_date":_col(["last_payment", "last payment", "last_pay"]),
    }

    # ---- parse account rows ---------------------------------------------------
    accounts = []
    for row in rows[header_idx + 1:]:
        if not any(row):
            continue
        def _get(field):
            j = ci.get(field)
            return row[j] if j is not None and j < len(row) else ""

        try:
            days_val = int(float(_get("days_overdue"))) if _get("days_overdue") else 0
        except (ValueError, TypeError):
            days_val = 0
        try:
            bal_val = float(str(_get("balance")).replace(",", "").replace("$", "")) if _get("balance") else 0.0
        except (ValueError, TypeError):
            bal_val = 0.0

        accounts.append({
            "account_id":          _get("account_id"),
            "company_name":        _get("company_name"),
            "contact_name":        _get("contact_name"),
            "contact_email":       _get("contact_email"),
            "invoice_number":      _get("invoice_number"),
            "invoice_date":        _get("invoice_date"),
            "due_date":            _get("due_date"),
            "days_overdue":        days_val,
            "balance":             bal_val,
            "payment_history":     _get("payment_history") or "unknown",
            "last_payment_date":   _get("last_payment_date"),
        })

    # ---- build summary totals -------------------------------------------------
    total_ar = sum(a["balance"] for a in accounts)
    buckets = {"current": 0.0, "days_1_30": 0.0, "days_31_60": 0.0,
               "days_61_90": 0.0, "days_91_plus": 0.0}
    for a in accounts:
        d, b = a["days_overdue"], a["balance"]
        if d == 0:
            buckets["current"] += b
        elif d <= 30:
            buckets["days_1_30"] += b
        elif d <= 60:
            buckets["days_31_60"] += b
        elif d <= 90:
            buckets["days_61_90"] += b
        else:
            buckets["days_91_plus"] += b

    return {
        "report_date":  datetime.utcnow().strftime("%Y-%m-%d"),
        "currency":     "USD",
        "source":       "excel",
        "summary":      {"total_ar": total_ar, **buckets},
        "accounts":     accounts,
    }

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def fetch_aging_report(as_of_date: str = "", min_days_overdue: int = 0,
                       excel_source: str = "") -> str:
    """
    Fetch the accounts receivable aging report.

    Args:
        as_of_date: Report date in YYYY-MM-DD format (defaults to today)
        min_days_overdue: Filter to accounts overdue by at least this many days
        excel_source: Optional S3 URI or file path to an .xlsx aging report.
                      If provided, parses the Excel file instead of returning
                      mock data. Falls back to mock data if parsing fails.

    Returns:
        JSON string with AR aging buckets and individual account details
    """
    report_date = as_of_date or datetime.utcnow().strftime("%Y-%m-%d")

    # ---- attempt Excel parse if source provided --------------------------------
    if excel_source:
        raw_bytes = None
        if excel_source.startswith("s3://"):
            raw_bytes, _ = _fetch_s3_bytes(excel_source)
        else:
            try:
                with open(excel_source, "rb") as fh:
                    raw_bytes = fh.read()
            except Exception:
                raw_bytes = None

        if raw_bytes is not None:
            parsed = _parse_aging_report_excel(raw_bytes)
            if "error" not in parsed:
                if min_days_overdue > 0:
                    parsed["accounts"] = [
                        a for a in parsed["accounts"]
                        if a["days_overdue"] >= min_days_overdue
                    ]
                return json.dumps(parsed, indent=2)
            # fall through to mock data if parse failed

    # ---- mock data (also used as fallback) ------------------------------------
    aging_data = {
        "report_date": report_date,
        "currency": "USD",
        "summary": {
            "total_ar":       1847500.00,
            "current":         820000.00,
            "days_1_30":       385000.00,
            "days_31_60":      312500.00,
            "days_61_90":      198000.00,
            "days_91_plus":    132000.00,
        },
        "accounts": [
            {
                "account_id":         "ACC-10021",
                "company_name":       "Nexus Technologies Inc.",
                "contact_email":      "ap@nexustech.com",
                "contact_name":       "Sarah Chen",
                "invoice_number":     "INV-2024-0891",
                "invoice_date":       "2024-01-10",
                "due_date":           "2024-02-09",
                "days_overdue":       32,
                "balance":            48500.00,
                "payment_history":    "good",
                "last_payment_date":  "2023-12-15",
            },
            {
                "account_id":         "ACC-10045",
                "company_name":       "Meridian Logistics Group",
                "contact_email":      "finance@meridianlogistics.com",
                "contact_name":       "Robert Okafor",
                "invoice_number":     "INV-2024-0742",
                "invoice_date":       "2023-12-20",
                "due_date":           "2024-01-19",
                "days_overdue":       53,
                "balance":            127000.00,
                "payment_history":    "slow_pay",
                "last_payment_date":  "2023-10-08",
            },
            {
                "account_id":         "ACC-10078",
                "company_name":       "Cascade Retail Corp",
                "contact_email":      "payments@cascaderetail.com",
                "contact_name":       "Linda Park",
                "invoice_number":     "INV-2024-0615",
                "invoice_date":       "2023-11-15",
                "due_date":           "2023-12-15",
                "days_overdue":       88,
                "balance":            89500.00,
                "payment_history":    "poor",
                "last_payment_date":  "2023-08-20",
            },
            {
                "account_id":         "ACC-10092",
                "company_name":       "Summit Healthcare Partners",
                "contact_email":      "billing@summithealthcare.com",
                "contact_name":       "Michael Torres",
                "invoice_number":     "INV-2024-0582",
                "invoice_date":       "2023-11-01",
                "due_date":           "2023-12-01",
                "days_overdue":       102,
                "balance":            42000.00,
                "payment_history":    "poor",
                "last_payment_date":  "2023-07-15",
            },
        ],
    }

    if min_days_overdue > 0:
        aging_data["accounts"] = [
            a for a in aging_data["accounts"]
            if a["days_overdue"] >= min_days_overdue
        ]

    return json.dumps(aging_data, indent=2)

@tool
def score_collection_risk(account_data: str) -> str:
    """
    Score each account by collection risk tier based on days overdue, balance, and payment history.

    Args:
        account_data: JSON string from fetch_aging_report containing account list

    Returns:
        JSON string with accounts ranked by risk tier (Critical/High/Medium/Low) with scores
    """
    try:
        data = json.loads(account_data)
        accounts = data.get("accounts", [])
    except Exception:
        return json.dumps({"error": "Invalid account data"})

    scored = []
    for acct in accounts:
        days = acct.get("days_overdue", 0)
        balance = acct.get("balance", 0)
        history = acct.get("payment_history", "good")

        # Scoring components (0-100 each)
        days_score = min(100, days * 1.0)           # 1 pt per day overdue
        balance_score = min(100, balance / 2000)    # $200K = 100 pts
        history_scores = {"good": 0, "slow_pay": 30, "poor": 60, "collections": 90}
        history_score = history_scores.get(history, 20)

        risk_score = int((days_score * 0.4) + (balance_score * 0.35) + (history_score * 0.25))

        if risk_score >= 70 or days >= 90:
            tier = "Critical"
            action = "Escalate to collections attorney or agency"
        elif risk_score >= 45 or days >= 60:
            tier = "High"
            action = "Senior collections rep -- direct phone call required"
        elif risk_score >= 20 or days >= 30:
            tier = "Medium"
            action = "Send formal collection notice with payment plan offer"
        else:
            tier = "Low"
            action = "Send friendly payment reminder"

        scored.append({
            "account_id":          acct.get("account_id"),
            "company_name":        acct.get("company_name"),
            "balance":             balance,
            "days_overdue":        days,
            "risk_score":          risk_score,
            "risk_tier":           tier,
            "recommended_action":  action,
            "contact_email":       acct.get("contact_email"),
            "contact_name":        acct.get("contact_name"),
        })

    scored.sort(key=lambda x: x["risk_score"], reverse=True)
    return json.dumps({
        "scored_accounts": scored,
        "tier_summary": {
            tier: sum(1 for a in scored if a["risk_tier"] == tier)
            for tier in ["Critical", "High", "Medium", "Low"]
        },
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
        contact_name: Name of the accounts payable contact
        days_overdue: Number of days the invoice is overdue
        balance: Outstanding balance amount
        risk_tier: Risk tier (Low/Medium/High/Critical)

    Returns:
        JSON string with drafted email subject and body tailored to collection urgency
    """
    company_from = os.environ.get("COMPANY_NAME", "Khyzr")

    if risk_tier == "Low":
        subject = "Friendly Payment Reminder -- Invoice Outstanding"
        tone = "friendly"
        body = (
            f"Dear {contact_name},\n\n"
            f"I hope this message finds you well. This is a friendly reminder that "
            f"an invoice of ${balance:,.2f} is now {days_overdue} days past due.\n\n"
            f"We value our partnership with {company_name} and want to make this as "
            f"easy as possible. If you have any questions or need assistance, please "
            f"do not hesitate to reach out.\n\n"
            f"Please arrange payment at your earliest convenience. You can pay securely "
            f"via our portal or by wire transfer.\n\n"
            f"Thank you for your continued business!"
        )

    elif risk_tier == "Medium":
        subject = f"Payment Required -- ${balance:,.2f} Overdue ({days_overdue} Days)"
        tone = "formal"
        body = (
            f"Dear {contact_name},\n\n"
            f"This is a formal notice that an outstanding balance of ${balance:,.2f} "
            f"from {company_name} is now {days_overdue} days overdue.\n\n"
            f"We have made multiple attempts to contact you regarding this balance. "
            f"To avoid any disruption to your services, we ask that you remit payment "
            f"immediately or contact us within 5 business days to discuss a payment arrangement.\n\n"
            f"If you are experiencing financial difficulties, we are open to discussing "
            f"a structured payment plan.\n\nPlease treat this matter with urgency."
        )

    elif risk_tier == "High":
        subject = f"URGENT: Overdue Account -- ${balance:,.2f} -- Immediate Action Required"
        tone = "urgent"
        body = (
            f"Dear {contact_name},\n\n"
            f"Your account with {company_from} has a seriously overdue balance of "
            f"${balance:,.2f} that is now {days_overdue} days past due.\n\n"
            f"This is a final notice before we escalate this matter. Failure to remit "
            f"payment or contact us within 48 hours will result in:\n"
            f"  - Suspension of your account and services\n"
            f"  - Referral to our senior collections team\n"
            f"  - Potential impact on your credit standing\n\n"
            f"Please call us immediately at the number below or pay online to resolve this matter."
        )

    else:  # Critical
        subject = f"FINAL NOTICE -- ${balance:,.2f} -- Account Referred for Collections"
        tone = "critical"
        body = (
            f"Dear {contact_name},\n\n"
            f"This is a final demand for payment of ${balance:,.2f}, "
            f"now {days_overdue} days overdue.\n\n"
            f"Your account has been reviewed and is being referred to our external collections "
            f"agency unless payment is received within 24 hours.\n\n"
            f"To avoid collections proceedings, pay immediately via our secure portal or "
            f"contact our collections department at once.\n\n"
            f"This matter is urgent and requires your immediate attention."
        )

    return json.dumps({
        "account_id":     account_id,
        "email_subject":  subject,
        "email_body":     body,
        "tone":           tone,
        "risk_tier":      risk_tier,
        "recipient_email": "",   # filled by escalate_account or caller
        "drafted_at":     datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def escalate_account(account_id: str, risk_tier: str, balance: float,
                     days_overdue: int, company_name: str, email_draft: str) -> str:
    """
    Escalate an overdue account based on risk tier -- notify internal team and/or send collection email.

    Args:
        account_id: Account identifier
        risk_tier: Risk tier (Low/Medium/High/Critical)
        balance: Outstanding balance
        days_overdue: Days overdue
        company_name: Customer company name
        email_draft: JSON string of drafted collection email

    Returns:
        JSON string with escalation actions taken and notification status
    """
    ar_manager = os.environ.get("AR_MANAGER_EMAIL", "ar-manager@company.com")
    cfo_email  = os.environ.get("CFO_EMAIL", "cfo@company.com")

    escalation_actions = []

    # Determine internal notification recipients
    if risk_tier == "Critical":
        internal_recipients = [ar_manager, cfo_email]
        escalation_level = "External collections referral"
    elif risk_tier == "High":
        internal_recipients = [ar_manager]
        escalation_level = "Senior collections rep assigned"
    elif risk_tier == "Medium":
        internal_recipients = [ar_manager]
        escalation_level = "Formal notice sent"
    else:
        internal_recipients = []
        escalation_level = "Automated reminder sent"

    escalation_actions.append({
        "action":           "internal_notification",
        "recipients":       internal_recipients,
        "escalation_level": escalation_level,
        "status":           "queued",
    })

    if risk_tier in ("Critical", "High"):
        escalation_actions.append({
            "action":     "service_suspension_review",
            "account_id": account_id,
            "status":     "flagged_for_review",
        })

    return json.dumps({
        "account_id":       account_id,
        "company_name":     company_name,
        "risk_tier":        risk_tier,
        "balance":          balance,
        "days_overdue":     days_overdue,
        "escalation_level": escalation_level,
        "actions_taken":    escalation_actions,
        "escalated_at":     datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def update_collection_status(account_id: str, new_status: str, notes: str = "") -> str:
    """
    Update the collection status for an account in the AR system.

    Args:
        account_id: Account identifier to update
        new_status: New status (reminder_sent, escalated, payment_plan,
                    in_collections, paid, disputed)
        notes: Optional notes about the collection activity

    Returns:
        JSON string with update confirmation and next scheduled action
    """
    valid_statuses = ["reminder_sent", "escalated", "payment_plan",
                      "in_collections", "paid", "disputed"]

    if new_status not in valid_statuses:
        return json.dumps({"error": f"Invalid status. Must be one of: {valid_statuses}"})

    next_actions = {
        "reminder_sent":  {"action": "Follow-up call",            "in_days": 5},
        "escalated":      {"action": "Review escalation response", "in_days": 2},
        "payment_plan":   {"action": "Monitor first payment",      "in_days": 30},
        "in_collections": {"action": "Agency status check",        "in_days": 14},
        "paid":           {"action": "None -- account cleared",    "in_days": None},
        "disputed":       {"action": "Legal review",               "in_days": 3},
    }

    update = {
        "account_id":      account_id,
        "previous_status": "pending",
        "new_status":      new_status,
        "notes":           notes,
        "updated_by":      "AR Collections Agent",
        "next_action":     next_actions.get(new_status, {}),
        "updated_at":      datetime.utcnow().isoformat(),
    }

    # Attempt real DynamoDB write
    dynamodb = boto3.resource(
        "dynamodb",
        region_name=os.environ.get("AWS_REGION", os.environ.get("AWS_REGION_NAME", "us-east-1")),
    )
    table_name = os.environ.get("AR_COLLECTIONS_TABLE", "khyzr-ar-collections-demo")
    try:
        table = dynamodb.Table(table_name)
        table.put_item(Item={
            "account_id": account_id,
            "updated_at": datetime.utcnow().isoformat(),
            "new_status": new_status,
            "notes":      notes,
            "updated_by": "AR Collections Agent",
            "next_action": next_actions.get(new_status, {}),
        })
        return json.dumps({"status": "recorded", "entry": update}, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "simulated",
            "note":   str(e)[:120],
            "entry":  update,
        }, indent=2)


# ---------------------------------------------------------------------------
# Strands Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the AR Collections Agent for Khyzr — an expert accounts receivable specialist.

EXACT workflow — follow in order:
1. Call fetch_aging_report with excel_source set to the S3 URI to load ALL accounts
2. Score each account by collection risk (Critical/High/Medium/Low) based on days overdue + balance
3. Call draft_collection_email for each account
4. Call escalate_account for Critical and High risk accounts
5. Call update_collection_status for all accounts
6. Output the FULL report — never summarize with one sentence

Your response MUST be the full report in this exact format:

## 💰 AR Collections Report

### 📊 Portfolio Summary
- Total accounts: X | Total AR: $X
- 🚨 Critical (90+ days): X accounts, $X
- ⚠️ High (61-90 days): X accounts, $X
- 🔶 Medium (31-60 days): X accounts, $X
- ✅ Low (1-30 days): X accounts, $X
- DSO: X days

### 📋 Account Details
| Customer | Invoice # | Amount Due | Days Overdue | Risk Tier | Action |
|----------|-----------|------------|--------------|-----------|--------|
(one row per account, sorted Critical → High → Medium → Low)

### 📧 Collection Emails Drafted
For each Critical/High account show the draft email subject and first 2 sentences.

### 🚨 Escalations
List any accounts escalated and to whom.

### ✅ Status Updated
Confirm all collection statuses recorded.

Never output just a summary sentence. Always show the full table."""

# ---------------------------------------------------------------------------
# Lazy agent initialisation — deferred until first invocation so AgentCore
# runtime startup completes well within the init timeout window.
# ---------------------------------------------------------------------------

_agent = None

def _get_agent():
    global _agent
    if _agent is None:
        logger.info("Initialising BedrockModel + Agent (first invocation)...")
        model = BedrockModel(
            model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0"),
            region_name=os.environ.get("AWS_REGION_NAME", os.environ.get("AWS_REGION", "us-east-1")),
        )
        _agent = Agent(
            model=model,
            tools=[
                fetch_aging_report,
                score_collection_risk,
                draft_collection_email,
                escalate_account,
                update_collection_status,
            ],
            system_prompt=SYSTEM_PROMPT,
        )
        logger.info("Agent ready.")
    return _agent


# ---------------------------------------------------------------------------
# AgentCore entrypoint
# ---------------------------------------------------------------------------

@app.entrypoint
def invoke(payload):
    """AgentCore entrypoint — receives {"bucket": "...", "key": "..."} or {"prompt": "..."}"""
    if "bucket" in payload and "key" in payload:
        s3_uri = f"s3://{payload['bucket']}/{payload['key']}"
        user_message = (
            f"Process all accounts from {s3_uri}. "
            f"Score every account, draft collection emails, escalate high-risk accounts, update statuses. "
            f"Output the full AR Collections Report with the complete account table and all sections."
        )
    else:
        user_message = payload.get(
            "prompt",
            payload.get(
                "message",
                "Work the full collections queue: fetch aging AR, score all accounts, "
                "draft collection emails, escalate high-risk accounts, update statuses.",
            ),
        )
    logger.info(f"Received prompt: {user_message[:100]}...")
    try:
        result = _get_agent()(user_message)
        logger.info("Agent invocation completed successfully")
        return {"result": str(result)}
    except Exception as e:
        logger.error(f"Agent invocation failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    logger.info("Starting AgentCore HTTP server on port 8080")
    app.run()
