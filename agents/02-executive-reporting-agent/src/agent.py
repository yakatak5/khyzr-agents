"""
Executive Reporting Agent
=========================
Pulls data from dashboards and data sources, then auto-generates narrative
board decks with commentary on KPI variances. Delivers polished executive
reports in markdown/PDF format to stakeholders.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def fetch_kpi_data(metric_names: list, period: str = "last_quarter") -> str:
    """
    Fetch KPI data from a data warehouse or analytics platform.

    Args:
        metric_names: List of KPI names to retrieve (e.g., ['revenue', 'churn_rate', 'nps'])
        period: Time period - 'last_month', 'last_quarter', 'ytd', 'last_year'

    Returns:
        JSON string with KPI values, targets, and prior period comparisons
    """
    # Simulates fetching from a data warehouse (Redshift, Snowflake, etc.)
    period_map = {
        "last_month": 30,
        "last_quarter": 90,
        "ytd": (datetime.utcnow() - datetime(datetime.utcnow().year, 1, 1)).days,
        "last_year": 365,
    }
    days = period_map.get(period, 90)

    # In production, this would query actual data sources via boto3/SQL
    kpi_data = {}
    for metric in metric_names:
        kpi_data[metric] = {
            "current_value": None,
            "target": None,
            "prior_period_value": None,
            "variance_pct": None,
            "trend": "up",
            "period_days": days,
            "note": f"Connect to data source for {metric}. Configure DATA_WAREHOUSE_ENDPOINT env var.",
        }

    # Try to pull from DynamoDB if configured
    table_name = os.environ.get("KPI_TABLE_NAME")
    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        for metric in metric_names:
            try:
                resp = table.get_item(Key={"metric_name": metric, "period": period})
                if "Item" in resp:
                    kpi_data[metric] = resp["Item"]
            except Exception as e:
                kpi_data[metric]["error"] = str(e)

    return json.dumps({"period": period, "kpis": kpi_data, "retrieved_at": datetime.utcnow().isoformat()}, indent=2)


@tool
def calculate_variance_commentary(metric_name: str, current: float, target: float, prior: float) -> str:
    """
    Calculate variance and generate auto-commentary for a KPI.

    Args:
        metric_name: Name of the KPI
        current: Current period value
        target: Target/budget value
        prior: Prior period value for comparison

    Returns:
        JSON with variance calculations and narrative commentary template
    """
    vs_target_pct = ((current - target) / target * 100) if target else 0
    vs_prior_pct = ((current - prior) / prior * 100) if prior else 0

    status = "on_track" if vs_target_pct >= -5 else ("at_risk" if vs_target_pct >= -15 else "off_track")
    trend = "improving" if vs_prior_pct > 0 else ("declining" if vs_prior_pct < -5 else "stable")

    direction_vs_target = "above" if vs_target_pct > 0 else "below"
    direction_vs_prior = "ahead of" if vs_prior_pct > 0 else "behind"

    commentary = (
        f"{metric_name} came in at {current:,.1f}, {abs(vs_target_pct):.1f}% {direction_vs_target} target "
        f"and {abs(vs_prior_pct):.1f}% {direction_vs_prior} prior period. "
        f"Status: {status.upper()}. Trend: {trend.capitalize()}."
    )

    return json.dumps({
        "metric": metric_name,
        "current": current,
        "target": target,
        "prior": prior,
        "vs_target_pct": round(vs_target_pct, 2),
        "vs_prior_pct": round(vs_prior_pct, 2),
        "status": status,
        "trend": trend,
        "auto_commentary": commentary,
    }, indent=2)


@tool
def generate_board_deck_structure(company_name: str, reporting_period: str, kpi_summary: dict) -> str:
    """
    Generate a structured board deck outline with slide titles and content areas.

    Args:
        company_name: Name of the company
        reporting_period: Reporting period (e.g., 'Q3 2025', 'October 2025')
        kpi_summary: Dictionary of KPI names to their status

    Returns:
        JSON structure representing the deck outline
    """
    deck = {
        "title": f"{company_name} — Executive Board Report {reporting_period}",
        "generated_at": datetime.utcnow().isoformat(),
        "slides": [
            {
                "slide": 1,
                "title": "Executive Summary",
                "content": ["One-paragraph narrative of the period", "Top 3 wins", "Top 3 risks/challenges"],
            },
            {
                "slide": 2,
                "title": "Financial Performance",
                "content": ["Revenue vs. target", "Gross margin", "EBITDA", "Cash position"],
            },
            {
                "slide": 3,
                "title": "KPI Scorecard",
                "content": [f"{k}: {v}" for k, v in kpi_summary.items()],
            },
            {
                "slide": 4,
                "title": "Growth & Commercial",
                "content": ["Customer acquisition", "Churn & retention", "Pipeline health", "NPS"],
            },
            {
                "slide": 5,
                "title": "Operations & Delivery",
                "content": ["Key milestones achieved", "Delivery against roadmap", "Operational metrics"],
            },
            {
                "slide": 6,
                "title": "Risks & Mitigations",
                "content": ["Top strategic risks", "Mitigation plans", "Escalations requiring board input"],
            },
            {
                "slide": 7,
                "title": "Outlook & Next Quarter Priorities",
                "content": ["Guidance update", "Key initiatives", "Resource asks"],
            },
        ],
    }
    return json.dumps(deck, indent=2)


@tool
def store_report(report_content: str, report_title: str, format: str = "markdown") -> str:
    """
    Store a completed executive report to S3.

    Args:
        report_content: Full report content
        report_title: Title/name for the report
        format: Output format - 'markdown' or 'html'

    Returns:
        S3 URI of the stored report
    """
    bucket = os.environ.get("REPORTS_BUCKET", "khyzr-executive-reports")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    ext = "md" if format == "markdown" else "html"
    key = f"board-reports/{timestamp}-{report_title.replace(' ', '-').lower()}.{ext}"

    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=report_content.encode("utf-8"),
            ContentType="text/markdown" if format == "markdown" else "text/html",
        )
        return json.dumps({"status": "stored", "s3_uri": f"s3://{bucket}/{key}"})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e), "note": "Report generated but not stored to S3."})


@tool
def distribute_report(report_markdown: str, subject: str, recipients: list) -> str:
    """
    Distribute the executive report via AWS SES email.

    Args:
        report_markdown: Report content in markdown
        subject: Email subject
        recipients: List of recipient email addresses

    Returns:
        Distribution status JSON
    """
    sender = os.environ.get("SES_SENDER_EMAIL", "")
    if not sender:
        return json.dumps({"error": "SES_SENDER_EMAIL not configured."})

    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    results = []
    for email in recipients:
        try:
            resp = ses.send_email(
                Source=sender,
                Destination={"ToAddresses": [email]},
                Message={
                    "Subject": {"Data": subject},
                    "Body": {"Text": {"Data": report_markdown}},
                },
            )
            results.append({"email": email, "status": "sent", "message_id": resp["MessageId"]})
        except Exception as e:
            results.append({"email": email, "status": "failed", "error": str(e)})
    return json.dumps({"results": results}, indent=2)


SYSTEM_PROMPT = """You are the Executive Reporting Agent for Khyzr — a senior financial analyst and board communication specialist.

