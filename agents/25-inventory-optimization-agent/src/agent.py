"""
Inventory Optimization Agent
==============================
Monitors stock levels, triggers reorder alerts, and optimizes safety stock
based on lead times and demand variability.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
import pandas as pd
import numpy as np
from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def get_current_inventory(warehouse_id: str = None) -> str:
    """Fetch current inventory levels from warehouse management system."""
    table_name = os.environ.get("INVENTORY_TABLE_NAME")
    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            params = {}
            if warehouse_id:
                params["FilterExpression"] = "warehouse_id = :w"
                params["ExpressionAttributeValues"] = {":w": warehouse_id}
            resp = table.scan(**params)
            return json.dumps({"items": resp.get("Items", []), "warehouse": warehouse_id}, indent=2)
        except Exception as e:
            pass
    
    sample_inventory = [
        {"sku": "SKU-001", "name": "Widget A", "quantity_on_hand": 850, "reorder_point": 200, "max_stock": 2000, "unit_cost": 12.50, "lead_time_days": 14},
        {"sku": "SKU-002", "name": "Widget B", "quantity_on_hand": 45, "reorder_point": 150, "max_stock": 1000, "unit_cost": 28.00, "lead_time_days": 21},
        {"sku": "SKU-003", "name": "Component X", "quantity_on_hand": 2400, "reorder_point": 500, "max_stock": 5000, "unit_cost": 3.75, "lead_time_days": 7},
    ]
    return json.dumps({"items": sample_inventory, "note": "Configure INVENTORY_TABLE_NAME for real WMS data"}, indent=2)


@tool
def calculate_optimal_safety_stock(sku: str, avg_daily_demand: float, demand_std: float, lead_time_days: int, service_level: float = 0.95) -> str:
    """
    Calculate optimal safety stock for a SKU using statistical method.

    Args:
        sku: Product identifier
        avg_daily_demand: Average daily demand units
        demand_std: Standard deviation of daily demand
        lead_time_days: Supplier lead time in days
        service_level: Target service level (0.95 = 95%)

    Returns:
        JSON safety stock calculation with reorder point
    """
    # Z-score for service level
    z_scores = {0.90: 1.28, 0.95: 1.65, 0.99: 2.33}
    z = z_scores.get(service_level, 1.65)
    
    # Safety stock = Z * sqrt(lead_time) * demand_std
    safety_stock = z * np.sqrt(lead_time_days) * demand_std
    reorder_point = avg_daily_demand * lead_time_days + safety_stock
    max_stock = reorder_point + (avg_daily_demand * 30)  # 30-day cycle
    
    holding_cost_daily = 0.25 / 365  # 25% annual holding cost
    
    return json.dumps({
        "sku": sku,
        "avg_daily_demand": avg_daily_demand,
        "demand_std": demand_std,
        "lead_time_days": lead_time_days,
        "service_level": service_level,
        "z_score": z,
        "optimal_safety_stock": round(safety_stock),
        "reorder_point": round(reorder_point),
        "recommended_max_stock": round(max_stock),
        "monthly_holding_cost": round(safety_stock * 0.25 / 12, 2),
    }, indent=2)


@tool
def generate_reorder_alerts(inventory_items: list) -> str:
    """
    Scan inventory items and generate reorder alerts for items below threshold.

    Args:
        inventory_items: List of inventory records

    Returns:
        JSON list of reorder alerts sorted by urgency
    """
    alerts = []
    for item in inventory_items:
        qty = item.get("quantity_on_hand", 0)
        rop = item.get("reorder_point", 0)
        lead = item.get("lead_time_days", 14)
        
        if qty <= 0:
            urgency = "CRITICAL"
            message = "OUT OF STOCK — immediate emergency procurement required"
        elif qty < rop * 0.5:
            urgency = "HIGH"
            message = f"Below 50% of reorder point — order immediately, {lead} day lead time"
        elif qty < rop:
            urgency = "MEDIUM"
            message = f"Below reorder point — place order within 48 hours"
        elif qty < rop * 1.2:
            urgency = "LOW"
            message = f"Approaching reorder point — plan purchase in next week"
        else:
            continue
        
        alerts.append({
            "sku": item.get("sku"),
            "name": item.get("name"),
            "quantity_on_hand": qty,
            "reorder_point": rop,
            "urgency": urgency,
            "message": message,
            "recommended_order_qty": max(0, item.get("max_stock", rop * 5) - qty),
        })
    
    alerts.sort(key=lambda x: ["CRITICAL", "HIGH", "MEDIUM", "LOW"].index(x["urgency"]))
    return json.dumps({"alerts": alerts, "total_alerts": len(alerts), "critical": sum(1 for a in alerts if a["urgency"] == "CRITICAL"), "generated_at": datetime.utcnow().isoformat()}, indent=2)


@tool
def send_reorder_notification(alerts: list, recipients: list) -> str:
    """Send reorder alert notifications via SES."""
    if not alerts:
        return json.dumps({"status": "no_alerts", "message": "All inventory levels healthy"})
    
    sender = os.environ.get("SES_SENDER_EMAIL", "")
    if not sender:
        return json.dumps({"status": "skipped", "alerts_count": len(alerts), "note": "Configure SES_SENDER_EMAIL to enable notifications"})
    
    critical = [a for a in alerts if a["urgency"] == "CRITICAL"]
    high = [a for a in alerts if a["urgency"] == "HIGH"]
    
    subject = f"🚨 Inventory Alert: {len(critical)} Critical, {len(high)} High Priority Items"
    body_lines = [f"Inventory Reorder Alert — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", ""]
    for a in alerts[:10]:
        body_lines.append(f"[{a['urgency']}] {a['sku']} ({a['name']}): {a['quantity_on_hand']} units — {a['message']}")
    
    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    results = []
    for email in recipients:
        try:
            resp = ses.send_email(
                Source=sender,
                Destination={"ToAddresses": [email]},
                Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": chr(10).join(body_lines)}}},
            )
            results.append({"email": email, "status": "sent"})
        except Exception as e:
            results.append({"email": email, "status": "failed", "error": str(e)})
    
    return json.dumps({"notifications_sent": len([r for r in results if r["status"] == "sent"]), "details": results}, indent=2)


SYSTEM_PROMPT = """You are the Inventory Optimization Agent for Khyzr — a supply chain operations specialist and inventory management expert.

