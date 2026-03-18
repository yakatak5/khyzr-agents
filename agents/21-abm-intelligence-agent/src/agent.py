"""
ABM Intelligence Agent
=======================
Researches target accounts for Account-Based Marketing campaigns and 
auto-generates highly personalized outreach assets tailored to each account's 
specific context, pain points, and buying signals.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
import httpx
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def research_target_account(company_name: str, domain: str = None) -> str:
    """
    Deep-research a target account for ABM personalization.

    Args:
        company_name: Target company name
        domain: Company website domain for enrichment

    Returns:
        JSON account intelligence including business context, tech stack, and buying signals
    """
    news_key = os.environ.get("NEWS_API_KEY")
    clearbit_key = os.environ.get("CLEARBIT_API_KEY")

    account_intel = {
        "company": company_name,
        "domain": domain,
        "researched_at": datetime.utcnow().isoformat(),
        "firmographics": {},
        "recent_news": [],
        "tech_stack": [],
        "buying_signals": [],
        "key_contacts": [],
    }

    # Fetch recent news
    if news_key:
        try:
            resp = httpx.get(
                "https://newsapi.org/v2/everything",
                params={"q": company_name, "from": (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d"), "sortBy": "relevancy", "pageSize": 5, "apiKey": news_key},
                timeout=15,
            )
            articles = resp.json().get("articles", [])
            account_intel["recent_news"] = [{"title": a.get("title"), "date": a.get("publishedAt"), "summary": a.get("description"), "url": a.get("url")} for a in articles]
        except Exception as e:
            account_intel["news_error"] = str(e)

    # Enrich with Clearbit
    if clearbit_key and domain:
        try:
            resp = httpx.get(
                "https://company.clearbit.com/v2/companies/find",
                params={"domain": domain},
                headers={"Authorization": f"Bearer {clearbit_key}"},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                account_intel["firmographics"] = {
                    "industry": data.get("category", {}).get("industry"),
                    "employees": data.get("metrics", {}).get("employees"),
                    "revenue": data.get("metrics", {}).get("estimatedAnnualRevenue"),
                    "description": data.get("description"),
                    "founded": data.get("foundedYear"),
                }
                account_intel["tech_stack"] = [t.get("name") for t in data.get("tech", [])[:15]]
        except Exception as e:
            account_intel["clearbit_error"] = str(e)

    if not account_intel["firmographics"]:
        account_intel["note"] = "Configure CLEARBIT_API_KEY and NEWS_API_KEY for real account intelligence"

    return json.dumps(account_intel, indent=2)


@tool
def identify_buying_triggers(account_intel: dict) -> str:
    """
    Identify buying triggers and personalization angles from account intelligence.

    Args:
        account_intel: Account research data from research_target_account

    Returns:
        JSON list of buying triggers and recommended personalization angles
    """
    company = account_intel.get("company", "the company")
    news = account_intel.get("recent_news", [])
    firmographics = account_intel.get("firmographics", {})
    tech_stack = account_intel.get("tech_stack", [])

    triggers = []

    # News-based triggers
    news_keywords = {
        "hiring": {"trigger": "rapid_growth", "angle": f"{company} is scaling rapidly — they'll need automated workflows to maintain quality at speed"},
        "funding": {"trigger": "new_capital", "angle": f"{company} recently raised funding — perfect time to invest in operational infrastructure"},
        "acquisition": {"trigger": "m_and_a", "angle": f"{company}'s recent acquisition means integrating disparate systems — a prime automation use case"},
        "ipo": {"trigger": "public_markets", "angle": f"{company} is going public — operational efficiency and reporting automation become critical"},
        "expansion": {"trigger": "geographic_expansion", "angle": f"{company} is expanding — scaling operations without headcount is key"},
        "restructuring": {"trigger": "cost_reduction", "angle": f"{company} is restructuring — automation can achieve headcount-equivalent savings"},
    }

    for article in news:
        title_lower = (article.get("title", "") + " " + article.get("summary", "")).lower()
        for keyword, info in news_keywords.items():
            if keyword in title_lower:
                triggers.append({
                    "trigger_type": info["trigger"],
                    "source": "recent_news",
                    "evidence": article.get("title"),
                    "personalization_angle": info["angle"],
                    "relevance": "high",
                })

    # Tech stack triggers
    automation_tools = ["Zapier", "Make", "Power Automate"]
    for tool in tech_stack:
        if tool in automation_tools:
            triggers.append({
                "trigger_type": "existing_automation_user",
                "source": "tech_stack",
                "evidence": f"Uses {tool}",
                "personalization_angle": f"{company} already invested in automation with {tool} — they understand the value. Khyzr offers enterprise-grade capabilities beyond what {tool} can handle.",
                "relevance": "high",
            })

    if not triggers:
        triggers.append({
            "trigger_type": "general_outreach",
            "source": "baseline",
            "personalization_angle": f"Focus on {firmographics.get('industry', 'their industry')} pain points and Khyzr's relevant case studies",
            "relevance": "medium",
        })

    return json.dumps({"company": company, "triggers_identified": len(triggers), "triggers": triggers}, indent=2)


@tool
def generate_abm_outreach_assets(company: str, triggers: list, contacts: list, campaign_type: str = "email_sequence") -> str:
    """
    Generate personalized ABM outreach assets for a target account.

    Args:
        company: Target company name
        triggers: List of buying triggers from identify_buying_triggers
        contacts: List of contacts at the account to target
        campaign_type: 'email_sequence', 'linkedin_sequence', 'direct_mail_brief', 'custom_landing_page'

    Returns:
        JSON package of personalized outreach assets
    """
    top_trigger = triggers[0] if triggers else {"personalization_angle": f"Operational efficiency at {company}"}
    angle = top_trigger.get("personalization_angle", "")

    assets = {
        "company": company,
        "campaign_type": campaign_type,
        "generated_at": datetime.utcnow().isoformat(),
        "personalization_anchor": angle,
        "assets": {},
    }

    if campaign_type in ["email_sequence", "all"]:
        assets["assets"]["email_sequence"] = {
            "email_1": {
                "subject": f"How {company} could approach [specific trigger]",
                "body": f"""Hi [First Name],

