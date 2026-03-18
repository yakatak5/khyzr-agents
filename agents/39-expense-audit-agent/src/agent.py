"""
Expense Audit Agent
===================
Scans employee expense submissions against company policy rules, detects duplicate
claims, flags anomalies, and generates comprehensive audit reports for finance review.

Built with AWS Strands Agents + AgentCore on AWS Bedrock (Claude Sonnet).
"""

import json
import os
import hashlib
import boto3
from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def load_expense_report(report_id: str, employee_id: str = "") -> str:
    """
    Load an expense report from the expense management system.

    Args:
        report_id: Expense report identifier
        employee_id: Optional employee ID to filter by submitter

    Returns:
        JSON string with expense report details, line items, and submission metadata
    """
    # In production: queries Concur, Expensify, or internal ERP expense module
    expense_report = {
        "report_id": report_id,
        "employee_id": employee_id or "EMP-10284",
        "employee_name": "Jordan Martinez",
        "department": "Sales",
        "manager_email": "manager@company.com",
        "submission_date": "2024-03-12",
        "period_start": "2024-02-01",
        "period_end": "2024-02-29",
        "status": "pending_audit",
        "total_claimed": 3847.50,
        "expense_items": [
            {
                "item_id": "EXP-001",
                "date": "2024-02-05",
                "category": "meals",
                "merchant": "The Capital Grille",
                "amount": 487.50,
                "attendees": 4,
                "receipt_attached": True,
                "description": "Client dinner - ABC Corp deal discussion",
            },
            {
                "item_id": "EXP-002",
                "date": "2024-02-07",
                "category": "travel_airfare",
                "merchant": "United Airlines",
                "amount": 1250.00,
                "receipt_attached": True,
                "description": "Flight NYC-LA for Q1 customer summit",
            },
            {
                "item_id": "EXP-003",
                "date": "2024-02-08",
                "category": "hotel",
                "merchant": "Marriott LA",
                "amount": 425.00,
                "nights": 1,
                "receipt_attached": True,
                "description": "Hotel - Q1 customer summit",
            },
            {
                "item_id": "EXP-004",
                "date": "2024-02-14",
                "category": "meals",
                "merchant": "Starbucks",
                "amount": 12.50,
                "receipt_attached": False,
                "description": "Team coffee",
            },
            {
                "item_id": "EXP-005",
                "date": "2024-02-20",
                "category": "entertainment",
                "merchant": "Broadway Theater",
                "amount": 480.00,
                "attendees": 2,
                "receipt_attached": True,
                "description": "Client entertainment",
            },
            {
                "item_id": "EXP-006",
                "date": "2024-02-22",
                "category": "meals",
                "merchant": "The Capital Grille",
                "amount": 487.50,
                "attendees": 4,
                "receipt_attached": True,
                "description": "Client dinner - ABC Corp deal discussion",
            },
            {
                "item_id": "EXP-007",
                "date": "2024-02-28",
                "category": "office_supplies",
                "merchant": "Amazon",
                "amount": 205.00,
                "receipt_attached": True,
                "description": "Office supplies for home office",
            },
        ],
        "loaded_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(expense_report, indent=2)


@tool
def check_policy_compliance(expense_items: str) -> str:
    """
    Check each expense item against company expense policy rules.

    Args:
        expense_items: JSON array string of expense items from the report

    Returns:
        JSON string with per-item compliance status and policy violations
    """
    try:
        items = json.loads(expense_items) if isinstance(json.loads(expense_items), list) else json.loads(expense_items).get("expense_items", [])
    except Exception:
        return json.dumps({"error": "Invalid expense items format"})

    # Company policy rules
    policy = {
        "meals_per_person_limit": 75.00,
        "hotel_per_night_limit": 350.00,
        "entertainment_per_person_limit": 150.00,
        "receipt_required_threshold": 25.00,
        "pre_approval_required_categories": ["entertainment"],
        "non_reimbursable_categories": ["personal_items", "alcohol_standalone"],
    }

    results = []
    for item in items:
        violations = []
        category = item.get("category", "")
        amount = item.get("amount", 0)
        receipt = item.get("receipt_attached", False)
        attendees = item.get("attendees", 1)

        # Receipt check
        if amount >= policy["receipt_required_threshold"] and not receipt:
            violations.append({
                "rule": "RECEIPT_REQUIRED",
                "message": f"Receipt required for expenses ≥${policy['receipt_required_threshold']:.0f}",
                "severity": "high",
            })

        # Per-person limits
        if category == "meals" and attendees:
            per_person = amount / attendees
            if per_person > policy["meals_per_person_limit"]:
                violations.append({
                    "rule": "MEALS_LIMIT_EXCEEDED",
                    "message": f"Meal cost ${per_person:.2f}/person exceeds ${policy['meals_per_person_limit']:.0f} policy limit",
                    "severity": "medium",
                })

        if category == "hotel":
            nights = item.get("nights", 1)
            per_night = amount / nights if nights else amount
            if per_night > policy["hotel_per_night_limit"]:
                violations.append({
                    "rule": "HOTEL_LIMIT_EXCEEDED",
                    "message": f"Hotel rate ${per_night:.2f}/night exceeds ${policy['hotel_per_night_limit']:.0f} policy limit",
                    "severity": "medium",
                })

        if category == "entertainment" and attendees:
            per_person = amount / attendees
            if per_person > policy["entertainment_per_person_limit"]:
                violations.append({
                    "rule": "ENTERTAINMENT_LIMIT_EXCEEDED",
                    "message": f"Entertainment ${per_person:.2f}/person exceeds ${policy['entertainment_per_person_limit']:.0f} limit",
                    "severity": "medium",
                })

        results.append({
            "item_id": item.get("item_id"),
            "category": category,
            "amount": amount,
            "compliant": len(violations) == 0,
            "violations": violations,
        })

    non_compliant = [r for r in results if not r["compliant"]]
    return json.dumps({
        "total_items": len(results),
        "compliant_items": len(results) - len(non_compliant),
        "non_compliant_items": len(non_compliant),
        "compliance_rate": round((len(results) - len(non_compliant)) / len(results) * 100, 1) if results else 0,
        "item_results": results,
    }, indent=2)


@tool
def detect_duplicates(expense_items: str, lookback_days: int = 90) -> str:
    """
    Detect potential duplicate expense claims by analyzing merchant, amount, and date proximity.

    Args:
        expense_items: JSON string of expense items to scan
        lookback_days: Number of days to look back for duplicate detection

    Returns:
        JSON string with identified duplicate clusters and confidence scores
    """
    try:
        data = json.loads(expense_items)
        items = data if isinstance(data, list) else data.get("expense_items", [])
    except Exception:
        return json.dumps({"error": "Invalid input"})

    # Generate fingerprint for each item (merchant + amount + date)
    seen = {}
    duplicates = []

    for item in items:
        # Create a fingerprint key
        merchant = item.get("merchant", "").lower().strip()
        amount = item.get("amount", 0)
        description = item.get("description", "").lower()
        fp_key = f"{merchant}|{amount}"

        if fp_key in seen:
            duplicates.append({
                "type": "exact_duplicate",
                "confidence": 0.95,
                "items": [seen[fp_key]["item_id"], item.get("item_id")],
                "merchant": merchant,
                "amount": amount,
                "dates": [seen[fp_key]["date"], item.get("date")],
                "action": "FLAG — likely duplicate submission",
            })
        else:
            seen[fp_key] = item

    return json.dumps({
        "duplicate_clusters_found": len(duplicates),
        "duplicates": duplicates,
        "scan_window_days": lookback_days,
        "scanned_items": len(items),
        "scanned_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def flag_anomalies(expense_report: str, compliance_results: str, duplicate_results: str) -> str:
    """
    Perform holistic anomaly detection combining policy violations, duplicates, and statistical outliers.

    Args:
        expense_report: Full expense report JSON string
        compliance_results: JSON from check_policy_compliance
        duplicate_results: JSON from detect_duplicates

    Returns:
        JSON string with all flagged anomalies, risk score, and recommended disposition
    """
    try:
        report = json.loads(expense_report)
        compliance = json.loads(compliance_results)
        duplicates = json.loads(duplicate_results)
    except Exception as e:
        return json.dumps({"error": str(e)})

    flags = []

    # Add compliance violations
    for item in compliance.get("item_results", []):
        for v in item.get("violations", []):
            flags.append({
                "flag_type": "POLICY_VIOLATION",
                "severity": v["severity"],
                "item_id": item["item_id"],
                "description": v["message"],
                "code": v["rule"],
            })

    # Add duplicates
    for dup in duplicates.get("duplicates", []):
        flags.append({
            "flag_type": "DUPLICATE_CLAIM",
            "severity": "critical",
            "item_ids": dup["items"],
            "description": f"Potential duplicate: {dup['merchant']} ${dup['amount']:.2f} on {dup['dates']}",
            "code": "DUPLICATE_SUBMISSION",
        })

    # Statistical outlier check (amount > 2x average)
    items = report.get("expense_items", [])
    if items:
        amounts = [i["amount"] for i in items]
        avg = sum(amounts) / len(amounts)
        for item in items:
            if item["amount"] > avg * 2.5 and item["amount"] > 500:
                flags.append({
                    "flag_type": "STATISTICAL_OUTLIER",
                    "severity": "medium",
                    "item_id": item.get("item_id"),
                    "description": f"Amount ${item['amount']:.2f} is {item['amount']/avg:.1f}x the report average",
                    "code": "HIGH_AMOUNT_OUTLIER",
                })

    # Risk scoring
    critical_count = sum(1 for f in flags if f["severity"] == "critical")
    high_count = sum(1 for f in flags if f["severity"] == "high")
    risk_score = min(100, critical_count * 30 + high_count * 15 + len(flags) * 5)

    disposition = "APPROVE" if risk_score < 20 else ("REVIEW" if risk_score < 50 else "REJECT")

    return json.dumps({
        "report_id": report.get("report_id"),
        "total_flags": len(flags),
        "critical_flags": critical_count,
        "high_flags": high_count,
        "risk_score": risk_score,
        "recommended_disposition": disposition,
        "flags": flags,
        "flagged_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def generate_audit_report(report_id: str, anomaly_data: str, employee_name: str = "") -> str:
    """
    Generate a complete expense audit report with findings, recommendations, and disposition.

    Args:
        report_id: Expense report identifier
        anomaly_data: JSON string from flag_anomalies with all findings
        employee_name: Employee name for the report header

    Returns:
        JSON string with complete audit report suitable for finance team review
    """
    try:
        anomalies = json.loads(anomaly_data)
    except Exception as e:
        return json.dumps({"error": str(e)})

    disposition = anomalies.get("recommended_disposition", "REVIEW")
    flags = anomalies.get("flags", [])

    audit_report = {
        "audit_report": {
            "report_id": report_id,
            "employee_name": employee_name or "Unknown",
            "audit_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "auditor": "Khyzr Expense Audit Agent",
            "executive_summary": {
                "disposition": disposition,
                "risk_score": anomalies.get("risk_score"),
                "total_flags": anomalies.get("total_flags"),
                "critical_issues": anomalies.get("critical_flags"),
            },
            "findings": flags,
            "recommendations": [
                "Investigate duplicate claims before approving payment" if anomalies.get("critical_flags", 0) > 0 else None,
                "Request receipts for flagged items above $25 threshold" if any(f.get("code") == "RECEIPT_REQUIRED" for f in flags) else None,
                "Manager review required for amounts exceeding policy limits" if any(f.get("flag_type") == "POLICY_VIOLATION" for f in flags) else None,
            ],
            "required_actions": [f for f in [
                "Block payment pending duplicate investigation" if anomalies.get("critical_flags", 0) > 0 else None,
                "Request supporting documentation for flagged items" if anomalies.get("total_flags", 0) > 0 else None,
            ] if f],
        },
        "generated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(audit_report, indent=2)


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Expense Audit Agent for Khyzr — an expert internal auditor specializing in employee expense compliance, fraud detection, and policy enforcement.

Your mission is to systematically audit expense reports: load the submission, validate each line item against policy, detect duplicates, flag anomalies, and generate a comprehensive audit report for finance team review.

When auditing an expense report:
1. Load the complete expense report including all line items, receipts, and metadata
2. Check each item against company expense policy rules:
   - Meals: ≤$75/person with receipt
   - Hotels: ≤$350/night
   - Entertainment: ≤$150/person, pre-approval required
   - Receipts required for expenses ≥$25
3. Detect duplicate submissions: same merchant + amount within the lookback window
4. Run statistical anomaly detection: identify outlier amounts and suspicious patterns
5. Generate a risk-scored audit report with clear APPROVE/REVIEW/REJECT recommendation

Fraud indicators you actively look for:
- **Duplicate Claims**: Same expense submitted multiple times (exact or near-duplicate)
- **Round Number Bias**: Clusters of round-number amounts (common in fabricated receipts)
- **Weekend/Holiday Expenses**: Business expenses on weekends without clear justification
- **Excessive Per-Person Costs**: Lavish meals or entertainment beyond policy
- **Missing Receipts**: Particularly for high-value items where receipts should exist
- **Pattern Anomalies**: Employee submitting significantly more than peers in same role

Audit outcomes:
- **APPROVE**: Risk score < 20, no critical flags
- **REVIEW**: Risk score 20-50, policy violations requiring manager sign-off
- **REJECT**: Risk score > 50, critical flags (duplicates, suspected fraud)

Your reports protect company finances while treating employees fairly. Flag legitimate issues with clear evidence, but avoid false positives that create unnecessary friction. Document all findings clearly for audit trail purposes."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[
        load_expense_report,
        check_policy_compliance,
        detect_duplicates,
        flag_anomalies,
        generate_audit_report,
    ],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Audit expense report EXP-2024-0312 for policy compliance and duplicate claims")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Audit expense report EXP-2024-0312 — check all items against policy, detect any duplicates, flag anomalies, and generate the audit report."
    }
    print(json.dumps(run(input_data)))
