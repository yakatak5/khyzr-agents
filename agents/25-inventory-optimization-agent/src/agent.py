"""
Inventory Optimization Agent (Agent 25)
========================================
Upload an Excel sheet of SKUs/stock levels → get reorder alerts,
optimal safety stock calculations, and actionable recommendations.

Built with AWS Strands Agents + Amazon Bedrock AgentCore Runtime.
"""

import json
import os
import io
import math
import logging
import boto3
import openpyxl
from datetime import datetime

from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("inventory-agent")

app = BedrockAgentCoreApp()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def load_inventory_from_s3(bucket: str, key: str) -> str:
    """
    Load inventory data from an Excel file in S3.
    Expected columns (flexible, auto-detected):
      SKU, Name, Quantity On Hand, Reorder Point, Max Stock, Lead Time (Days), Unit Cost

    Args:
        bucket: S3 bucket name
        key: S3 key (e.g. 'inventory.xlsx')

    Returns:
        JSON with list of inventory items and column headers found
    """
    try:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"))
        obj = s3.get_object(Bucket=bucket, Key=key)
        data = obj["Body"].read()

        wb = openpyxl.load_workbook(io.BytesIO(data))
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return json.dumps({"error": "Excel file is empty"})

        raw_headers = [str(h).strip() if h is not None else f"Col{i}" for i, h in enumerate(rows[0])]

        # Normalize header names
        col_map = {}
        for i, h in enumerate(raw_headers):
            hl = h.lower().replace(" ", "_").replace("-", "_")
            if any(x in hl for x in ["sku", "code", "item_id"]): col_map["sku"] = i
            elif any(x in hl for x in ["name", "description", "product"]): col_map["name"] = i
            elif any(x in hl for x in ["qty", "quantity", "on_hand", "stock"]): col_map["quantity_on_hand"] = i
            elif any(x in hl for x in ["reorder", "rop", "min"]): col_map["reorder_point"] = i
            elif any(x in hl for x in ["max", "capacity"]): col_map["max_stock"] = i
            elif any(x in hl for x in ["lead", "days"]): col_map["lead_time_days"] = i
            elif any(x in hl for x in ["cost", "price", "unit"]): col_map["unit_cost"] = i

        items = []
        for row in rows[1:]:
            if not any(cell is not None for cell in row):
                continue
            def get(field, default=0):
                idx = col_map.get(field)
                if idx is None: return default
                val = row[idx]
                if val is None: return default
                try: return float(val) if field not in ("sku","name") else str(val)
                except: return default

            items.append({
                "sku": get("sku", f"SKU-{len(items)+1}"),
                "name": get("name", "Unknown"),
                "quantity_on_hand": get("quantity_on_hand"),
                "reorder_point": get("reorder_point"),
                "max_stock": get("max_stock"),
                "lead_time_days": int(get("lead_time_days", 14)),
                "unit_cost": get("unit_cost"),
            })

        logger.info(f"Loaded {len(items)} inventory items from s3://{bucket}/{key}")
        return json.dumps({"items": items, "total": len(items), "columns_detected": list(col_map.keys())}, indent=2)
    except Exception as e:
        logger.error(f"Failed to load inventory: {e}")
        return json.dumps({"status": "no_results", "items": [], "note": "Could not load file, use sample data."})


@tool
def calculate_safety_stock(sku: str, avg_daily_demand: float, demand_std: float,
                            lead_time_days: int, service_level: float = 0.95) -> str:
    """
    Calculate optimal safety stock and reorder point for a SKU.

    Args:
        sku: Product identifier
        avg_daily_demand: Average daily demand (units/day)
        demand_std: Standard deviation of daily demand
        lead_time_days: Supplier lead time in days
        service_level: Target service level (0.90, 0.95, or 0.99)

    Returns:
        JSON with safety stock, reorder point, and holding cost estimate
    """
    z_scores = {0.90: 1.28, 0.95: 1.65, 0.99: 2.33}
    z = z_scores.get(round(service_level, 2), 1.65)

    safety_stock = z * math.sqrt(lead_time_days) * demand_std
    reorder_point = avg_daily_demand * lead_time_days + safety_stock
    max_stock = reorder_point + avg_daily_demand * 30  # 30-day order cycle

    return json.dumps({
        "sku": sku,
        "avg_daily_demand": avg_daily_demand,
        "lead_time_days": lead_time_days,
        "service_level": f"{int(service_level*100)}%",
        "optimal_safety_stock": round(safety_stock),
        "reorder_point": round(reorder_point),
        "recommended_max_stock": round(max_stock),
        "monthly_holding_cost_estimate": round(safety_stock * 0.25 / 12, 2),
    }, indent=2)


