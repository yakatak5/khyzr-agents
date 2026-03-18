"""
AP Automation Agent
===================
Automates accounts payable workflows: extracts invoice data from PDFs,
matches against purchase orders, flags discrepancies, routes for approval,
and updates the AP ledger.

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
def extract_invoice_data(invoice_source: str) -> str:
    """
    Extract structured data from an invoice (PDF path, S3 URI, or raw text).

    Args:
        invoice_source: S3 URI, file path, or base64-encoded invoice content

    Returns:
        JSON string with extracted invoice fields: vendor, amount, line items, dates, PO reference
    """
    # In production: uses pdfplumber or AWS Textract to parse PDF invoices
    # Simulated extraction result
    invoice_data = {
        "invoice_number": "INV-2024-08821",
        "vendor_name": "Apex Supply Co.",
        "vendor_id": "VND-4492",
        "invoice_date": "2024-03-10",
        "due_date": "2024-04-09",
        "po_reference": "PO-2024-00312",
        "currency": "USD",
        "subtotal": 12450.00,
        "tax_amount": 996.00,
        "total_amount": 13446.00,
        "line_items": [
            {"description": "Industrial Filters - 50 units", "quantity": 50, "unit_price": 189.00, "line_total": 9450.00},
            {"description": "Maintenance Kit - 10 units", "quantity": 10, "unit_price": 300.00, "line_total": 3000.00},
        ],
        "payment_terms": "Net 30",
        "bank_account_last4": "7823",
        "extraction_confidence": 0.97,
        "extracted_at": datetime.utcnow().isoformat(),
        "source": invoice_source,
    }
    return json.dumps(invoice_data, indent=2)


@tool
def match_purchase_order(po_number: str, invoice_data: str) -> str:
    """
    Match an invoice against its referenced purchase order from the ERP system.

    Args:
        po_number: Purchase order number to retrieve and match against
        invoice_data: JSON string of extracted invoice data

    Returns:
        JSON string with match results, variance analysis, and three-way match status
    """
    # In production: queries ERP (SAP, Oracle, NetSuite) via API
    try:
        inv = json.loads(invoice_data)
    except Exception:
        inv = {}

    po_data = {
        "po_number": po_number,
        "vendor_id": "VND-4492",
        "approved_amount": 12450.00,
        "line_items": [
            {"description": "Industrial Filters", "quantity_ordered": 50, "unit_price": 189.00},
            {"description": "Maintenance Kit", "quantity_ordered": 10, "unit_price": 300.00},
        ],
        "status": "approved",
        "approved_by": "procurement@company.com",
    }

    inv_total = inv.get("subtotal", 0)
    po_total = po_data["approved_amount"]
    variance = inv_total - po_total
    variance_pct = (variance / po_total * 100) if po_total else 0

    match_result = {
        "po_number": po_number,
        "match_status": "matched" if abs(variance_pct) <= 2 else "discrepancy",
        "three_way_match": {
            "po_match": True,
            "receipt_match": True,  # In production, checks goods receipt
            "invoice_match": abs(variance_pct) <= 2,
        },
        "financial_comparison": {
            "po_approved_amount": po_total,
            "invoice_subtotal": inv_total,
            "variance_amount": round(variance, 2),
            "variance_pct": round(variance_pct, 2),
        },
        "vendor_match": po_data["vendor_id"] == inv.get("vendor_id"),
        "matched_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(match_result, indent=2)


@tool
def flag_discrepancies(match_result: str) -> str:
    """
    Evaluate match results and flag discrepancies requiring human review.

    Args:
        match_result: JSON string from match_purchase_order

    Returns:
        JSON string listing all discrepancies with severity, codes, and recommended actions
    """
    try:
        data = json.loads(match_result)
    except Exception:
        return json.dumps({"error": "Invalid match result data"})

    discrepancies = []
    fin = data.get("financial_comparison", {})
    variance_pct = abs(fin.get("variance_pct", 0))
    variance_amt = fin.get("variance_amount", 0)

    if variance_pct > 10:
        discrepancies.append({
            "code": "PRICE_VARIANCE_HIGH",
            "severity": "critical",
            "description": f"Invoice amount deviates {variance_pct:.1f}% from PO (${variance_amt:.2f})",
            "action": "Hold payment — escalate to Procurement Manager",
        })
    elif variance_pct > 2:
        discrepancies.append({
            "code": "PRICE_VARIANCE_MINOR",
            "severity": "warning",
            "description": f"Invoice amount deviates {variance_pct:.1f}% from PO",
            "action": "Route to approver with variance note",
        })

    if not data.get("vendor_match"):
        discrepancies.append({
            "code": "VENDOR_MISMATCH",
            "severity": "critical",
            "description": "Vendor ID on invoice does not match PO vendor",
            "action": "Block payment — potential fraud indicator",
        })

    three_way = data.get("three_way_match", {})
    if not three_way.get("receipt_match"):
        discrepancies.append({
            "code": "NO_GOODS_RECEIPT",
            "severity": "high",
            "description": "No goods receipt recorded for this PO",
            "action": "Hold payment — confirm delivery with warehouse",
        })

    return json.dumps({
        "invoice_status": "hold" if any(d["severity"] == "critical" for d in discrepancies) else (
            "review" if discrepancies else "approved_for_payment"
        ),
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies,
        "evaluated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def route_for_approval(invoice_number: str, discrepancy_data: str, approver_email: str = "") -> str:
    """
    Route invoice for approval based on discrepancy severity and approval thresholds.

    Args:
        invoice_number: Invoice number to route
        discrepancy_data: JSON string from flag_discrepancies
        approver_email: Override approver email (uses role-based routing if empty)

    Returns:
        JSON string with routing decision, approver assigned, and notification status
    """
    try:
        disc = json.loads(discrepancy_data)
    except Exception:
        disc = {}

    status = disc.get("invoice_status", "review")
    discrepancies = disc.get("discrepancies", [])

    # Role-based routing logic
    if not approver_email:
        has_critical = any(d["severity"] == "critical" for d in discrepancies)
        has_high = any(d["severity"] == "high" for d in discrepancies)
        if has_critical:
            approver_email = os.environ.get("AP_CONTROLLER_EMAIL", "ap-controller@company.com")
            approver_role = "AP Controller"
        elif has_high:
            approver_email = os.environ.get("AP_MANAGER_EMAIL", "ap-manager@company.com")
            approver_role = "AP Manager"
        else:
            approver_email = os.environ.get("AP_CLERK_EMAIL", "ap-clerk@company.com")
            approver_role = "AP Clerk"
    else:
        approver_role = "Manual Override"

    # Simulate sending approval notification via SES/SNS
    routing_result = {
        "invoice_number": invoice_number,
        "routing_status": "routed",
        "approval_required": status != "approved_for_payment",
        "assigned_to": approver_email,
        "approver_role": approver_role,
        "priority": "urgent" if any(d["severity"] == "critical" for d in discrepancies) else "normal",
        "due_by": datetime.utcnow().strftime("%Y-%m-%d"),
        "notification_sent": True,
        "routed_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(routing_result, indent=2)


@tool
def update_ap_ledger(invoice_number: str, invoice_data: str, approval_status: str = "pending") -> str:
    """
    Update the AP ledger with invoice details and approval status.

    Args:
        invoice_number: Invoice number to record
        invoice_data: JSON string of invoice details
        approval_status: Current status (pending, approved, rejected, paid)

    Returns:
        JSON string with ledger entry confirmation and transaction ID
    """
    try:
        inv = json.loads(invoice_data)
    except Exception:
        inv = {}

    # In production: writes to ERP (NetSuite, QuickBooks, SAP) via API
    ledger_entry = {
        "transaction_id": f"AP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "invoice_number": invoice_number,
        "vendor_name": inv.get("vendor_name", "Unknown"),
        "vendor_id": inv.get("vendor_id", ""),
        "invoice_date": inv.get("invoice_date", ""),
        "due_date": inv.get("due_date", ""),
        "total_amount": inv.get("total_amount", 0),
        "currency": inv.get("currency", "USD"),
        "gl_account": "2000-AP",
        "cost_center": os.environ.get("DEFAULT_COST_CENTER", "CORP-001"),
        "approval_status": approval_status,
        "po_reference": inv.get("po_reference", ""),
        "recorded_at": datetime.utcnow().isoformat(),
        "recorded_by": "AP Automation Agent",
    }

    # Persist to DynamoDB in production
    dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    table_name = os.environ.get("AP_LEDGER_TABLE", "khyzr-ap-ledger")

    try:
        table = dynamodb.Table(table_name)
        table.put_item(Item=ledger_entry)
        return json.dumps({"status": "recorded", "entry": ledger_entry})
    except Exception as e:
        return json.dumps({"status": "simulated", "note": str(e), "entry": ledger_entry})


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the AP Automation Agent for Khyzr — an expert accounts payable specialist with deep knowledge of invoice processing, purchase order matching, and financial controls.

Your mission is to automate the end-to-end accounts payable workflow: extract invoice data, perform three-way matching, identify discrepancies, route for approval, and maintain an accurate AP ledger.

When processing an invoice:
1. Extract all structured data from the invoice (vendor, amounts, line items, PO reference, dates)
2. Retrieve the referenced purchase order and perform three-way matching (PO ↔ Invoice ↔ Goods Receipt)
3. Flag any discrepancies with severity classification:
   - **Critical**: Vendor mismatch, >10% price variance, potential duplicate → Block payment
   - **High**: Missing goods receipt, quantity variance → Hold and investigate
   - **Warning**: Minor price variance (2-10%), missing PO reference → Route for review
4. Route invoice to the appropriate approver based on discrepancy severity
5. Update the AP ledger with the invoice record and current approval status

Financial controls you enforce:
- **Segregation of duties**: Extraction, approval, and payment are separate steps
- **Duplicate detection**: Check for duplicate invoice numbers from the same vendor
- **Vendor validation**: Confirm vendor ID matches before processing
- **Payment terms adherence**: Flag invoices approaching due dates for prioritization
- **Early payment discounts**: Identify and flag discount opportunities (e.g., 2/10 Net 30)

Always maintain GAAP compliance and internal audit readiness. Document every decision with clear rationale. Flag 🚨 on any potential fraud indicators (vendor mismatch, unusual bank account changes, round-number amounts). Your work directly impacts cash flow and vendor relationships — be accurate and timely."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[
        extract_invoice_data,
        match_purchase_order,
        flag_discrepancies,
        route_for_approval,
        update_ap_ledger,
    ],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Process invoice INV-2024-08821 from the incoming queue")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Process invoice from s3://khyzr-ap-inbox/invoices/INV-2024-08821.pdf — extract data, match PO, flag any discrepancies, and route for approval."
    }
    print(json.dumps(run(input_data)))
