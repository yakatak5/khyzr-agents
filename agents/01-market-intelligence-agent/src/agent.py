"""
Market Intelligence Agent
=========================
Continuously monitors competitor news, SEC filings, and analyst reports.
Surfaces competitor moves and market shifts to executive stakeholders.
Emails a daily briefing to a configured list of recipients via SES.

Built with AWS Strands Agents + AgentCore on AWS Bedrock (Claude Sonnet).
"""

import json
import os
import re
import boto3
import httpx
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def search_news(query: str, days_back: int = 7) -> str:
    """
    Search recent news articles about a company or topic.

    Args:
        query: Search query (e.g. company name, topic, competitor)
        days_back: How many days back to search (default 7)

    Returns:
        JSON string of news articles with title, source, date, summary, url
    """
    api_key = os.environ.get("NEWS_API_KEY")
    from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    if api_key:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "from": from_date,
            "sortBy": "relevancy",
            "pageSize": 10,
            "apiKey": api_key,
            "language": "en",
        }
        try:
            resp = httpx.get(url, params=params, timeout=15)
            data = resp.json()
            articles = [
                {
                    "title": a.get("title"),
                    "source": a.get("source", {}).get("name"),
                    "date": a.get("publishedAt"),
                    "summary": a.get("description"),
                    "url": a.get("url"),
                }
                for a in data.get("articles", [])
            ]
            return json.dumps(articles, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})
    else:
        return json.dumps({"error": "NEWS_API_KEY not configured."})


@tool
def search_sec_filings(company_name: str, filing_type: str = "8-K") -> str:
    """
    Search SEC EDGAR for recent filings by a company.

    Args:
        company_name: Company name or ticker symbol
        filing_type: SEC filing type (8-K, 10-K, 10-Q, S-1, etc.)

    Returns:
        JSON string of recent filings with date, description, and URL
    """
    try:
        headers = {"User-Agent": "MarketIntelligenceAgent contact@example.com"}
        resp = httpx.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={
                "q": company_name,
                "forms": filing_type,
                "dateRange": "custom",
                "startdt": (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d"),
            },
            headers=headers,
            timeout=15,
        )
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        filings = [
            {
                "date": h["_source"].get("period_of_report") or h["_source"].get("file_date"),
                "company": h["_source"].get("display_names", [{}])[0].get("name")
                    if h["_source"].get("display_names") else company_name,
                "form_type": h["_source"].get("form_type"),
                "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company="
                    + company_name.replace(" ", "+") + "&type=" + filing_type,
            }
            for h in hits[:5]
        ]
        return json.dumps(filings, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def summarize_competitive_landscape(competitors: list, topic: str = "recent strategy and moves") -> str:
    """
    Aggregate intelligence across multiple competitors into a structured briefing.

    Args:
        competitors: List of competitor names to analyze
        topic: Specific topic or angle to focus on

    Returns:
        Structured competitive briefing template (to be filled by agent reasoning)
    """
    template = {
        "briefing_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "topic": topic,
        "competitors_analyzed": competitors,
        "sections": {
            "key_moves": "Populated from news/filings search",
            "market_shifts": "Populated from analysis",
            "threats": "Populated from analysis",
            "opportunities": "Populated from analysis",
            "recommended_actions": "Populated from analysis",
        },
    }
    return json.dumps(template, indent=2)


@tool
def store_intelligence_report(report: str, report_name: str) -> str:
    """
    Store a completed intelligence report to S3.

    Args:
        report: The full report content (markdown)
        report_name: Name/title for the report (used as S3 key prefix)

    Returns:
        S3 URI where the report was stored
    """
    bucket = os.environ.get("INTELLIGENCE_BUCKET", "market-intelligence-reports")
    s3 = boto3.client("s3")
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    key = f"reports/{timestamp}-{report_name.replace(' ', '-').lower()}.md"
    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=report.encode("utf-8"),
            ContentType="text/markdown",
        )
        return json.dumps({"status": "stored", "s3_uri": f"s3://{bucket}/{key}", "key": key})
    except Exception as e:
        return json.dumps({"error": str(e), "note": "Report generated but not stored."})


@tool
def send_briefing_email(report_markdown: str, subject: str, recipient_emails: list) -> str:
    """
    Send the intelligence briefing to a list of email recipients via AWS SES.

    Args:
        report_markdown: Full briefing content in markdown format
        subject: Email subject line
        recipient_emails: List of email addresses to send to

    Returns:
        JSON string with send status and SES message IDs
    """
    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    sender = os.environ.get("SES_SENDER_EMAIL", "")

    if not sender:
        return json.dumps({"error": "SES_SENDER_EMAIL not configured in environment variables."})
    if not recipient_emails:
        return json.dumps({"error": "No recipient emails provided."})

    # Convert markdown to basic HTML for email clients
    html_body = _markdown_to_html(report_markdown)

    results = []
    for email in recipient_emails:
        try:
            response = ses.send_email(
                Source=sender,
                Destination={"ToAddresses": [email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                        "Text": {"Data": report_markdown, "Charset": "UTF-8"},
                    },
                },
            )
            results.append({"email": email, "status": "sent", "message_id": response["MessageId"]})
        except Exception as e:
            results.append({"email": email, "status": "failed", "error": str(e)})

    sent = sum(1 for r in results if r["status"] == "sent")
    failed = len(results) - sent
    return json.dumps({"sent": sent, "failed": failed, "details": results}, indent=2)


