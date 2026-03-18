"""
Cash Flow Agent
===============
Synthesizes AR aging, AP schedules, and historical patterns to produce
rolling 13-week cash flow forecasts with variance analysis.

Built with AWS Strands Agents + AgentCore on AWS Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def fetch_ar_schedule(weeks_ahead: int = 13) -> str:
    """
    Fetch expected AR cash collections schedule based on invoice due dates and collection patterns.

    Args:
        weeks_ahead: Number of weeks to project AR collections (default 13)

    Returns:
        JSON string with weekly expected cash inflows from AR
    """
    today = datetime.utcnow()
    weeks = []
    base_collections = [
        185000, 210000, 195000, 225000, 180000, 215000, 200000,
        230000, 195000, 220000, 185000, 210000, 200000
    ]

    for i in range(min(weeks_ahead, 13)):
        week_start = today + timedelta(weeks=i)
        collection = base_collections[i] if i < len(base_collections) else 200000
        confidence = 0.95 - (i * 0.02)  # Confidence decreases for further weeks

        weeks.append({
            "week": i + 1,
            "week_start": week_start.strftime("%Y-%m-%d"),
            "week_end": (week_start + timedelta(days=6)).strftime("%Y-%m-%d"),
            "expected_collections": collection,
            "confidence": round(max(0.70, confidence), 2),
            "composition": {
                "current_due": round(collection * 0.65, 2),
                "30_60_day_recovery": round(collection * 0.25, 2),
                "90_plus_recovery": round(collection * 0.10, 2),
            },
        })

    return json.dumps({
        "ar_collection_schedule": weeks,
        "total_expected_13_week": sum(w["expected_collections"] for w in weeks),
        "avg_weekly_collections": sum(w["expected_collections"] for w in weeks) / len(weeks),
        "current_ar_balance": 1847500.00,
        "generated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def fetch_ap_schedule(weeks_ahead: int = 13) -> str:
    """
    Fetch scheduled AP payments and known cash outflows for the forecast period.

    Args:
        weeks_ahead: Number of weeks to project AP payments

    Returns:
        JSON string with weekly expected cash outflows including AP, payroll, and fixed costs
    """
    today = datetime.utcnow()
    weeks = []
    base_payables = [
        165000, 142000, 188000, 155000, 310000, 148000, 162000,
        175000, 140000, 195000, 158000, 310000, 155000
    ]
    # Payroll weeks (every 2 weeks add $95K)
    payroll_weeks = {1, 3, 5, 7, 9, 11, 13}

    for i in range(min(weeks_ahead, 13)):
        week_start = today + timedelta(weeks=i)
        week_num = i + 1
        ap_payment = base_payables[i] if i < len(base_payables) else 165000
        payroll = 95000 if week_num in payroll_weeks else 0

        total_outflows = ap_payment + payroll

        weeks.append({
            "week": week_num,
            "week_start": week_start.strftime("%Y-%m-%d"),
            "week_end": (week_start + timedelta(days=6)).strftime("%Y-%m-%d"),
            "total_outflows": total_outflows,
            "breakdown": {
                "ap_payments": ap_payment,
                "payroll": payroll,
                "fixed_overhead": 22000,  # rent, utilities, subscriptions
                "debt_service": 18500 if week_num in {4, 8, 12} else 0,
            },
        })
        # Adjust total to include fixed overhead
        weeks[-1]["total_outflows"] = ap_payment + payroll + 22000 + weeks[-1]["breakdown"]["debt_service"]

    return json.dumps({
        "ap_payment_schedule": weeks,
        "total_expected_13_week_outflows": sum(w["total_outflows"] for w in weeks),
        "avg_weekly_outflows": sum(w["total_outflows"] for w in weeks) / len(weeks),
        "current_ap_balance": 485000.00,
        "generated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def analyze_historical_cashflow(lookback_weeks: int = 13) -> str:
    """
    Analyze historical cash flow patterns to identify seasonality and trends for forecasting.

    Args:
        lookback_weeks: Number of weeks of historical data to analyze

    Returns:
        JSON string with historical averages, variance, seasonality factors, and trend direction
    """
    # In production: queries accounting system or data warehouse
    historical = {
        "lookback_weeks": lookback_weeks,
        "historical_averages": {
            "avg_weekly_inflows": 204615,
            "avg_weekly_outflows": 189230,
            "avg_weekly_net": 15385,
        },
        "variance_analysis": {
            "inflow_std_dev": 18500,
            "outflow_std_dev": 42000,  # Higher variance due to payroll cycles
            "inflow_coefficient_of_variation": 0.090,
            "outflow_coefficient_of_variation": 0.222,
        },
        "seasonality_factors": {
            "q1_inflow_factor": 0.92,   # Q1 typically slower collections
            "q2_inflow_factor": 1.05,
            "q3_inflow_factor": 1.08,
            "q4_inflow_factor": 1.15,   # Year-end strong
            "month_end_spike": True,
            "quarter_end_spike": True,
        },
        "trend": {
            "direction": "improving",
            "weekly_growth_rate": 0.012,  # 1.2% weekly growth in net cash flow
            "13_week_trend": "+18.4%",
        },
        "cash_conversion_cycle_days": 42,
        "dso_days": 38,
        "dpo_days": 31,
        "analyzed_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(historical, indent=2)


@tool
def build_13week_forecast(ar_schedule: str, ap_schedule: str, historical_data: str,
                           opening_cash_balance: float) -> str:
    """
    Build the rolling 13-week cash flow forecast combining AR, AP, and historical patterns.

    Args:
        ar_schedule: JSON string from fetch_ar_schedule
        ap_schedule: JSON string from fetch_ap_schedule
        historical_data: JSON string from analyze_historical_cashflow
        opening_cash_balance: Current cash balance to start the forecast

    Returns:
        JSON string with complete 13-week forecast including base/bull/bear scenarios
    """
    try:
        ar = json.loads(ar_schedule)
        ap = json.loads(ap_schedule)
        hist = json.loads(historical_data)
    except Exception as e:
        return json.dumps({"error": str(e)})

    ar_weeks = {w["week"]: w for w in ar.get("ar_collection_schedule", [])}
    ap_weeks = {w["week"]: w for w in ap.get("ap_payment_schedule", [])}

    forecast_weeks = []
    running_cash = opening_cash_balance
    inflow_std = hist.get("variance_analysis", {}).get("inflow_std_dev", 18500)
    outflow_std = hist.get("variance_analysis", {}).get("outflow_std_dev", 42000)

    for week_num in range(1, 14):
        ar_week = ar_weeks.get(week_num, {})
        ap_week = ap_weeks.get(week_num, {})

        inflows = ar_week.get("expected_collections", 200000)
        outflows = ap_week.get("total_outflows", 189000)
        net = inflows - outflows
        running_cash += net

        # Scenario analysis using historical std dev
        bull_net = (inflows + inflow_std * 0.5) - (outflows - outflow_std * 0.5)
        bear_net = (inflows - inflow_std * 0.5) - (outflows + outflow_std * 0.5)

        forecast_weeks.append({
            "week": week_num,
            "week_start": ar_week.get("week_start", ""),
            "base_case": {
                "inflows": inflows,
                "outflows": outflows,
                "net_cash_flow": round(net, 2),
                "ending_cash_balance": round(running_cash, 2),
            },
            "bull_case_net": round(bull_net, 2),
            "bear_case_net": round(bear_net, 2),
            "cash_at_risk": round(running_cash - (outflows + inflow_std), 2),
            "minimum_cash_coverage": running_cash > 0,
        })

    # Identify cash gap weeks
    cash_gap_weeks = [w["week"] for w in forecast_weeks if not w["minimum_cash_coverage"]]

    return json.dumps({
        "forecast_type": "13-Week Rolling Cash Flow Forecast",
        "opening_cash_balance": opening_cash_balance,
        "forecast_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "weekly_forecast": forecast_weeks,
        "summary": {
            "total_projected_inflows": sum(w["base_case"]["inflows"] for w in forecast_weeks),
            "total_projected_outflows": sum(w["base_case"]["outflows"] for w in forecast_weeks),
            "net_13_week_cash_change": sum(w["base_case"]["net_cash_flow"] for w in forecast_weeks),
            "ending_13_week_balance": forecast_weeks[-1]["base_case"]["ending_cash_balance"] if forecast_weeks else 0,
            "minimum_balance_week": min(forecast_weeks, key=lambda w: w["base_case"]["ending_cash_balance"])["week"] if forecast_weeks else None,
            "minimum_balance_amount": min(w["base_case"]["ending_cash_balance"] for w in forecast_weeks) if forecast_weeks else 0,
            "cash_gap_weeks": cash_gap_weeks,
            "liquidity_risk": len(cash_gap_weeks) > 0,
        },
        "generated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def generate_cashflow_report(forecast_data: str, historical_data: str) -> str:
    """
    Generate the final cash flow forecast report with executive narrative and S3 storage.

    Args:
        forecast_data: JSON string from build_13week_forecast
        historical_data: JSON string from analyze_historical_cashflow

    Returns:
        JSON string with report content and S3 URI
    """
    try:
        forecast = json.loads(forecast_data)
        hist = json.loads(historical_data)
    except Exception as e:
        return json.dumps({"error": str(e)})

    summary = forecast.get("summary", {})
    liquidity_risk = summary.get("liquidity_risk", False)
    min_balance = summary.get("minimum_balance_amount", 0)
    net_change = summary.get("net_13_week_cash_change", 0)

    report_content = f"""# 13-Week Rolling Cash Flow Forecast