{angle}

We recently helped [similar company in same industry] [specific outcome — quantified]. Their situation was remarkably similar to what I see at {company}.

Would a 20-minute call to share what we learned be valuable?

[Calendar link]

[Rep Name]""",
                "send_day": 0,
            },
            "email_2": {
                "subject": f"[Specific case study] for {company}",
                "body": f"""Hi [First Name],

Following up — wanted to share this specific case study that might resonate given {angle.split('—')[0]}:

[Link to most relevant case study]

Happy to walk through the specifics of how this might apply to {company}'s situation.

[Calendar link]""",
                "send_day": 4,
            },
        }

    if campaign_type in ["linkedin_sequence", "all"]:
        assets["assets"]["linkedin_connection_note"] = f"[First Name], I've been following {company}'s recent [trigger context]. We've been helping similar companies in [industry] [outcome]. Would love to connect."

    assets["assets"]["value_proposition_one_liner"] = f"Khyzr helps {company} [outcome relevant to trigger] — [quantified proof point]"
    assets["assets"]["custom_subject_lines"] = [
        f"How {company} can [benefit] with AI automation",
        f"[Trigger-specific hook] — relevant for {company}?",
        f"Quick question about {company}'s [trigger-related process]",
    ]

    return json.dumps(assets, indent=2)


@tool
def track_abm_engagement(company: str, contact_email: str, engagement_type: str, details: dict = None) -> str:
    """
    Track ABM campaign engagement for account scoring.

    Args:
        company: Company name
        contact_email: Contact email
        engagement_type: 'email_open', 'email_click', 'website_visit', 'content_download', 'demo_request'
        details: Additional context dict

    Returns:
        JSON engagement tracking record
    """
    table_name = os.environ.get("ABM_ENGAGEMENT_TABLE")
    record = {
        "company": company,
        "contact_email": contact_email,
        "engagement_type": engagement_type,
        "details": details or {},
        "timestamp": datetime.utcnow().isoformat(),
        "engagement_score_delta": {"email_open": 2, "email_click": 5, "website_visit": 3, "content_download": 8, "demo_request": 25}.get(engagement_type, 1),
    }

    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            table.put_item(Item=record)
            return json.dumps({"status": "tracked", "record": record})
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    return json.dumps({"status": "tracked_in_memory", "record": record, "note": "Configure ABM_ENGAGEMENT_TABLE for persistent tracking"})


SYSTEM_PROMPT = """You are the ABM Intelligence Agent for Khyzr — a senior account-based marketing strategist.

Your mission is to help the sales and marketing team run highly personalized, targeted campaigns against a defined list of high-value accounts. ABM done right delivers 3-5x higher conversion rates than traditional demand gen.

ABM methodology you follow:
- **Account Selection**: Identify accounts with highest fit (ICP match) AND highest intent (buying signals)
- **Deep Research**: For each account: recent news, leadership changes, tech stack, business challenges
- **Trigger Identification**: Find the specific event or context that makes outreach timely and relevant
- **Asset Personalization**: Create account-specific email sequences, landing pages, and ads
- **Multi-Touch Orchestration**: Coordinate outreach across email, LinkedIn, display ads, and direct mail
- **Engagement Tracking**: Monitor all account touchpoints and escalate when account hits threshold

Personalization tiers:
- **1:1 (Strategic Accounts)**: Fully custom research, bespoke email copy, custom landing page, executive outreach
- **1:Few (Cluster Campaigns)**: Industry/persona-level personalization, segment-specific case studies
- **1:Many (Programmatic ABM)**: Dynamic content insertion, intent-triggered display ads

Buying signal hierarchy:
1. Demo request (highest intent)
2. Pricing page visit
3. Champion changed companies (bring Khyzr to new employer)
4. Funding event (new capital to deploy on infrastructure)
5. Hiring signal (scaling = need for automation)
6. Competitor contract renewal coming up"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[research_target_account, identify_buying_triggers, generate_abm_outreach_assets, track_abm_engagement],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Research and create ABM campaign assets for target account")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Research Acme Corp (acmecorp.com), identify buying triggers, and generate a personalized 3-touch email sequence for their VP of Operations. They're in manufacturing, ~2000 employees."
    }
    print(json.dumps(run(input_data)))