def _markdown_to_html(md: str) -> str:
    """Convert markdown to simple HTML for email delivery."""
    html = md
    # Headers
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    # Bold
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    # Bullet lists
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"(<li>.*</li>)", r"<ul>\1</ul>", html, flags=re.DOTALL)
    # Paragraphs (double newlines)
    html = re.sub(r"\n\n", "</p><p>", html)
    html = f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 800px; margin: auto; padding: 20px; color: #333;">
    <p>{html}</p>
    <hr style="margin-top: 40px; border: none; border-top: 1px solid #eee;">
    <p style="font-size: 12px; color: #999;">Market Intelligence Agent — Powered by AWS Bedrock + Strands</p>
    </body></html>
    """
    return html


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Market Intelligence Agent — an expert competitive intelligence analyst.

Your job is to monitor competitors, surface market shifts, and deliver concise, actionable briefings to executive stakeholders via email.

When given a list of competitors or a market to monitor:
1. Search for recent news on each competitor (last 7 days by default)
2. Check SEC filings for material events (8-K filings signal major moves)
3. Synthesize findings into a structured executive briefing in markdown
4. Highlight: key moves, market shifts, threats, opportunities, recommended actions
5. Store the final report to S3
6. Email the briefing to all configured recipients

Always be concise. Executives need signal, not noise.
Format reports in clean markdown with clear sections.
Flag anything that requires immediate attention with 🚨.
The email subject should follow this format: "🧠 Market Intelligence Briefing — [Date]"
"""


def create_agent() -> Agent:
    """Create and return the configured Market Intelligence Agent."""
    model = BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-5"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[
            search_news,
            search_sec_filings,
            summarize_competitive_landscape,
            store_intelligence_report,
            send_briefing_email,
        ],
    )
    return agent


# ---------------------------------------------------------------------------
# Lambda handler (AgentCore entry point)
# ---------------------------------------------------------------------------

def handler(event: dict, context) -> dict:
    """
    AWS Lambda handler — AgentCore invocation entry point.

    Expected event payload:
    {
        "competitors": ["Company A", "Company B"],
        "recipients": ["exec@company.com", "cto@company.com"],  // optional, falls back to env var
        "topic": "product launches and partnerships",            // optional
        "days_back": 7                                           // optional
    }
    """
    competitors = event.get("competitors", [])
    topic = event.get("topic", "recent strategy, product moves, and market positioning")
    days_back = event.get("days_back", 7)

    # Recipients: event payload takes priority, then env var (comma-separated list)
    recipients = event.get("recipients") or _get_recipients_from_env()

    if not competitors:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "No competitors specified in event payload"}),
        }

    if not recipients:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "No recipients configured. Set BRIEFING_RECIPIENTS env var or pass 'recipients' in payload."}),
        }

    agent = create_agent()
    today = datetime.utcnow().strftime("%B %d, %Y")

    prompt = f"""
Generate a competitive intelligence briefing for the following companies:
{', '.join(competitors)}

Focus: {topic}
Timeframe: Last {days_back} days
Today's date: {today}

Steps:
1. For each competitor, search recent news
2. For each competitor, check for SEC filings (8-K for public companies)
3. Synthesize all findings into a structured executive briefing in markdown
4. Store the report to S3
5. Email the briefing to these recipients: {recipients}
   Use subject: "🧠 Market Intelligence Briefing — {today}"
"""

    response = agent(prompt)

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "status": "completed",
                "competitors": competitors,
                "recipients": recipients,
                "response": str(response),
            }
        ),
    }


def _get_recipients_from_env() -> list:
    """Parse comma-separated email list from BRIEFING_RECIPIENTS env var."""
    raw = os.environ.get("BRIEFING_RECIPIENTS", "")
    return [e.strip() for e in raw.split(",") if e.strip()]


# ---------------------------------------------------------------------------
# Local dev runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    competitors = sys.argv[1:] if len(sys.argv) > 1 else ["OpenAI", "Google DeepMind", "Anthropic"]
    print(f"Running Market Intelligence Agent for: {competitors}\n")

    agent = create_agent()
    today = datetime.utcnow().strftime("%B %d, %Y")
    recipients = _get_recipients_from_env() or ["test@example.com"]

    result = agent(
        f"Give me a competitive intelligence briefing on {', '.join(competitors)} — "
        f"focus on the last 7 days. Today is {today}. "
        f"Store to S3 and email to: {recipients}"
    )
    print(result)