**Generated:** {datetime.utcnow().strftime("%B %d, %Y")}
**Prepared by:** Khyzr Cash Flow Agent

## Executive Summary

{"⚠️ LIQUIDITY ALERT: Cash balance projected to fall below zero in weeks: " + str(summary.get("cash_gap_weeks")) if liquidity_risk else "✅ No liquidity gaps identified in the 13-week forecast window."}

| Metric | Value |
|--------|-------|
| Opening Cash Balance | ${forecast.get("opening_cash_balance", 0):,.0f} |
| Total Projected Inflows | ${summary.get("total_projected_inflows", 0):,.0f} |
| Total Projected Outflows | ${summary.get("total_projected_outflows", 0):,.0f} |
| Net Cash Change | ${net_change:,.0f} |
| Minimum Balance (Week {summary.get("minimum_balance_week", "N/A")}) | ${min_balance:,.0f} |

## Trend Analysis
- Historical trend: {hist.get("trend", {}).get("direction", "stable")} ({hist.get("trend", {}).get("13_week_trend", "N/A")})
- Cash Conversion Cycle: {hist.get("cash_conversion_cycle_days", "N/A")} days
- DSO: {hist.get("dso_days", "N/A")} days | DPO: {hist.get("dpo_days", "N/A")} days

## Weekly Forecast Detail
See attached JSON for full weekly breakdown.
"""

    bucket = os.environ.get("REPORTS_BUCKET", "khyzr-cashflow-reports")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    key = f"13-week-forecast/{timestamp}.md"

    try:
        s3.put_object(Bucket=bucket, Key=key, Body=report_content.encode("utf-8"), ContentType="text/markdown")
        s3_uri = f"s3://{bucket}/{key}"
    except Exception as e:
        s3_uri = f"error: {str(e)}"

    return json.dumps({
        "report_saved": True,
        "s3_uri": s3_uri,
        "report_summary": summary,
        "liquidity_risk_flag": liquidity_risk,
        "report_content_preview": report_content[:500],
        "generated_at": datetime.utcnow().isoformat(),
    }, indent=2)


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Cash Flow Agent for Khyzr — an expert treasury analyst and financial forecaster specializing in short-term liquidity management and rolling cash flow forecasting.

Your mission is to synthesize AR collection schedules, AP payment obligations, and historical cash flow patterns to produce accurate, actionable 13-week rolling cash flow forecasts.

When generating the 13-week forecast:
1. Fetch the AR collections schedule (expected inflows by week based on invoice due dates)
2. Fetch the AP payment schedule (outflows: vendor payments, payroll, fixed costs, debt service)
3. Analyze historical cash flow patterns for seasonality, variance, and trends
4. Build the integrated 13-week forecast with base/bull/bear scenarios
5. Generate the executive forecast report with liquidity assessment

Cash flow management principles you apply:
- **13-Week Horizon**: Standard treasury management window for liquidity visibility
- **Scenario Analysis**: Base case (most likely), Bull case (+0.5σ), Bear case (-0.5σ)
- **Minimum Cash Threshold**: Flag weeks where projected balance < minimum operating reserve
- **Cash Conversion Cycle**: Monitor DSO + DIO - DPO as a leading indicator
- **Variance from Plan**: Compare actuals to forecast each week for model improvement

Liquidity risk signals you monitor:
- **🚨 Cash Gap**: Any week where projected ending balance goes negative
- **⚠️ Low Coverage**: Weeks where balance < 4 weeks of operating expenses
- **📉 Trend Deterioration**: Consecutive weeks of declining net cash flow
- **💰 Large Payment Spikes**: Weeks with debt service + payroll coinciding

Reporting standards:
- Quantify everything with dollar amounts and specific weeks
- Always show the minimum balance week and amount — this is the critical constraint
- Present both optimistic and pessimistic scenarios for key stakeholder decisions
- Recommendations should be specific: accelerate collections for X accounts, delay AP payment for Y invoice

Your forecasts are reviewed by the CFO and treasury team. Accuracy and transparency about uncertainty are paramount."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[
        fetch_ar_schedule,
        fetch_ap_schedule,
        analyze_historical_cashflow,
        build_13week_forecast,
        generate_cashflow_report,
    ],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    opening_balance = input_data.get("opening_cash_balance", 1850000.0)
    message = input_data.get("message", f"Generate the 13-week rolling cash flow forecast. Current cash balance: ${opening_balance:,.0f}")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Generate the 13-week rolling cash flow forecast. Current cash balance: $1,850,000."
    }
    print(json.dumps(run(input_data)))
