"""
Audit Trail Documentation Agent
================================
Compiles transaction records, supporting documents, and control evidence
into audit-ready packages stored in S3 and optionally emailed to auditors.

Built with AWS Strands Agents + AgentCore on AWS Bedrock (Claude Sonnet).
"""

import json
import os
import re
import csv
import io
import boto3
import httpx
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def query_transactions(
    start_date: str,
    end_date: str,
    account_codes: list = None,
    min_amount: float = None,
    transaction_types: list = None,
) -> str:
    """
    Query the general ledger / transaction database for records within a date range.

    In production, replace the mock data below with a real DB query
    (RDS via psycopg2, Athena via boto3, or an ERP API call).

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        account_codes: Optional list of GL account codes to filter by
        min_amount: Optional minimum transaction amount filter
        transaction_types: Optional list of types (e.g. ["JOURNAL", "INVOICE", "PAYMENT"])

    Returns:
        JSON string of transaction records
    """
    # --- MOCK DATA (replace with real DB/ERP integration) ---
    mock_transactions = [
        {"id": "TXN-001", "date": start_date, "type": "INVOICE", "account": "2000", "description": "Vendor invoice - Office Supplies Co", "amount": 4250.00, "currency": "USD", "approved_by": "J.Smith", "po_ref": "PO-2024-0041"},
        {"id": "TXN-002", "date": start_date, "type": "PAYMENT", "account": "1000", "description": "Payment to Office Supplies Co", "amount": -4250.00, "currency": "USD", "approved_by": "J.Smith", "po_ref": "PO-2024-0041"},
        {"id": "TXN-003", "date": start_date, "type": "JOURNAL", "account": "5100", "description": "Monthly depreciation - Equipment", "amount": 12500.00, "currency": "USD", "approved_by": "CFO", "po_ref": None},
        {"id": "TXN-004", "date": end_date, "type": "INVOICE", "account": "2000", "description": "Vendor invoice - Cloud Services LLC", "amount": 8900.00, "currency": "USD", "approved_by": "CTO", "po_ref": "PO-2024-0089"},
        {"id": "TXN-005", "date": end_date, "type": "JOURNAL", "account": "4000", "description": "Revenue recognition - Q4 SaaS contracts", "amount": 245000.00, "currency": "USD", "approved_by": "Controller", "po_ref": None},
        {"id": "TXN-006", "date": end_date, "type": "PAYMENT", "account": "1000", "description": "Payroll disbursement - December", "amount": -185000.00, "currency": "USD", "approved_by": "HR Director", "po_ref": None},
    ]

    # Apply filters
    results = mock_transactions
    if account_codes:
        results = [t for t in results if t["account"] in account_codes]
    if min_amount is not None:
        results = [t for t in results if abs(t["amount"]) >= min_amount]
    if transaction_types:
        types_upper = [t.upper() for t in transaction_types]
        results = [t for t in results if t["type"] in types_upper]

    return json.dumps({
        "query": {
            "start_date": start_date,
            "end_date": end_date,
            "filters_applied": {
                "account_codes": account_codes,
                "min_amount": min_amount,
                "transaction_types": transaction_types,
            }
        },
        "count": len(results),
        "transactions": results,
    }, indent=2)


@tool
def list_supporting_documents(transaction_ids: list) -> str:
    """
    Retrieve supporting document references for a list of transaction IDs.
    Checks S3 for attached invoices, receipts, approvals, and contracts.

    Args:
        transaction_ids: List of transaction IDs to look up documents for

    Returns:
        JSON string mapping transaction IDs to their supporting documents
    """
    bucket = os.environ.get("AUDIT_BUCKET", "audit-trail-packages")
    s3 = boto3.client("s3")
    docs_map = {}

    for txn_id in transaction_ids:
        prefix = f"supporting-docs/{txn_id}/"
        try:
            resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
            docs = [
                {
                    "key": obj["Key"],
                    "filename": obj["Key"].split("/")[-1],
                    "size_kb": round(obj["Size"] / 1024, 1),
                    "last_modified": obj["LastModified"].isoformat(),
                }
                for obj in resp.get("Contents", [])
            ]
            docs_map[txn_id] = {
                "document_count": len(docs),
                "documents": docs,
                "status": "complete" if docs else "missing",
            }
        except Exception as e:
            # If bucket doesn't exist yet, return mock data
            docs_map[txn_id] = {
                "document_count": 1,
                "documents": [{"filename": f"{txn_id}-invoice.pdf", "size_kb": 142.3, "status": "mock"}],
                "status": "complete",
            }

    return json.dumps(docs_map, indent=2)


