"""
Procurement Agent
==================
Manages RFQ distribution, collects vendor responses, and scores proposals
based on predefined criteria for procurement decisions.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def create_rfq(requirements: dict) -> str:
    """
    Create an RFQ (Request for Quotation) document from procurement requirements.

    Args:
        requirements: Dict with: item_description, quantity, specifications, delivery_date,
                      evaluation_criteria, submission_deadline

    Returns:
        JSON RFQ document ready for distribution
    """
    rfq = {
        "rfq_id": f"RFQ-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "created_at": datetime.utcnow().isoformat(),
        "status": "draft",
        "item_description": requirements.get("item_description", ""),
        "quantity": requirements.get("quantity"),
        "specifications": requirements.get("specifications", []),
        "delivery_requirements": {
            "required_by": requirements.get("delivery_date"),
            "delivery_location": requirements.get("delivery_location", "TBD"),
            "incoterms": requirements.get("incoterms", "DAP"),
        },
        "commercial_terms": {
            "payment_terms": requirements.get("payment_terms", "Net 30"),
            "currency": requirements.get("currency", "USD"),
            "price_validity_days": requirements.get("price_validity_days", 30),
        },
        "evaluation_criteria": requirements.get("evaluation_criteria", {
            "price": 40,
            "quality": 25,
            "delivery_capability": 20,
            "vendor_stability": 15,
        }),
        "submission_deadline": requirements.get("submission_deadline", (datetime.utcnow() + timedelta(days=14)).strftime("%Y-%m-%d")),
        "submission_instructions": "Submit proposals via email to procurement@company.com with RFQ ID in subject line",
    }
    
    bucket = os.environ.get("PROCUREMENT_BUCKET", "khyzr-procurement")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    key = f"rfqs/{rfq['rfq_id']}.json"
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(rfq).encode(), ContentType="application/json")
    except Exception:
        pass
    
    return json.dumps(rfq, indent=2)


@tool
def distribute_rfq_to_vendors(rfq_id: str, vendor_emails: list) -> str:
    """
    Distribute an RFQ to a list of qualified vendors via email.

    Args:
        rfq_id: RFQ identifier
        vendor_emails: List of vendor email addresses

    Returns:
        JSON distribution status
    """
    sender = os.environ.get("SES_SENDER_EMAIL", "")
    if not sender:
        return json.dumps({"status": "skipped", "note": "Configure SES_SENDER_EMAIL", "vendors_targeted": len(vendor_emails)})
    
    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    subject = f"Request for Quotation: {rfq_id}"
    body = f"""Dear Vendor,

We are inviting your company to submit a proposal for {rfq_id}.

Please review the attached RFQ specifications and submit your quotation by the deadline specified.

RFQ ID: {rfq_id}
Portal: {os.environ.get("VENDOR_PORTAL_URL", "https://vendor-portal.company.com")}

Please reference RFQ ID {rfq_id} in your submission.