Your primary responsibility is to pull business data from various sources and transform it into polished, narrative-driven executive reports and board decks that senior leadership and board members can act on immediately.

Core capabilities:
- Retrieve KPI data across financial, operational, and growth metrics
- Calculate variances against targets and prior periods with precise commentary
- Structure reports following best-practice board reporting standards
- Write clear, concise executive narratives that explain the 'so what' behind data
- Generate complete board deck outlines with slide-by-slide content
- Store reports to S3 and distribute via email

Report writing standards:
- Lead with the executive summary: one paragraph covering the period's headline story
- Every KPI must include variance vs target, variance vs prior period, and a one-sentence narrative explanation
- Use RAG (Red/Amber/Green) status consistently
- Flag escalations explicitly: "REQUIRES BOARD DECISION:" 
- End with clear next-period guidance and asks

When generating reports:
1. First fetch the relevant KPIs for the period
2. Calculate variance commentary for each material metric
3. Generate the deck structure
4. Write the full narrative report in markdown
5. Store to S3 and distribute to stakeholders

Always maintain a professional, confident tone appropriate for board-level communication. Present data objectively but with interpretive context that helps leaders make decisions."""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[fetch_kpi_data, calculate_variance_commentary, generate_board_deck_structure, store_report, distribute_report],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Generate executive report for last quarter")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Generate an executive board report for Q3 2025 covering revenue, churn rate, NPS, and gross margin. Company: Khyzr Technologies."
    }
    print(json.dumps(run(input_data)))
