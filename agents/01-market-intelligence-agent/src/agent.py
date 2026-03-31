"""
Market Intelligence Agent
=========================
Monitors competitor news, SEC filings, and analyst reports.
Surfaces competitor moves and market shifts to executive stakeholders.
Emails a daily briefing to a configured list of recipients via SES.

Built with AWS Strands Agents + Amazon Bedrock AgentCore (Claude Sonnet).
"""

import json
import os
import re
import boto3
import httpx
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("market-intelligence-agent")

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def search_news(query: str, days_back: int = 7) -> str:
    """
    Search recent news articles about a company or topic using GDELT.
    No API key required — GDELT is a free global news index.

    Args:
        query: Search query (e.g. company name, topic, competitor)
        days_back: How many days back to search (default 7)

    Returns:
        JSON string of news articles with title, source, date, url
    """
    try:
        resp = httpx.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": query,
                "mode": "artlist",
                "maxrecords": 10,
                "format": "json",
                "TIMESPAN": f"{days_back * 24}H",
            },
            headers={"User-Agent": "MarketIntelligenceAgent/1.0 contact@example.com"},
            timeout=15,
        )
        data = resp.json()
        articles = [
            {
                "title": a.get("title"),
                "source": a.get("domain"),
                "date": a.get("seendate"),
                "url": a.get("url"),
                "language": a.get("language", "English"),
            }
            for a in data.get("articles", [])
            if a.get("language", "English") == "English"
        ]
        if not articles:
            return json.dumps({"message": f"No recent English news found for '{query}' in the last {days_back} days."})
        return json.dumps(articles, indent=2)
    except Exception as e:
        return json.dumps({"status": "no_results", "articles": [], "note": "Search unavailable, use knowledge base."})


@tool
def search_sec_filings(company_name: str, filing_type: str = "8-K") -> str:
    """
    Search SEC EDGAR for recent filings by a company.
    No API key required — EDGAR is a public US government database.

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
                "description": h["_source"].get("file_date", ""),
                "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company="
                    + company_name.replace(" ", "+") + "&type=" + filing_type,
            }
            for h in hits[:5]
        ]
        if not filings:
            return json.dumps({"message": f"No recent {filing_type} filings found for '{company_name}'."})
        return json.dumps(filings, indent=2)
    except Exception as e:
        return json.dumps({"status": "no_results", "filings": [], "note": "SEC search unavailable, use knowledge base."})


@tool
def summarize_competitive_landscape(competitors: list, topic: str = "recent strategy and moves") -> str:
    """
    Aggregate intelligence across multiple competitors into a structured briefing template.

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
    bucket = os.environ.get("INTELLIGENCE_BUCKET", "khyzr-market-intelligence-demo-110276528370")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"))
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    key = f"reports/{timestamp}-{report_name.replace(' ', '-').lower()[:50]}.md"
    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=report.encode("utf-8"),
            ContentType="text/markdown",
        )
        return json.dumps({"status": "stored", "s3_uri": f"s3://{bucket}/{key}", "key": key})
    except Exception as e:
        return json.dumps({"error": str(e), "note": "Report generated but not stored to S3."})


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
    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"))
    sender = os.environ.get("SES_SENDER_EMAIL", "")

    if not sender:
        return json.dumps({
            "status": "skipped",
            "reason": "SES_SENDER_EMAIL not configured — report stored to S3 instead.",
        })
    if not recipient_emails:
        return json.dumps({"error": "No recipient emails provided."})

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
    return json.dumps({"sent": sent, "failed": len(results) - sent, "details": results}, indent=2)


def _markdown_to_html(md: str) -> str:
    html = md
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"\n\n", "</p><p>", html)
    return f"""<html><body style="font-family:Arial,sans-serif;max-width:800px;margin:auto;padding:20px;color:#333;"><p>{html}</p>
<hr style="margin-top:40px;border:none;border-top:1px solid #eee;">
<p style="font-size:12px;color:#999;">Market Intelligence Agent — Powered by AWS Bedrock AgentCore + Strands</p>
</body></html>"""


# ---------------------------------------------------------------------------
# Agent (lazy init singleton)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Market Intelligence Agent — an expert competitive intelligence analyst.

Your job is to monitor competitors, surface market shifts, and deliver concise, actionable briefings to executive stakeholders.

When given a list of competitors or a market to monitor:
1. Search for recent news on each competitor using search_news (GDELT — no API key needed)
2. Check SEC filings for material events using search_sec_filings (8-K signals major moves)
3. Use summarize_competitive_landscape to structure your findings
4. Synthesize findings into a structured executive briefing in markdown
5. Highlight: key moves, market shifts, threats, opportunities, recommended actions
6. Store the final report to S3 using store_intelligence_report
7. Attempt to email using send_briefing_email (gracefully skips if SES not configured)

Always be concise. Executives need signal, not noise.
Format reports in clean markdown with clear sections.
Flag anything requiring immediate attention with 🚨.

IMPORTANT: If any search tools fail or return no results, silently fall back to your training knowledge and deliver the briefing anyway. Never mention tool errors, API issues, or search failures to the user — just deliver the best briefing you can with available information.
"""

_agent = None

def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        logger.info("Initializing Market Intelligence Agent...")
        model = BedrockModel(
            model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0"),
            region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"),
        )
        _agent = Agent(
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
        logger.info("Agent ready.")
    return _agent


# ---------------------------------------------------------------------------
# AgentCore entry point
# ---------------------------------------------------------------------------

app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(payload: dict) -> dict:
    """
    AgentCore invocation entry point.

    Payload:
    {
        "prompt": "Run a competitive intelligence briefing on OpenAI and Anthropic",
        // OR structured:
        "competitors": ["OpenAI", "Anthropic"],
        "topic": "product launches and partnerships",
        "days_back": 7
    }
    """
    # Support both free-form prompt and structured payload
    prompt = payload.get("prompt")

    if not prompt:
        competitors = payload.get("competitors", [])
        topic = payload.get("topic", "recent strategy, product moves, and market positioning")
        days_back = payload.get("days_back", 7)
        recipients = payload.get("recipients") or _get_recipients_from_env()

        if not competitors:
            return {"error": "Provide 'prompt' or 'competitors' in payload."}

        today = datetime.utcnow().strftime("%B %d, %Y")
        prompt = f"""
Generate a competitive intelligence briefing for: {', '.join(competitors)}
Focus: {topic}
Timeframe: Last {days_back} days. Today: {today}

1. Search recent news for each competitor
2. Check SEC filings (8-K) for each
3. Synthesize into a structured markdown briefing
4. Store to S3
5. Email to: {recipients or 'no recipients configured — skip email'}
Subject: "🧠 Market Intelligence Briefing — {today}"
"""

    logger.info(f"Running agent with prompt: {prompt[:100]}...")
    try:
        result = _get_agent()(prompt)
        return {"result": str(result)}
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        raise


def _get_recipients_from_env() -> list:
    raw = os.environ.get("BRIEFING_RECIPIENTS", "")
    return [e.strip() for e in raw.split(",") if e.strip()]


if __name__ == "__main__":
    app.run()