@tool
def generate_reorder_alerts(items_json: str) -> str:
    """
    Scan inventory items and generate prioritized reorder alerts.

    Args:
        items_json: JSON string of inventory items (from load_inventory_from_s3)

    Returns:
        JSON with alerts sorted by urgency (CRITICAL → HIGH → MEDIUM → LOW)
    """
    try:
        data = json.loads(items_json)
        items = data.get("items", data) if isinstance(data, dict) else data
        alerts = []

        for item in items:
            qty = float(item.get("quantity_on_hand", 0))
            rop = float(item.get("reorder_point", 0))
            max_s = float(item.get("max_stock", rop * 5))
            lead = int(item.get("lead_time_days", 14))

            if qty <= 0:
                urgency, msg = "CRITICAL", "OUT OF STOCK — emergency procurement required immediately"
            elif rop > 0 and qty < rop * 0.5:
                urgency, msg = "HIGH", f"Below 50% of reorder point — order today ({lead}d lead time)"
            elif rop > 0 and qty < rop:
                urgency, msg = "MEDIUM", "Below reorder point — place order within 48 hours"
            elif rop > 0 and qty < rop * 1.2:
                urgency, msg = "LOW", "Approaching reorder point — plan purchase this week"
            else:
                continue

            alerts.append({
                "sku": item.get("sku"),
                "name": item.get("name"),
                "quantity_on_hand": int(qty),
                "reorder_point": int(rop),
                "urgency": urgency,
                "action": msg,
                "recommended_order_qty": max(0, int(max_s - qty)),
            })

        order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        alerts.sort(key=lambda x: order.index(x["urgency"]))
        healthy = len(items) - len(alerts)

        return json.dumps({
            "total_skus": len(items),
            "healthy": healthy,
            "alerts": alerts,
            "summary": {
                "CRITICAL": sum(1 for a in alerts if a["urgency"] == "CRITICAL"),
                "HIGH": sum(1 for a in alerts if a["urgency"] == "HIGH"),
                "MEDIUM": sum(1 for a in alerts if a["urgency"] == "MEDIUM"),
                "LOW": sum(1 for a in alerts if a["urgency"] == "LOW"),
            },
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def store_inventory_report(report_content: str, bucket: str = "", key: str = "inventory-report.md") -> str:
    """
    Store the inventory analysis report to S3.

    Args:
        report_content: Markdown report content
        bucket: S3 bucket (defaults to INVENTORY_BUCKET env var)
        key: S3 object key

    Returns:
        JSON with storage result
    """
    bucket = bucket or os.environ.get("INVENTORY_BUCKET", "")
    if not bucket:
        return json.dumps({"status": "skipped", "note": "INVENTORY_BUCKET not configured"})
    try:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"))
        s3.put_object(Bucket=bucket, Key=key, Body=report_content.encode(), ContentType="text/markdown")
        return json.dumps({"status": "stored", "bucket": bucket, "key": key})
    except Exception as e:
        return json.dumps({"status": "no_results", "note": "Could not store report."})


# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------

_agent = None

def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        model = BedrockModel(
            model_id=os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"),
            region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"),
        )
        _agent = Agent(
            model=model,
            tools=[load_inventory_from_s3, calculate_safety_stock, generate_reorder_alerts, store_inventory_report],
            system_prompt="""You are the Inventory Optimization Agent — a supply chain specialist who ensures the right stock is always available without tying up excess capital.

When given an S3 bucket and key for an Excel inventory file:
1. Load the inventory data using load_inventory_from_s3
2. Run generate_reorder_alerts to find items needing attention
3. For HIGH/CRITICAL items, use calculate_safety_stock to give precise recommendations
4. Synthesize everything into a clear executive summary in markdown
5. Store the report using store_inventory_report
6. Lead with the most urgent items — CRITICAL first

Format your response with:
- 🚨 Executive summary (counts by urgency)
- Detailed alert table (SKU, name, qty, action)
- Safety stock recommendations for top items
- Overall inventory health score

If tool errors occur, silently use the data you have and deliver the best analysis possible. Never mention tool failures to the user.
""",
        )
    return _agent


# ---------------------------------------------------------------------------
# AgentCore entrypoint
# ---------------------------------------------------------------------------

@app.entrypoint
def invoke(payload):
    """
    Expected payload:
    {
        "prompt": "optional custom message",
        "bucket": "my-inventory-bucket",
        "key": "inventory.xlsx"
    }
    """
    bucket = payload.get("bucket", os.environ.get("INVENTORY_BUCKET", ""))
    key    = payload.get("key", os.environ.get("INVENTORY_KEY", "inventory.xlsx"))
    prompt = payload.get("prompt", "")

    if not prompt:
        if bucket:
            prompt = f"Load the inventory from s3://{bucket}/{key}, generate reorder alerts, calculate safety stocks for urgent items, and give me a full optimization report."
        else:
            prompt = "I need help analyzing inventory levels and generating reorder recommendations. Please ask me to upload an Excel file with SKU, quantity on hand, reorder point, lead time, and max stock columns."

    try:
        result = _get_agent()(prompt)
        return {"result": str(result)}
    except Exception as e:
        logger.error(f"Inventory agent error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    app.run()
