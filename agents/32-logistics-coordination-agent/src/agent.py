"""
Logistics Coordination Agent
=============================
Integrates carrier data to provide real-time shipment visibility and automatically escalates delays.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime
import httpx
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def track_shipments(status_filter: str = "in_transit", limit: int = 50) -> str:
    """Fetch active shipment tracking data from carrier APIs or TMS."""
    import httpx
    
    table_name = os.environ.get("SHIPMENTS_TABLE_NAME")
    if table_name:
        import boto3
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            params = {"Limit": limit}
            if status_filter != "all":
                params["FilterExpression"] = "#s = :s"
                params["ExpressionAttributeNames"] = {"#s": "status"}
                params["ExpressionAttributeValues"] = {":s": status_filter}
            resp = table.scan(**params)
            return json.dumps({"shipments": resp.get("Items", [])}, indent=2)
        except Exception:
            pass
    
    from datetime import timedelta
    shipments = [
        {"shipment_id": "SHP-001", "carrier": "FedEx", "tracking_number": "789012345678", "origin": "Chicago, IL", "destination": "New York, NY", "status": "in_transit", "expected_delivery": (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d"), "last_update": datetime.utcnow().isoformat(), "days_delayed": 0, "customer_id": "CUST-001"},
        {"shipment_id": "SHP-002", "carrier": "UPS", "tracking_number": "1Z999AA10123456784", "origin": "Los Angeles, CA", "destination": "Seattle, WA", "status": "delayed", "expected_delivery": (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d"), "last_update": (datetime.utcnow() - timedelta(hours=48)).isoformat(), "days_delayed": 2, "delay_reason": "Weather disruption", "customer_id": "CUST-002"},
        {"shipment_id": "SHP-003", "carrier": "DHL", "tracking_number": "JD014600009976589118", "origin": "Frankfurt, DE", "destination": "Boston, MA", "status": "customs_hold", "expected_delivery": (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%d"), "last_update": (datetime.utcnow() - timedelta(hours=36)).isoformat(), "days_delayed": 1, "delay_reason": "Customs inspection", "customer_id": "CUST-003"},
    ]
    
    if status_filter != "all":
        shipments = [s for s in shipments if s["status"] == status_filter or status_filter in s["status"]]
    
    return json.dumps({"shipments": shipments[:limit], "total": len(shipments), "note": "Configure SHIPMENTS_TABLE_NAME for real TMS data"}, indent=2)


@tool
def detect_shipment_delays(shipments: list) -> str:
    """Detect delayed shipments and classify by severity."""
    from datetime import timedelta
    
    delayed = []
    today = datetime.utcnow().date()
    
    for s in shipments:
        days_delayed = s.get("days_delayed", 0)
        status = s.get("status", "")
        
        # Check if expected delivery has passed
        expected_str = s.get("expected_delivery")
        if expected_str:
            expected = datetime.strptime(expected_str, "%Y-%m-%d").date()
            if expected < today and days_delayed == 0:
                days_delayed = (today - expected).days
        
        hours_no_update = 0
        last_update_str = s.get("last_update")
        if last_update_str:
            last_update = datetime.fromisoformat(last_update_str)
            hours_no_update = (datetime.utcnow() - last_update).total_seconds() / 3600
        
        if days_delayed > 0 or status in ["delayed", "customs_hold", "exception"] or hours_no_update > 24:
            severity = "CRITICAL" if days_delayed > 3 else ("HIGH" if days_delayed >= 1 or hours_no_update > 24 else "MEDIUM")
            delayed.append({
                **s,
                "days_delayed": days_delayed,
                "hours_since_update": round(hours_no_update, 1),
                "severity": severity,
                "requires_escalation": severity in ["CRITICAL", "HIGH"],
            })
    
    delayed.sort(key=lambda x: ["CRITICAL", "HIGH", "MEDIUM"].index(x["severity"]))
    return json.dumps({"delayed_shipments": delayed, "count": len(delayed), "critical": sum(1 for d in delayed if d["severity"] == "CRITICAL"), "analyzed_at": datetime.utcnow().isoformat()}, indent=2)


@tool
def escalate_delay(shipment: dict, notification_emails: list) -> str:
    """Send delay escalation notification to relevant stakeholders."""
    sender = os.environ.get("SES_SENDER_EMAIL", "")
    if not sender:
        return json.dumps({"status": "skipped", "note": "Configure SES_SENDER_EMAIL"})
    
    severity = shipment.get("severity", "HIGH")
    severity_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡"}.get(severity, "🟡")
    
    subject = f"{severity_emoji} [{severity}] Shipment Delay: {shipment.get('shipment_id')} — {shipment.get('carrier')}"
    body = f"""SHIPMENT DELAY NOTIFICATION

