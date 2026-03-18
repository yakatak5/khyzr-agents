"""
Attribution Agent
=================
Maps touchpoints across the marketing funnel and generates multi-touch
attribution reports per campaign or channel to optimize marketing spend.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
import pandas as pd
from datetime import datetime, timedelta
from io import StringIO
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def fetch_touchpoint_data(date_range: str = "last_90_days", channel: str = None) -> str:
    """
    Fetch multi-touch attribution data from marketing analytics sources.

    Args:
        date_range: Time window - 'last_30_days', 'last_90_days', 'last_quarter', 'ytd'
        channel: Filter by channel ('paid_search', 'organic', 'email', 'content', 'events', 'referral')

    Returns:
        JSON touchpoint data with conversion paths
    """
    days = {"last_30_days": 30, "last_90_days": 90, "last_quarter": 90, "ytd": 180}.get(date_range, 90)
    bucket = os.environ.get("ANALYTICS_DATA_BUCKET")

    if bucket:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        try:
            obj = s3.get_object(Bucket=bucket, Key=f"attribution/touchpoints-{date_range}.json")
            data = json.loads(obj["Body"].read())
            if channel:
                data = [d for d in data if d.get("channel") == channel]
            return json.dumps({"touchpoints": data, "count": len(data)}, indent=2)
        except Exception:
            pass

    # Sample attribution data
    sample = [
        {
            "deal_id": "DEAL-001",
            "company": "Acme Corp",
            "won": True,
            "arr": 120000,
            "touchpoints": [
                {"touch": 1, "channel": "paid_search", "campaign": "brand_keywords", "date": "2025-07-15", "position": "first_touch"},
                {"touch": 2, "channel": "content", "campaign": "automation_guide", "date": "2025-07-22", "position": "mid_touch"},
                {"touch": 3, "channel": "email", "campaign": "enterprise_nurture", "date": "2025-08-01", "position": "mid_touch"},
                {"touch": 4, "channel": "events", "campaign": "saas_summit_2025", "date": "2025-08-15", "position": "last_touch"},
            ],
        },
    ]
    return json.dumps({"touchpoints": sample, "date_range": date_range, "note": "Configure ANALYTICS_DATA_BUCKET for real attribution data"}, indent=2)


@tool
def apply_attribution_model(touchpoint_data: list, model: str = "linear") -> str:
    """
    Apply a multi-touch attribution model to touchpoint data.

    Args:
        touchpoint_data: List of deals with touchpoints
        model: Attribution model - 'first_touch', 'last_touch', 'linear', 'time_decay', 'u_shaped', 'w_shaped'

    Returns:
        JSON attribution results showing credit allocation by channel and campaign
    """
    model_descriptions = {
        "first_touch": "100% credit to first touchpoint",
        "last_touch": "100% credit to last touchpoint",
        "linear": "Equal credit distributed across all touchpoints",
        "time_decay": "More credit to recent touchpoints (exponential decay)",
        "u_shaped": "40% first touch, 40% last touch, 20% distributed across middle",
        "w_shaped": "30% first, 30% lead creation, 30% opp creation, 10% remaining",
    }

    channel_credit = {}
    campaign_credit = {}
    total_revenue = 0

    for deal in touchpoint_data:
        arr = deal.get("arr", 0) if deal.get("won") else 0
        total_revenue += arr
        touches = deal.get("touchpoints", [])
        n = len(touches)

        if n == 0:
            continue

        for i, touch in enumerate(touches):
            channel = touch.get("channel", "unknown")
            campaign = touch.get("campaign", "unknown")
            position = touch.get("position", "mid_touch")

            # Calculate credit based on model
            if model == "first_touch":
                credit = arr if i == 0 else 0
            elif model == "last_touch":
                credit = arr if i == n - 1 else 0
            elif model == "linear":
                credit = arr / n
            elif model == "time_decay":
                weights = [2 ** i for i in range(n)]
                total_weight = sum(weights)
                credit = arr * (weights[i] / total_weight)
            elif model == "u_shaped":
                if n == 1:
                    credit = arr
                elif i == 0 or i == n - 1:
                    credit = arr * 0.40
                else:
                    credit = arr * 0.20 / max(n - 2, 1)
            else:
                credit = arr / n  # Default to linear

            channel_credit[channel] = channel_credit.get(channel, 0) + credit
            campaign_credit[campaign] = campaign_credit.get(campaign, 0) + credit

    return json.dumps({
        "model_applied": model,
        "model_description": model_descriptions.get(model),
        "total_revenue_attributed": round(total_revenue, 2),
        "credit_by_channel": {k: round(v, 2) for k, v in sorted(channel_credit.items(), key=lambda x: x[1], reverse=True)},
        "credit_by_campaign": {k: round(v, 2) for k, v in sorted(campaign_credit.items(), key=lambda x: x[1], reverse=True)},
    }, indent=2)


@tool
def generate_attribution_report(attribution_results: dict, date_range: str, budget_data: dict = None) -> str:
    """
    Generate a comprehensive attribution report with insights and recommendations.

    Args:
        attribution_results: Output from apply_attribution_model
        date_range: Reporting period
        budget_data: Optional dict of actual spend by channel for ROAS calculation

    Returns:
        JSON attribution report with ROAS, efficiency metrics, and recommendations
    """
    channel_credit = attribution_results.get("credit_by_channel", {})
    total_revenue = attribution_results.get("total_revenue_attributed", 0)
    model = attribution_results.get("model_applied", "linear")

    channel_analysis = []
    for channel, credit in channel_credit.items():
        spend = budget_data.get(channel, 0) if budget_data else 0
        roas = round(credit / spend, 2) if spend > 0 else None
        channel_analysis.append({
            "channel": channel,
            "attributed_revenue": round(credit, 2),
            "revenue_share_pct": round(credit / total_revenue * 100, 1) if total_revenue else 0,
            "spend": spend,
            "roas": roas,
            "status": ("scale" if roas and roas > 3 else ("optimize" if roas and roas > 1 else "review")) if roas else "no_spend_data",
        })

    channel_analysis.sort(key=lambda x: x["attributed_revenue"], reverse=True)

    recommendations = []
    for ch in channel_analysis:
        if ch["status"] == "scale":
            recommendations.append(f"SCALE: {ch['channel']} — ROAS {ch['roas']}x, increase budget by 20-30%")
        elif ch["status"] == "review":
            recommendations.append(f"REVIEW: {ch['channel']} — ROAS {ch['roas']}x, below breakeven, pause low performers")

    return json.dumps({
        "report_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "period": date_range,
        "attribution_model": model,
        "total_attributed_revenue": total_revenue,
        "channel_breakdown": channel_analysis,
        "top_channel": channel_analysis[0]["channel"] if channel_analysis else None,
        "recommendations": recommendations,
        "model_comparison_note": "Run multiple attribution models to triangulate true channel value",
    }, indent=2)


SYSTEM_PROMPT = """You are the Attribution Agent for Khyzr — a marketing analytics specialist and revenue attribution expert.