Your mission is to ensure the right amount of stock is always available: enough to meet demand without excess inventory that ties up capital and incurs holding costs.

Inventory management principles:
- **Safety Stock**: Buffer stock calculated using demand variability and lead time uncertainty
- **Reorder Point**: The inventory level that triggers a new purchase order = (avg daily demand × lead time) + safety stock
- **Economic Order Quantity (EOQ)**: Optimal order size balancing ordering cost vs. holding cost
- **ABC Analysis**: Focus optimization effort on A items (high value), use simpler rules for C items
- **Service Level**: Typically target 95-99% for A items, 90-95% for B/C items

Monitoring cadence:
- Real-time: Track inventory transactions and update quantities
- Daily: Scan for items crossing reorder points; generate alerts
- Weekly: Review safety stock levels against actual demand variability
- Monthly: Review ABC classification and update service level targets

Alert escalation:
- **Critical (0 units)**: Notify procurement + operations manager immediately; consider emergency suppliers
- **High (<50% of ROP)**: Notify procurement — order within same business day
- **Medium (at ROP)**: Standard purchase order process — 48-hour response window
- **Low (approaching ROP)**: Planning flag — no immediate action required"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[get_current_inventory, calculate_optimal_safety_stock, generate_reorder_alerts, send_reorder_notification],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Check inventory levels, generate reorder alerts, and calculate optimal safety stocks")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Scan all inventory levels, identify items below reorder point, calculate optimal safety stocks, and send alerts to procurement@company.com"
    }
    print(json.dumps(run(input_data)))
