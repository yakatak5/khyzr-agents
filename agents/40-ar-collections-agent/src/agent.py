"""
AR Collections Agent
====================
Monitors aging accounts receivable, scores collection risk by tier, generates
personalized collection emails, and escalates overdue accounts to appropriate teams.

Built with AWS Strands Agents + AgentCore on AWS Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def fetch_aging_report(as_of_date: str = "", min_days_overdue: int = 0) -> str:
    """
    Fetch the accounts receivable aging report from the billing system.

    Args:
        as_of_date: Report date in YYYY-MM-DD format (defaults to today)
        min_days_overdue: Filter to accounts overdue by at least this many days

    Returns:
        JSON string with AR aging buckets and individual account details
    """
    report_date = as_of_date or datetime.utcnow().strftime("%Y-%m-%d")

    # In production: queries billing system (Stripe, QuickBooks, NetSuite)
    aging_data = {
        "report_date": report_date,
        "currency": "USD",
        "summary": {
            "total_ar": 1847500.00,
            "current": 820000.00,
            "days_1_30": 385000.00,
            "days_31_60": 312500.00,
            "days_61_90": 198000.00,
            "days_91_plus": 132000.00,
        },
        "accounts": [
            {
                "account_id": "ACC-10021",
                "company_name": "Nexus Technologies Inc.",
                "contact_email": "ap@nexustech.com",
                "contact_name": "Sarah Chen",
                "invoice_number": "INV-2024-0891",
                "invoice_date": "2024-01-10",
                "due_date": "2024-02-09",
                "days_overdue": 32,
                "balance": 48500.00,
                "payment_history": "good",
                "last_payment_date": "2023-12-15",
            },
            {
                "account_id": "ACC-10045",
                "company_name": "Meridian Logistics Group",
                "contact_email": "finance@meridianlogistics.com",
                "contact_name": "Robert Okafor",
                "invoice_number": "INV-2024-0742",
                "invoice_date": "2023-12-20",
                "due_date": "2024-01-19",
                "days_overdue": 53,
                "balance": 127000.00,
                "payment_history": "slow_pay",
                "last_payment_date": "2023-10-08",
            },
            {
                "account_id": "ACC-10078",
                "company_name": "Cascade Retail Corp",
                "contact_email": "payments@cascaderetail.com",
                "contact_name": "Linda Park",
                "invoice_number": "INV-2024-0615",
                "invoice_date": "2023-11-15",
                "due_date": "2023-12-15",
                "days_overdue": 88,
                "balance": 89500.00,
                "payment_history": "poor",
                "last_payment_date": "2023-08-20",
            },
            {
                "account_id": "ACC-10092",
                "company_name": "Summit Healthcare Partners",
                "contact_email": "billing@summithealthcare.com",
                "contact_name": "Michael Torres",
                "invoice_number": "INV-2024-0582",
                "invoice_date": "2023-11-01",
                "due_date": "2023-12-01",
                "days_overdue": 102,
                "balance": 42000.00,
                "payment_history": "poor",
                "last_payment_date": "2023-07-15",
            },
        ],
    }

    if min_days_overdue > 0:
        aging_data["accounts"] = [
            a for a in aging_data["accounts"] if a["days_overdue"] >= min_days_overdue
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
        days_score = min(100, days * 1.0)  # 1pt per day
        balance_score = min(100, balance / 2000)  # $200K = 100pts
        history_scores = {"good": 0, "slow_pay": 30, "poor": 60, "collections": 90}
        history_score = history_scores.get(history, 20)

        risk_score = int((days_score * 0.4) + (balance_score * 0.35) + (history_score * 0.25))

        if risk_score >= 70 or days >= 90:
            tier = "Critical"
            action = "Escalate to collections attorney or agency"
        elif risk_score >= 45 or days >= 60:
            tier = "High"
            action = "Senior collections rep — direct phone call required"
        elif risk_score >= 20 or days >= 30:
            tier = "Medium"
            action = "Send formal collection notice with payment plan offer"
        else:
            tier = "Low"
            action = "Send friendly payment reminder"

        scored.append({
            "account_id": acct.get("account_id"),
            "company_name": acct.get("company_name"),
            "balance": balance,
            "days_overdue": days,
            "risk_score": risk_score,
            "risk_tier": tier,
            "recommended_action": action,
            "contact_email": acct.get("contact_email"),
            "contact_name": acct.get("contact_name"),
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
    sender_name = os.environ.get("AR_CONTACT_NAME", "Accounts Receivable Team")
    company_from = os.environ.get("COMPANY_NAME", "Khyzr")

    if risk_tier == "Low":
        subject = f"Friendly Payment Reminder — Invoice Outstanding"
        tone = "friendly"
        body = f"""Dear {contact_name},

I hope this message finds you well. This is a friendly reminder that an invoice of ${balance:,.2f} is now {days_overdue} days past due.

We value our partnership with {company_name} and want to make this as easy as possible. If you have any questions or need assistance, please don't hesitate to reach out.

Please arrange payment at your earliest convenience. You can pay securely via our portal or by wire transfer.

Thank you for your continued business!"""

    elif risk_tier == "Medium":
        subject = f"Payment Required — ${balance:,.2f} Overdue ({days_overdue} Days)"
        tone = "formal"
        body = f"""Dear {contact_name},

This is a formal notice that an outstanding balance of ${balance:,.2f} from {company_name} is now {days_overdue} days overdue.

We have made multiple attempts to contact you regarding this balance. To avoid any disruption to your services, we ask that you remit payment immediately or contact us within 5 business days to discuss a payment arrangement.

If you are experiencing financial difficulties, we are open to discussing a structured payment plan.