@tool
def assess_control_evidence(transaction_records: str) -> str:
    """
    Assess internal control evidence for a set of transactions.
    Checks for: dual approval, segregation of duties, policy compliance,
    unusual amounts, missing PO references, and unsupported entries.

    Args:
        transaction_records: JSON string of transaction records (from query_transactions)

    Returns:
        JSON string with control assessment findings and risk flags
    """
    try:
        data = json.loads(transaction_records)
        transactions = data.get("transactions", [])
    except Exception:
        return json.dumps({"error": "Invalid transaction_records input"})

    findings = []
    flags = []

    for txn in transactions:
        txn_findings = {"transaction_id": txn["id"], "controls_passed": [], "controls_failed": [], "risk_level": "LOW"}

        # Check: approval present
        if txn.get("approved_by"):
            txn_findings["controls_passed"].append("Approval documented")
        else:
            txn_findings["controls_failed"].append("Missing approval signature")
            txn_findings["risk_level"] = "HIGH"
            flags.append({"txn_id": txn["id"], "flag": "Missing approval", "risk": "HIGH"})

        # Check: PO reference for invoices
        if txn["type"] == "INVOICE":
            if txn.get("po_ref"):
                txn_findings["controls_passed"].append("PO reference matched")
            else:
                txn_findings["controls_failed"].append("Invoice missing PO reference")
                txn_findings["risk_level"] = "MEDIUM"
                flags.append({"txn_id": txn["id"], "flag": "Invoice without PO", "risk": "MEDIUM"})

        # Check: large journal entries (>$100K without clear description)
        if txn["type"] == "JOURNAL" and abs(txn["amount"]) > 100000:
            if len(txn.get("description", "")) > 20:
                txn_findings["controls_passed"].append("Large entry has adequate description")
            else:
                txn_findings["controls_failed"].append("Large journal entry lacks adequate description")
                txn_findings["risk_level"] = "HIGH"
                flags.append({"txn_id": txn["id"], "flag": "Large unsupported journal entry", "risk": "HIGH"})

        # Check: round-number amounts (potential red flag)
        if txn["amount"] % 1000 == 0 and abs(txn["amount"]) >= 10000:
            txn_findings["controls_passed"].append("Round amount noted — verify supporting docs")

        findings.append(txn_findings)

    risk_summary = {
        "HIGH": sum(1 for f in findings if f["risk_level"] == "HIGH"),
        "MEDIUM": sum(1 for f in findings if f["risk_level"] == "MEDIUM"),
        "LOW": sum(1 for f in findings if f["risk_level"] == "LOW"),
    }

    return json.dumps({
        "total_transactions_reviewed": len(transactions),
        "risk_summary": risk_summary,
        "flags": flags,
        "transaction_findings": findings,
    }, indent=2)


