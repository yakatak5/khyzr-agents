"""
Support Automation Agent
=========================
Classifies, prioritizes, and auto-resolves or routes support tickets
based on content, urgency, and customer context.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json, os, boto3
from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def fetch_open_tickets(status: str = "open", limit: int = 50) -> str:
    """Fetch open support tickets from helpdesk system."""
    table_name = os.environ.get("TICKETS_TABLE_NAME")
    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            resp = table.scan(FilterExpression="#s = :s", ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":s": status}, Limit=limit)
            return json.dumps({"tickets": resp.get("Items", [])}, indent=2)
        except Exception:
            pass
    
    sample_tickets = [
        {"ticket_id": "TKT-001", "subject": "Cannot login to dashboard", "body": "I keep getting 401 errors when trying to login. This is blocking our team from accessing reports.", "customer_tier": "enterprise", "submitted_at": "2025-10-01T09:00:00Z", "status": "open", "category": None},
        {"ticket_id": "TKT-002", "subject": "How do I export data to CSV?", "body": "Hi, I wanted to know how to export my data to CSV format.", "customer_tier": "starter", "submitted_at": "2025-10-01T10:30:00Z", "status": "open", "category": None},
        {"ticket_id": "TKT-003", "subject": "API integration returning 500 errors in production", "body": "URGENT - Our production integration has been returning 500 errors for 2 hours. Revenue is impacted.", "customer_tier": "enterprise", "submitted_at": "2025-10-01T11:00:00Z", "status": "open", "category": None},
    ]
    return json.dumps({"tickets": sample_tickets, "note": "Configure TICKETS_TABLE_NAME for real helpdesk data"}, indent=2)


@tool
def classify_and_prioritize_ticket(ticket: dict) -> str:
    """
    Classify ticket category and assign priority based on content and customer context.

    Returns:
        JSON with classification, priority, and routing recommendation
    """
    subject = (ticket.get("subject", "") + " " + ticket.get("body", "")).lower()
    customer_tier = ticket.get("customer_tier", "standard")
    
    # Category classification
    categories = {
        "auth_login": ["login", "password", "401", "authentication", "access denied", "cannot login"],
        "api_integration": ["api", "integration", "500", "endpoint", "webhook", "sdk"],
        "data_export": ["export", "csv", "download", "report", "data"],
        "billing": ["invoice", "billing", "payment", "charge", "subscription"],
        "performance": ["slow", "timeout", "latency", "loading", "performance"],
        "bug": ["error", "broken", "not working", "issue", "problem", "bug"],
        "how_to": ["how do i", "how to", "where is", "help me", "guide"],
    }
    
    category = "general"
    for cat, keywords in categories.items():
        if any(kw in subject for kw in keywords):
            category = cat
            break
    
    # Priority based on category + customer tier + urgency signals
    urgency_signals = ["urgent", "production", "critical", "down", "revenue", "blocking", "emergency"]
    is_urgent = any(s in subject for s in urgency_signals)
    
    priority_matrix = {
        ("enterprise", True): "P1",
        ("enterprise", False): "P2",
        ("business", True): "P2",
        ("business", False): "P3",
        ("starter", True): "P2",
        ("starter", False): "P4",
    }
    
    priority = priority_matrix.get((customer_tier, is_urgent), "P3")
    if category == "api_integration" and is_urgent:
        priority = "P1"
    
    # Auto-resolve candidates
    auto_resolvable = category == "how_to"
    kb_articles = {"how_to": "https://docs.khyzr.ai/faq", "data_export": "https://docs.khyzr.ai/export", "auth_login": "https://docs.khyzr.ai/login-troubleshooting"}
    
    routing = {
        "P1": "senior_support_engineer",
        "P2": "support_engineer",
        "P3": "support_associate",
        "P4": "self_service_or_tier1",
    }.get(priority, "support_associate")
    
    sla_hours = {"P1": 1, "P2": 4, "P3": 8, "P4": 24}.get(priority, 8)
    
    return json.dumps({
        "ticket_id": ticket.get("ticket_id"),
        "category": category,
        "priority": priority,
        "is_urgent": is_urgent,
        "sla_response_hours": sla_hours,
        "routing": routing,
        "auto_resolvable": auto_resolvable,
        "suggested_kb_article": kb_articles.get(category),
        "classified_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def auto_respond_ticket(ticket_id: str, category: str, customer_email: str, kb_article_url: str = None) -> str:
    """Send an automated first-response to a support ticket."""
    sender = os.environ.get("SES_SENDER_EMAIL", "")
    if not sender:
        return json.dumps({"status": "skipped", "note": "Configure SES_SENDER_EMAIL"})
    
    responses = {
        "how_to": f"Thank you for reaching out! I found this guide that should help: {kb_article_url or 'https://docs.khyzr.ai'}. If you need further assistance, a support engineer will follow up.",
        "auth_login": f"I can see you're having trouble logging in. Please try: 1) Clear browser cache, 2) Use incognito mode, 3) Reset password at https://app.khyzr.ai/reset. If issue persists, our team is investigating. Full guide: {kb_article_url or 'https://docs.khyzr.ai/login'}",
        "general": "Thank you for contacting Khyzr Support. We've received your request and a support engineer will be in touch within the SLA window.",
    }
    
    body = responses.get(category, responses["general"])
    
    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    try:
        resp = ses.send_email(
            Source=sender,
            Destination={"ToAddresses": [customer_email]},
            Message={"Subject": {"Data": f"Re: Your Support Request [{ticket_id}]"}, "Body": {"Text": {"Data": body}}},
        )
        return json.dumps({"status": "auto_response_sent", "ticket_id": ticket_id, "message_id": resp["MessageId"]})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


@tool
def route_ticket_to_queue(ticket_id: str, routing: str, priority: str, notes: str = "") -> str:
    """Route a ticket to the appropriate support queue."""
    table_name = os.environ.get("TICKETS_TABLE_NAME")
    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            table.update_item(
                Key={"ticket_id": ticket_id},
                UpdateExpression="SET assigned_queue = :q, priority = :p, routing_notes = :n, routed_at = :t",
                ExpressionAttributeValues={":q": routing, ":p": priority, ":n": notes, ":t": datetime.utcnow().isoformat()},
            )
            return json.dumps({"status": "routed", "ticket_id": ticket_id, "queue": routing, "priority": priority})
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})
    return json.dumps({"status": "simulated_route", "ticket_id": ticket_id, "queue": routing, "priority": priority})


SYSTEM_PROMPT = """You are the Support Automation Agent for Khyzr — a customer support operations specialist.