Please treat this matter with urgency."""

    elif risk_tier == "High":
        subject = f"URGENT: Overdue Account — ${balance:,.2f} — Immediate Action Required"
        tone = "urgent"
        body = f"""Dear {contact_name},

Your account with {company_from} has a seriously overdue balance of ${balance:,.2f} that is now {days_overdue} days past due.

This is a final notice before we escalate this matter. Failure to remit payment or contact us within 48 hours will result in:
• Suspension of your account and services
• Referral to our senior collections team
• Potential impact on your credit standing

Please call us immediately at the number below or pay online to resolve this matter."""

    else:  # Critical
        subject = f"FINAL NOTICE — ${balance:,.2f} — Account Referred for Collections"
        tone = "critical"
        body = f"""Dear {contact_name},

This is a final demand for payment of ${balance:,.2f}, now {days_overdue} days overdue.

Your account has been reviewed and is being referred to our external collections agency unless payment is received within 24 hours.

To avoid collections proceedings, pay immediately via our secure portal or contact our collections department at once.

This matter is urgent and requires your immediate attention."""

    return json.dumps({
        "account_id": account_id,
        "email_subject": subject,
        "email_body": body,
        "tone": tone,
        "risk_tier": risk_tier,
        "recipient_email": "",  # filled by escalate_account or caller
        "drafted_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def escalate_account(account_id: str, risk_tier: str, balance: float,
                     days_overdue: int, company_name: str, email_draft: str) -> str:
    """
    Escalate an overdue account based on risk tier — notify internal team and/or send collection email.

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
    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    ar_manager = os.environ.get("AR_MANAGER_EMAIL", "ar-manager@company.com")
    cfo_email = os.environ.get("CFO_EMAIL", "cfo@company.com")

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
        "action": "internal_notification",
        "recipients": internal_recipients,
        "escalation_level": escalation_level,
        "status": "queued",
    })

    if risk_tier in ("Critical", "High"):
        escalation_actions.append({
            "action": "service_suspension_review",
            "account_id": account_id,
            "status": "flagged_for_review",
        })

    return json.dumps({
        "account_id": account_id,
        "company_name": company_name,
        "risk_tier": risk_tier,
        "balance": balance,
        "days_overdue": days_overdue,
        "escalation_level": escalation_level,
        "actions_taken": escalation_actions,
        "escalated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def update_collection_status(account_id: str, new_status: str, notes: str = "") -> str:
    """
    Update the collection status for an account in the AR system.

    Args:
        account_id: Account identifier to update
        new_status: New status (reminder_sent, escalated, payment_plan, in_collections, paid)
        notes: Optional notes about the collection activity

    Returns:
        JSON string with update confirmation and next scheduled action
    """
    valid_statuses = ["reminder_sent", "escalated", "payment_plan", "in_collections", "paid", "disputed"]

    if new_status not in valid_statuses:
        return json.dumps({"error": f"Invalid status. Must be one of: {valid_statuses}"})

    next_actions = {
        "reminder_sent": {"action": "Follow-up call", "in_days": 5},
        "escalated": {"action": "Review escalation response", "in_days": 2},
        "payment_plan": {"action": "Monitor first payment", "in_days": 30},
        "in_collections": {"action": "Agency status check", "in_days": 14},
        "paid": {"action": "None — account cleared", "in_days": None},
        "disputed": {"action": "Legal review", "in_days": 3},
    }

    # In production: updates ERP/CRM database
    update = {
        "account_id": account_id,
        "previous_status": "pending",
        "new_status": new_status,
        "notes": notes,
        "updated_by": "AR Collections Agent",
        "next_action": next_actions.get(new_status, {}),
        "updated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(update, indent=2)


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the AR Collections Agent for Khyzr — an expert accounts receivable specialist with deep knowledge of collections best practices, cash flow management, and customer relationship preservation.

Your mission is to monitor the aging AR portfolio, score collection risk, generate personalized outreach, escalate overdue accounts appropriately, and update collection statuses to keep cash flowing.

When working the collections queue:
1. Fetch the aging AR report and identify accounts by overdue buckets (30/60/90/90+ days)
2. Score each account by collection risk tier (Critical/High/Medium/Low) based on:
   - Days overdue (most important factor)
   - Outstanding balance size
   - Payment history (good/slow-pay/poor)
3. Draft tier-appropriate collection emails for each account
4. Escalate accounts to appropriate personnel based on risk tier
5. Update collection status in the AR system with next action dates

Risk tier escalation framework:
- **Low (1-30 days, good history)**: Friendly automated reminder
- **Medium (31-60 days or slow-pay)**: Formal notice + payment plan offer
- **High (61-90 days or large balance)**: Senior collector + direct call
- **Critical (90+ days or poor history)**: External collections agency consideration

Collections strategy principles:
- Preserve customer relationships wherever possible — most late payments are cash flow issues, not bad faith
- Always offer payment plans before threatening collections referral
- Prioritize by dollar value × risk score (impact-weighted)
- Maintain complete audit trail of all collection activities

Cash flow impact: Flag 🚨 any single account where overdue balance exceeds $100K. Monitor total DSO (Days Sales Outstanding) — target <45 days. Alert finance if DSO exceeds 60 days.

Your tone adapts to the situation: warm for Low-risk, professional for Medium, firm for High, and unambiguous for Critical. Every communication should motivate prompt payment while leaving the relationship intact where possible."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
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


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Work the collections queue — identify all overdue accounts, score risk, and send appropriate outreach")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Run the daily collections workflow: fetch aging AR, score all overdue accounts, draft and send collection emails, escalate high-risk accounts, and update statuses."
    }
    print(json.dumps(run(input_data)))