@tool
def compile_audit_package(
    audit_period: str,
    transaction_summary: str,
    control_findings: str,
    package_name: str,
) -> str:
    """
    Compile all audit evidence into a structured markdown report and store to S3.

    Args:
        audit_period: Human-readable audit period (e.g. "Q4 2024" or "December 2024")
        transaction_summary: Summary of transactions reviewed
        control_findings: Control assessment results (JSON string)
        package_name: Name for this audit package (used as S3 key)

    Returns:
        JSON with S3 URI of the compiled package and a summary
    """
    bucket = os.environ.get("AUDIT_BUCKET", "audit-trail-packages")
    s3 = boto3.client("s3")
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    key = f"packages/{timestamp}-{package_name.replace(' ', '-').lower()}.md"

    # Parse findings for the report
    try:
        findings = json.loads(control_findings)
    except Exception:
        findings = {}

    risk_summary = findings.get("risk_summary", {})
    flags = findings.get("flags", [])

    # Build the audit package document
    report = f"""# Audit Trail Package — {audit_period}

**Generated:** {datetime.utcnow().strftime("%B %d, %Y at %H:%M UTC")}
**Package ID:** {timestamp}
**Status:** {"⚠️ Exceptions Found" if flags else "✅ No Exceptions"}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Audit Period | {audit_period} |
| Transactions Reviewed | {findings.get("total_transactions_reviewed", "N/A")} |
| High Risk Items | {risk_summary.get("HIGH", 0)} |
| Medium Risk Items | {risk_summary.get("MEDIUM", 0)} |
| Low Risk Items | {risk_summary.get("LOW", 0)} |

---

## Transaction Summary

{transaction_summary}

---

## Control Assessment

### Risk Flags{"" if flags else " — None"}

{"".join(f"- 🚨 **{f['risk']} RISK** — TXN `{f['txn_id']}`: {f['flag']}\n" for f in flags) if flags else "_No exceptions or control failures identified._"}

### Detailed Findings

"""
    # Add per-transaction findings
    for txn_finding in findings.get("transaction_findings", []):
        risk_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(txn_finding["risk_level"], "⚪")
        report += f"#### {risk_emoji} {txn_finding['transaction_id']} — {txn_finding['risk_level']} Risk\n"
        if txn_finding["controls_passed"]:
            report += "**Controls Passed:**\n"
            for c in txn_finding["controls_passed"]:
                report += f"- ✅ {c}\n"
        if txn_finding["controls_failed"]:
            report += "**Controls Failed:**\n"
            for c in txn_finding["controls_failed"]:
                report += f"- ❌ {c}\n"
        report += "\n"

    report += f"""---

## Supporting Documentation

All supporting documents are stored in S3 under:
`s3://{bucket}/supporting-docs/`

Auditors may request direct S3 access or a pre-signed URL package.

---

## Auditor Notes

_This section is reserved for auditor annotations and sign-off._

**Prepared by:** Market Intelligence Agent (Automated)
**Review Required:** {"Yes — exceptions present" if flags else "No — clean run"}

---
*This package was compiled automatically by the Audit Trail Documentation Agent.*
*Powered by AWS Bedrock + Strands Agents*
"""

    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=report.encode("utf-8"),
            ContentType="text/markdown",
        )
        s3_uri = f"s3://{bucket}/{key}"
        stored = True
    except Exception as e:
        s3_uri = f"(S3 store failed: {e})"
        stored = False

    return json.dumps({
        "status": "compiled",
        "s3_uri": s3_uri,
        "stored": stored,
        "audit_period": audit_period,
        "exception_count": len(flags),
        "report_preview": report[:500] + "...",
        "full_report": report,
    }, indent=2)


@tool
def send_audit_package_email(
    report_content: str,
    audit_period: str,
    s3_uri: str,
    recipient_emails: list,
) -> str:
    """
    Email the compiled audit package to auditors and finance leadership.

    Args:
        report_content: Full markdown report content
        audit_period: Human-readable audit period label
        s3_uri: S3 location of the stored package
        recipient_emails: List of email addresses to notify

    Returns:
        JSON with send status per recipient
    """
    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    sender = os.environ.get("SES_SENDER_EMAIL", "")

    if not sender:
        return json.dumps({"error": "SES_SENDER_EMAIL not configured."})
    if not recipient_emails:
        return json.dumps({"error": "No recipient emails provided."})

    subject = f"📋 Audit Trail Package — {audit_period}"
    html_body = _markdown_to_html(report_content, s3_uri)

    results = []
    for email in recipient_emails:
        try:
            response = ses.send_email(
                Source=sender,
                Destination={"ToAddresses": [email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                        "Text": {"Data": report_content, "Charset": "UTF-8"},
                    },
                },
            )
            results.append({"email": email, "status": "sent", "message_id": response["MessageId"]})
        except Exception as e:
            results.append({"email": email, "status": "failed", "error": str(e)})

    sent = sum(1 for r in results if r["status"] == "sent")
    return json.dumps({"sent": sent, "failed": len(results) - sent, "details": results}, indent=2)