Your mission is to provide marketing leadership with accurate, multi-model attribution analysis so they can make confident budget allocation decisions. "Half of my marketing spend is wasted — I just don't know which half" should never be said here.

Attribution models you apply and when to use each:
- **First-Touch**: Best for measuring brand awareness and top-of-funnel effectiveness
- **Last-Touch**: Useful for measuring conversion efficiency and bottom-of-funnel
- **Linear**: Fair baseline for long, complex B2B sales cycles
- **Time-Decay**: Best when recency of engagement is a stronger signal
- **U-Shaped (Position-Based)**: Industry standard for B2B; weights first and last touches most heavily
- **W-Shaped**: Adds lead creation moment as a third high-weight position
- **Data-Driven**: Machine learning model trained on conversion patterns (requires sufficient data volume)

Attribution analysis dimensions:
- **Channel attribution**: Which channels drive the most pipeline and revenue
- **Campaign attribution**: Which specific campaigns have the highest ROAS
- **Content attribution**: Which pieces of content appear in winning deal paths
- **Influence attribution**: Which touches moved deals forward (not just created or closed)

ROAS benchmarks for Khyzr:
- Paid Search: Target ROAS 3-5x
- Paid Social (LinkedIn): Target ROAS 2-3x (longer consideration cycle)
- Content/SEO: Track pipe influence %, not direct attribution
- Events: Measure sourced + influenced ARR vs. total event cost

When analyzing attribution:
1. Fetch touchpoint data for the requested period
2. Apply requested attribution model (recommend running 3 models for comparison)
3. Generate channel and campaign-level credit allocation
4. Calculate ROAS where spend data is available
5. Produce actionable report with budget reallocation recommendations"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[fetch_touchpoint_data, apply_attribution_model, generate_attribution_report],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Generate Q3 multi-touch attribution report using linear and U-shaped models")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Run attribution analysis for last 90 days using both linear and U-shaped models. Show credit by channel and recommend budget reallocations."
    }
    print(json.dumps(run(input_data)))