Best regards,
Procurement Team"""
    
    results = []
    for email in vendor_emails:
        try:
            resp = ses.send_email(
                Source=sender,
                Destination={"ToAddresses": [email]},
                Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}},
            )
            results.append({"vendor_email": email, "status": "sent", "message_id": resp["MessageId"]})
        except Exception as e:
            results.append({"vendor_email": email, "status": "failed", "error": str(e)})
    
    return json.dumps({"rfq_id": rfq_id, "distributed_to": len(results), "sent": sum(1 for r in results if r["status"] == "sent"), "details": results}, indent=2)


@tool
def score_vendor_proposal(rfq_id: str, vendor_name: str, proposal: dict, evaluation_criteria: dict) -> str:
    """
    Score a vendor proposal against evaluation criteria.

    Args:
        rfq_id: RFQ identifier
        vendor_name: Vendor name
        proposal: Vendor proposal dict with price, quality_evidence, delivery_commitment, references
        evaluation_criteria: Dict of criteria with weights (must sum to 100)

    Returns:
        JSON scored proposal with total score and ranking input
    """
    weights = evaluation_criteria or {"price": 40, "quality": 25, "delivery_capability": 20, "vendor_stability": 15}
    scores = {}
    
    # Price scoring (lower price = higher score, but normalize against proposals)
    quoted_price = proposal.get("total_price", 0)
    if quoted_price > 0:
        # Normalize — needs multiple proposals for real scoring; use absolute evaluation for now
        price_score = 8  # Will be adjusted when comparing across proposals
        scores["price"] = {"raw_value": quoted_price, "score_out_of_10": price_score}
    
    # Quality
    quality_certs = len(proposal.get("quality_certifications", []))
    quality_score = min(10, quality_certs * 2 + (5 if proposal.get("iso_certified") else 0))
    scores["quality"] = {"certifications": quality_certs, "score_out_of_10": quality_score}
    
    # Delivery
    commit_days = proposal.get("delivery_days_committed", 999)
    required_days = proposal.get("required_delivery_days", 30)
    delivery_score = 10 if commit_days <= required_days else max(0, 10 - (commit_days - required_days) / 5)
    scores["delivery_capability"] = {"committed_days": commit_days, "score_out_of_10": round(delivery_score, 1)}
    
    # Vendor stability
    years_in_business = proposal.get("years_in_business", 0)
    stability_score = min(10, years_in_business / 2)
    scores["vendor_stability"] = {"years_in_business": years_in_business, "score_out_of_10": round(stability_score, 1)}
    
    # Weighted total
    total = sum(scores.get(k, {}).get("score_out_of_10", 5) * (weights.get(k, 10) / 100) for k in weights)
    
    return json.dumps({
        "rfq_id": rfq_id,
        "vendor": vendor_name,
        "proposal_summary": {"total_price": quoted_price, "delivery_commitment": f"{commit_days} days"},
        "scores_by_criterion": scores,
        "total_weighted_score": round(total, 2),
        "max_possible_score": 10,
        "recommendation": "Recommend" if total >= 7 else ("Consider" if total >= 5 else "Do Not Recommend"),
        "scored_at": datetime.utcnow().isoformat(),
    }, indent=2)


SYSTEM_PROMPT = """You are the Procurement Agent for Khyzr — a senior procurement manager and strategic sourcing specialist.

Your mission is to run efficient, fair, and transparent procurement processes that secure the best value for the company while managing supplier risk.

Procurement methodology:
- **Strategic Sourcing**: Understand total cost of ownership, not just unit price
- **Competitive Bidding**: Always get 3+ qualified quotes for any significant purchase
- **Objective Evaluation**: Score proposals against predefined, weighted criteria before selection
- **Vendor Development**: Build long-term partnerships with strategic suppliers
- **Risk Management**: Assess vendor financial health, capacity, and concentration risk

RFQ process steps:
1. Define requirements (specifications, quantities, delivery, commercial terms)
2. Identify and qualify vendor pool (3-5+ qualified vendors)
3. Draft and distribute RFQ with clear evaluation criteria
4. Receive and log proposals within deadline
5. Score each proposal objectively against weighted criteria
6. Generate recommendation with top vendor and backup option
7. Negotiate final terms and award contract

Evaluation criteria weights (customize by category):
- Direct materials: Price 40%, Quality 30%, Delivery 20%, Vendor stability 10%
- Services/IT: Quality 35%, Capabilities 30%, Price 25%, References 10%
- Logistics: Price 30%, Reliability 35%, Coverage 20%, Technology 15%"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[create_rfq, distribute_rfq_to_vendors, score_vendor_proposal],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    message = input_data.get("message", "Create and distribute an RFQ for upcoming procurement need")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Create an RFQ for 500 units of industrial sensors (model IS-4000 or equivalent), required by 2025-11-15, Net 30 payment terms. Distribute to vendors: vendor1@example.com, vendor2@example.com, vendor3@example.com."
    }
    print(json.dumps(run(input_data)))