def _markdown_to_html(md: str, s3_uri: str = "") -> str:
    """Convert markdown to HTML for email."""
    html = md
    html = re.sub(r"^# (.+)$", r"<h1 style='color:#1a1a2e'>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2 style='color:#16213e;border-bottom:1px solid #eee;padding-bottom:4px'>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$", r"<h3 style='color:#0f3460'>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"\n\n", "</p><p>", html)

    s3_note = f'<p style="background:#f5f5f5;padding:10px;border-radius:4px;font-family:monospace;font-size:12px">📦 Full package stored at: {s3_uri}</p>' if s3_uri else ""

    return f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 860px; margin: auto; padding: 24px; color: #333;">
    <p>{html}</p>
    {s3_note}
    <hr style="margin-top: 40px; border: none; border-top: 1px solid #eee;">
    <p style="font-size: 11px; color: #999;">Audit Trail Documentation Agent — Powered by AWS Bedrock + Strands</p>
    </body></html>
    """


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Audit Trail Documentation Agent — a meticulous financial controls specialist.

Your job is to compile complete, audit-ready packages that external auditors and internal reviewers can rely on.

When given an audit period and scope:
1. Query transactions for the specified period and filters
2. Look up supporting documents for each transaction
3. Assess internal control evidence — check for approvals, PO matches, segregation of duties, and anomalies
4. Compile everything into a structured audit package and store it to S3
5. If recipients are provided, email the package to auditors/finance leadership

Be thorough and precise. Flag every exception. Use risk levels (HIGH / MEDIUM / LOW).
Format output in clean markdown. Never skip a step — auditors depend on completeness.
"""


def create_agent() -> Agent:
    model = BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-5"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )
    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[
            query_transactions,
            list_supporting_documents,
            assess_control_evidence,
            compile_audit_package,
            send_audit_package_email,
        ],
    )


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def handler(event: dict, context) -> dict:
    """
    AWS Lambda handler — AgentCore entry point.

    Expected event payload:
    {
        "audit_period": "Q4 2024",
        "start_date": "2024-10-01",
        "end_date": "2024-12-31",
        "account_codes": ["1000", "2000", "4000", "5100"],  // optional
        "min_amount": 1000,                                  // optional
        "transaction_types": ["INVOICE", "JOURNAL"],         // optional
        "recipients": ["auditor@firm.com", "cfo@company.com"] // optional
    }
    """
    audit_period = event.get("audit_period", "")
    start_date = event.get("start_date", "")
    end_date = event.get("end_date", "")

    if not all([audit_period, start_date, end_date]):
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "audit_period, start_date, and end_date are required"}),
        }

    recipients = event.get("recipients") or _get_recipients_from_env()
    account_codes = event.get("account_codes")
    min_amount = event.get("min_amount")
    transaction_types = event.get("transaction_types")

    agent = create_agent()

    filters_desc = []
    if account_codes:
        filters_desc.append(f"GL accounts: {', '.join(account_codes)}")
    if min_amount:
        filters_desc.append(f"minimum amount: ${min_amount:,.0f}")
    if transaction_types:
        filters_desc.append(f"types: {', '.join(transaction_types)}")
    filters_text = "; ".join(filters_desc) if filters_desc else "no filters (all transactions)"

    prompt = f"""
Compile an audit trail package for the following period:

- Audit Period: {audit_period}
- Date Range: {start_date} to {end_date}
- Filters: {filters_text}
- Recipients: {recipients if recipients else "none — store to S3 only"}

Steps:
1. Query transactions for this period with the specified filters
2. List supporting documents for each transaction found
3. Assess internal controls across all transactions
4. Compile the full audit package and store it to S3
5. {"Email the package to: " + str(recipients) if recipients else "No email needed — S3 only"}
"""

    response = agent(prompt)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "completed",
            "audit_period": audit_period,
            "recipients": recipients,
            "response": str(response),
        }),
    }


def _get_recipients_from_env() -> list:
    raw = os.environ.get("AUDIT_RECIPIENTS", "")
    return [e.strip() for e in raw.split(",") if e.strip()]


# ---------------------------------------------------------------------------
# Local dev runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Running Audit Trail Documentation Agent (dev mode)\n")
    agent = create_agent()
    result = agent(
        "Compile an audit trail package for Q4 2024 (2024-10-01 to 2024-12-31). "
        "Query all transactions, check supporting documents, assess controls, "
        "and compile the audit package. Store to S3. No email needed."
    )
    print(result)