Your mission is to ensure every customer gets a fast, helpful response and that support resources are focused on high-impact issues.

Support automation capabilities:
- **Classification**: Categorize tickets by topic (auth, API, billing, how-to, bug, etc.)
- **Priority scoring**: Assign P1-P4 priority based on impact, urgency, and customer tier
- **Auto-response**: Send knowledge base articles and initial responses instantly for common questions
- **Intelligent routing**: Route to the right queue/person based on classification and skills
- **SLA monitoring**: Track response times and escalate approaching SLA breaches

Priority definitions:
- **P1**: Production outage, revenue impact, enterprise customer — 1-hour response
- **P2**: Major feature broken, enterprise customer, or urgent business impact — 4-hour response
- **P3**: Non-critical issue, workaround exists — 8-hour response
- **P4**: General questions, how-to requests — 24-hour response

Customer tier treatment:
- Enterprise: Dedicated CSM notified for P1/P2; SLA commitments in contract
- Business: Standard SLAs; flag for CSM review if multiple P1s in 30 days
- Starter: Self-service first; human escalation for P1/P2 only"""


model = BedrockModel(model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"), region_name=os.environ.get("AWS_REGION", "us-east-1"))
agent = Agent(model=model, tools=[fetch_open_tickets, classify_and_prioritize_ticket, auto_respond_ticket, route_ticket_to_queue], system_prompt=SYSTEM_PROMPT)


def run(input_data: dict) -> dict:
    response = agent(input_data.get("message", "Process all open support tickets: classify, prioritize, auto-respond where possible, and route to appropriate queues"))
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {"message": "Process all open support tickets. Classify each, assign priority, send auto-responses for how-to questions, and route P1/P2 tickets to senior engineers immediately."}
    print(json.dumps(run(input_data)))
