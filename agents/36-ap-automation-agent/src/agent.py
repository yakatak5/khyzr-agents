"""
AP Automation Agent
===================
Automates accounts payable workflows: extracts invoice data from PDFs,
matches against purchase orders, flags discrepancies, routes for approval,
and updates the AP ledger.

Built with AWS Strands Agents + AgentCore on AWS Bedrock (Claude Sonnet).
Deploys as an AWS Lambda function serving as a Bedrock Action Group executor.
"""

import json
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
    # Provide a no-op decorator so the tool functions still work as plain functions
    def tool(fn):
        return fn


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
    # In production: uses pdfplumber or AWS Textract to parse PDF invoices.
    # If invoice_source is an S3 URI, attempt to fetch the object for text parsing.
    raw_text = ""
    if invoice_source.startswith("s3://"):
        try:
            parts = invoice_source[5:].split("/", 1)
            bucket, key = parts[0], parts[1]
            s3 = boto3.client("s3")
            obj = s3.get_object(Bucket=bucket, Key=key)
            raw_text = obj["Body"].read().decode("utf-8")
        except Exception:
            raw_text = ""  # Fall back to mock data

    # Realistic mock — mirrors the demo invoice loaded into S3 by Terraform
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
            {
                "description": "Industrial Filters - 50 units",
                "quantity": 50,
                "unit_price": 189.00,
                "line_total": 9450.00,
            },
            {
                "description": "Maintenance Kit - 10 units",
                "quantity": 10,
                "unit_price": 300.00,
                "line_total": 3000.00,
            },
        ],
        "payment_terms": "Net 30",
        "bank_account_last4": "7823",
        "extraction_confidence": 0.97,
        "extracted_at": datetime.utcnow().isoformat(),
        "source": invoice_source,
        "raw_text_preview": raw_text[:200] if raw_text else "(mock data)",
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

    # Mock PO data — matches the demo invoice exactly for a clean pass
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
        "approved_date": "2024-02-28",
        "goods_receipt_number": "GR-2024-00891",
        "goods_received_date": "2024-03-08",
    }

    inv_total = inv.get("subtotal", 0)
    po_total = po_data["approved_amount"]
    variance = inv_total - po_total
    variance_pct = (variance / po_total * 100) if po_total else 0

    inv_vendor_id = inv.get("vendor_id", "")
    vendor_match = (po_data["vendor_id"] == inv_vendor_id) if inv_vendor_id else True

    match_result = {
        "po_number": po_number,
        "match_status": "matched" if abs(variance_pct) <= 2 and vendor_match else "discrepancy",
        "three_way_match": {
            "po_match": True,
            "receipt_match": True,  # Goods receipt GR-2024-00891 found
            "invoice_match": abs(variance_pct) <= 2,
        },
        "financial_comparison": {
            "po_approved_amount": po_total,
            "invoice_subtotal": inv_total,
            "variance_amount": round(variance, 2),
            "variance_pct": round(variance_pct, 2),
        },
        "vendor_match": vendor_match,
        "vendor_id_on_po": po_data["vendor_id"],
        "vendor_id_on_invoice": inv_vendor_id,
        "goods_receipt": {
            "receipt_number": po_data["goods_receipt_number"],
            "received_date": po_data["goods_received_date"],
        },
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

    # Price variance checks
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

    # Vendor mismatch check
    if not data.get("vendor_match", True):
        discrepancies.append({
            "code": "VENDOR_MISMATCH",
            "severity": "critical",
            "description": (
                f"Vendor ID on invoice ({data.get('vendor_id_on_invoice', 'N/A')}) "
                f"does not match PO vendor ({data.get('vendor_id_on_po', 'N/A')})"
            ),
            "action": "Block payment — potential fraud indicator",
        })

    # Goods receipt check
    three_way = data.get("three_way_match", {})
    if not three_way.get("receipt_match", True):
        discrepancies.append({
            "code": "NO_GOODS_RECEIPT",
            "severity": "high",
            "description": "No goods receipt recorded for this PO",
            "action": "Hold payment — confirm delivery with warehouse",
        })

    has_critical = any(d["severity"] == "critical" for d in discrepancies)
    has_high = any(d["severity"] == "high" for d in discrepancies)

    return json.dumps({
        "invoice_status": (
            "hold" if has_critical
            else "review" if (has_high or discrepancies)
            else "approved_for_payment"
        ),
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies,
        "recommended_action": (
            "Block payment and escalate" if has_critical
            else "Hold and review discrepancies" if discrepancies
            else "Clear for payment processing"
        ),
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
            approver_email = os.environ.get("AP_CONTROLLER_EMAIL", "ap-controller@demo.com")
            approver_role = "AP Controller"
            priority = "urgent"
        elif has_high:
            approver_email = os.environ.get("AP_MANAGER_EMAIL", "ap-manager@demo.com")
            approver_role = "AP Manager"
            priority = "high"
        else:
            approver_email = os.environ.get("AP_CLERK_EMAIL", "ap-clerk@demo.com")
            approver_role = "AP Clerk"
            priority = "normal"
    else:
        approver_role = "Manual Override"
        priority = "normal"

    # Simulate sending approval notification via SES/SNS
    # In production: boto3.client('ses').send_email(...)
    routing_result = {
        "invoice_number": invoice_number,
        "routing_status": "routed",
        "approval_required": status != "approved_for_payment",
        "assigned_to": approver_email,
        "approver_role": approver_role,
        "priority": priority,
        "invoice_status": status,
        "discrepancy_summary": (
            f"{len(discrepancies)} discrepancy(ies) found: "
            + ", ".join(d["code"] for d in discrepancies)
            if discrepancies else "No discrepancies — clean invoice"
        ),
        "due_by": datetime.utcnow().strftime("%Y-%m-%d"),
        "notification_sent": True,
        "notification_channel": "email",
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

    transaction_id = f"AP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{invoice_number[-5:]}"

    ledger_entry = {
        "transaction_id": transaction_id,
        "invoice_number": invoice_number or inv.get("invoice_number", "UNKNOWN"),
        "vendor_name": inv.get("vendor_name", "Unknown"),
        "vendor_id": inv.get("vendor_id", ""),
        "invoice_date": inv.get("invoice_date", ""),
        "due_date": inv.get("due_date", ""),
        "total_amount": inv.get("total_amount", 0),
        "subtotal": inv.get("subtotal", 0),
        "tax_amount": inv.get("tax_amount", 0),
        "currency": inv.get("currency", "USD"),
        "gl_account": "2000-AP",
        "cost_center": os.environ.get("DEFAULT_COST_CENTER", "CORP-001"),
        "approval_status": approval_status,
        "po_reference": inv.get("po_reference", ""),
        "payment_terms": inv.get("payment_terms", "Net 30"),
        "recorded_at": datetime.utcnow().isoformat(),
        "recorded_by": "AP Automation Agent",
    }

    # Attempt real DynamoDB write
    table_name = os.environ.get("AP_LEDGER_TABLE", "khyzr-ap-automation-demo-ledger")
    region = os.environ.get("AWS_REGION_NAME", os.environ.get("AWS_REGION", "us-east-1"))

    try:
        dynamodb = boto3.resource("dynamodb", region_name=region)
        table = dynamodb.Table(table_name)
        table.put_item(Item=ledger_entry)
        write_status = "written_to_dynamodb"
    except Exception as e:
        write_status = f"simulated (DynamoDB unavailable: {str(e)[:80]})"

    return json.dumps({
        "status": "recorded",
        "transaction_id": transaction_id,
        "write_status": write_status,
        "table": table_name,
        "entry": ledger_entry,
    }, indent=2)


# ---------------------------------------------------------------------------
# Lambda handler — Bedrock Action Group executor
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """Handle Bedrock Agent Action Group invocations."""
    action_group = event.get("actionGroup", "")
    api_path = event.get("apiPath", "")   # e.g. "/extract-invoice-data"
    parameters = event.get("parameters", [])
    request_body = event.get("requestBody", {})

    # Parse parameters list into a dict
    params = {}
    for p in parameters:
        params[p["name"]] = p["value"]

    # Also check requestBody (Bedrock may send params here for POST operations)
    if request_body:
        content = request_body.get("content", {})
        for _media_type, media_content in content.items():
            props = media_content.get("properties", [])
            for prop in props:
                params[prop["name"]] = prop["value"]

    # Route to the correct tool function
    if api_path == "/extract-invoice-data":
        result = extract_invoice_data(params.get("invoice_source", "demo-invoice"))

    elif api_path == "/match-purchase-order":
        result = match_purchase_order(
            params.get("po_number", "PO-2024-00312"),
            params.get("invoice_data", "{}"),
        )

    elif api_path == "/flag-discrepancies":
        result = flag_discrepancies(params.get("match_result", "{}"))

    elif api_path == "/route-for-approval":
        result = route_for_approval(
            params.get("invoice_number", ""),
            params.get("discrepancy_data", "{}"),
            params.get("approver_email", ""),
        )

    elif api_path == "/update-ap-ledger":
        result = update_ap_ledger(
            params.get("invoice_number", ""),
            params.get("invoice_data", "{}"),
            params.get("approval_status", "pending"),
        )

    else:
        result = json.dumps({"error": f"Unknown api_path: {api_path}"})

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "apiPath": api_path,
            "httpMethod": event.get("httpMethod", "POST"),
            "httpStatusCode": 200,
            "responseBody": {
                "application/json": {
                    "body": result
                }
            },
        },
    }


# ---------------------------------------------------------------------------
# Strands Agent definition (for local run() mode)
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


def run(input_data: dict = None) -> dict:
    """
    Local / AgentCore entry point — uses the Strands Agent with all 5 tools.
    Requires strands-agents to be installed.
    """
    if not STRANDS_AVAILABLE:
        return {"error": "strands-agents not installed. Run: pip install strands-agents"}

    if input_data is None:
        input_data = {}

    message = input_data.get(
        "message",
        "Process the demo invoice INV-2024-08821 — extract all data, match against "
        "PO-2024-00312, flag any discrepancies, route for approval, and update the ledger.",
    )

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

    response = agent(message)
    return {"result": str(response)}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if not sys.stdin.isatty():
        input_data = json.loads(sys.stdin.read())
    else:
        input_data = {
            "message": (
                "Process the demo invoice INV-2024-08821 — extract all data, match "
                "against PO-2024-00312, flag any discrepancies, route for approval, "
                "and update the ledger."
            )
        }

    print(json.dumps(run(input_data), indent=2))