Shipment: {shipment.get("shipment_id")}
Carrier: {shipment.get("carrier")} | Tracking: {shipment.get("tracking_number")}
Route: {shipment.get("origin")} → {shipment.get("destination")}
Customer: {shipment.get("customer_id")}

Delay: {shipment.get("days_delayed", 0)} day(s)
Reason: {shipment.get("delay_reason", "Unknown")}
Last Update: {shipment.get("last_update")}

REQUIRED ACTIONS:
- Contact carrier for updated ETA
- Notify customer/stakeholder of revised delivery
- Consider alternative routing if CRITICAL

Generated by Khyzr Logistics Coordination Agent — {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}"""
    
    import boto3
    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    results = []
    for email in notification_emails:
        try:
            resp = ses.send_email(Source=sender, Destination={"ToAddresses": [email]}, Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}})
            results.append({"email": email, "status": "sent"})
        except Exception as e:
            results.append({"email": email, "status": "failed", "error": str(e)})
    
    return json.dumps({"escalation_sent": True, "notifications": results}, indent=2)


@tool
def update_shipment_eta(shipment_id: str, new_eta: str, reason: str) -> str:
    """Update shipment ETA in the tracking system."""
    table_name = os.environ.get("SHIPMENTS_TABLE_NAME")
    if table_name:
        import boto3
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            table.update_item(
                Key={"shipment_id": shipment_id},
                UpdateExpression="SET expected_delivery = :eta, delay_reason = :r, last_update = :t",
                ExpressionAttributeValues={":eta": new_eta, ":r": reason, ":t": datetime.utcnow().isoformat()},
            )
            return json.dumps({"status": "updated", "shipment_id": shipment_id, "new_eta": new_eta})
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})
    return json.dumps({"status": "skipped", "note": "Configure SHIPMENTS_TABLE_NAME"})


SYSTEM_PROMPT = """You are the Logistics Coordination Agent for Khyzr — a supply chain logistics specialist and carrier management expert.

Your mission is to provide real-time visibility into all shipments and proactively manage exceptions before they impact operations or customer commitments.

Logistics monitoring scope:
- **Inbound freight**: Raw materials and components from suppliers
- **Outbound freight**: Customer shipments and deliveries
- **Intercompany transfers**: Between distribution centers and warehouses
- **Last-mile delivery**: Final customer delivery tracking

Exception categories:
- **Critical**: Shipment >3 days late AND impacts production or customer commitment
- **High**: Shipment 1-3 days late OR carrier hasn't updated status in 24+ hours
- **Medium**: Minor delay (<1 day) with carrier-provided reason
- **Informational**: On-time shipments with proactive status updates

Carrier integrations:
- FedEx, UPS, DHL, USPS via tracking APIs
- Freight carriers via EDI 214 (transportation status) messages
- Port/customs status via CBP APIs
- Ocean freight via container tracking APIs

Escalation protocols:
- **Critical delay to customer**: Notify Account Manager + CSM + Operations Director within 1 hour
- **Production impact**: Notify Plant Manager + Procurement + Supply Chain VP
- **Carrier issue**: Open escalation with carrier account rep; consider alternative routing
- **Force majeure**: Escalate to executive team; activate backup supplier/carrier"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[track_shipments, detect_shipment_delays, escalate_delay, update_shipment_eta],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Run logistics coordination task")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Check all active shipments for delays and escalate any critical issues"
    }
    print(json.dumps(run(input_data)))
