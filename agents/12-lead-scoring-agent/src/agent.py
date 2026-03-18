"""
Lead Scoring Agent
==================
Ranks inbound and outbound leads by conversion probability using behavioral,
firmographic, and intent data. Helps sales teams prioritize their outreach
to maximize conversion rates and pipeline efficiency.

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
def fetch_leads(source: str = "all", limit: int = 100) -> str:
    """
    Fetch unscored or recently updated leads from CRM system.

    Args:
        source: Lead source filter - 'all', 'inbound', 'outbound', 'website', 'event'
        limit: Maximum number of leads to return

    Returns:
        JSON list of leads with firmographic and behavioral data
    """
    table_name = os.environ.get("LEADS_TABLE_NAME")
    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            params = {"Limit": limit}
            if source != "all":
                params["FilterExpression"] = "lead_source = :s"
                params["ExpressionAttributeValues"] = {":s": source}
            resp = table.scan(**params)
            return json.dumps({"leads": resp.get("Items", []), "count": len(resp.get("Items", []))}, indent=2)
        except Exception as e:
            pass

    # Sample lead data structure
    sample_leads = [
        {
            "lead_id": "LD-001",
            "email": "john.smith@enterprise.com",
            "first_name": "John",
            "last_name": "Smith",
            "title": "VP of Engineering",
            "company": "Enterprise Corp",
            "company_size": 2500,
            "industry": "Financial Services",
            "annual_revenue_usd": 500_000_000,
            "technology_stack": ["Salesforce", "AWS", "Python"],
            "lead_source": "inbound",
            "source_detail": "gated_whitepaper",
            "created_date": (datetime.utcnow() - timedelta(days=2)).isoformat(),
            "behavioral": {
                "website_visits_30d": 8,
                "pages_viewed": ["pricing", "enterprise", "case_studies", "docs"],
                "email_opens_30d": 4,
                "email_clicks_30d": 2,
                "webinar_attended": True,
                "demo_requested": False,
                "content_downloads": 2,
            },
            "intent_signals": {
                "g2_profile_viewed": True,
                "competitor_comparison_viewed": True,
                "intent_score_bombora": 72,
            },
        }
    ]
    return json.dumps({"leads": sample_leads, "count": len(sample_leads), "note": "Configure LEADS_TABLE_NAME for real CRM data"}, indent=2)


@tool
def score_lead(lead: dict) -> str:
    """
    Score a single lead using a multi-dimensional scoring model.

    Args:
        lead: Lead object with firmographic, behavioral, and intent data

    Returns:
        JSON scoring result with overall score, breakdown by dimension, and recommended action
    """
    scores = {}

    # 1. Firmographic Fit (25 points max)
    firmographic = 0
    company_size = lead.get("company_size", 0)
    if company_size >= 1000:
        firmographic += 10
    elif company_size >= 200:
        firmographic += 6
    elif company_size >= 50:
        firmographic += 3

    icp_industries = ["Financial Services", "Healthcare", "Technology", "Manufacturing", "Retail"]
    if lead.get("industry") in icp_industries:
        firmographic += 8

    icp_titles = ["VP", "Director", "Head of", "Chief", "CTO", "CEO", "CFO", "COO"]
    title = lead.get("title", "")
    if any(t in title for t in icp_titles):
        firmographic += 7
    scores["firmographic_fit"] = min(firmographic, 25)

    # 2. Behavioral Engagement (35 points max)
    behavioral = lead.get("behavioral", {})
    behavior_score = 0
    behavior_score += min(behavioral.get("website_visits_30d", 0) * 2, 10)
    behavior_score += min(behavioral.get("email_clicks_30d", 0) * 3, 9)
    behavior_score += 8 if behavioral.get("demo_requested") else 0
    behavior_score += 5 if behavioral.get("webinar_attended") else 0
    pricing_visited = "pricing" in behavioral.get("pages_viewed", [])
    behavior_score += 3 if pricing_visited else 0
    scores["behavioral_engagement"] = min(behavior_score, 35)

    # 3. Intent Signals (25 points max)
    intent = lead.get("intent_signals", {})
    intent_score = 0
    intent_score += intent.get("intent_score_bombora", 0) // 5  # Normalize 0-100 to 0-20
    intent_score += 3 if intent.get("g2_profile_viewed") else 0
    intent_score += 2 if intent.get("competitor_comparison_viewed") else 0
    scores["intent_signals"] = min(intent_score, 25)

    # 4. Source Quality (15 points max)
    source_scores = {
        "demo_request": 15, "trial_signup": 13, "pricing_page": 10,
        "gated_whitepaper": 7, "webinar": 7, "event": 6, "cold_outbound": 3,
    }
    scores["source_quality"] = source_scores.get(lead.get("source_detail", ""), 5)

    total_score = sum(scores.values())
    grade = "A" if total_score >= 80 else ("B" if total_score >= 60 else ("C" if total_score >= 40 else "D"))

    action = {
        "A": "Immediate SDR outreach — high priority. Route to senior AE within 24 hours.",
        "B": "SDR outreach within 48 hours. Add to nurture sequence if no response.",
        "C": "Enroll in automated nurture sequence. SDR review in 2 weeks.",
        "D": "Marketing nurture only. Flag for re-scoring in 30 days.",
    }[grade]

    return json.dumps({
        "lead_id": lead.get("lead_id"),
        "email": lead.get("email"),
        "company": lead.get("company"),
        "title": lead.get("title"),
        "total_score": total_score,
        "grade": grade,
        "score_breakdown": scores,
        "recommended_action": action,
        "scored_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def batch_score_and_rank(leads: list) -> str:
    """
    Score and rank a batch of leads, returning a prioritized list.

    Args:
        leads: List of lead objects

    Returns:
        JSON ranked lead list with scores and priority actions
    """
    scored = []
    for lead in leads:
        try:
            score_result = json.loads(score_lead(lead))
            scored.append(score_result)
        except Exception as e:
            scored.append({"lead_id": lead.get("lead_id"), "error": str(e)})

    scored.sort(key=lambda x: x.get("total_score", 0), reverse=True)

    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for s in scored:
        grade_counts[s.get("grade", "D")] = grade_counts.get(s.get("grade", "D"), 0) + 1

    return json.dumps({
        "total_leads_scored": len(scored),
        "grade_distribution": grade_counts,
        "top_priority_leads": [s for s in scored if s.get("grade") == "A"],
        "all_scored_leads": scored,
        "scored_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def update_crm_scores(scored_leads: list) -> str:
    """
    Write updated lead scores back to the CRM/DynamoDB.

    Args:
        scored_leads: List of scored lead objects with total_score and grade

    Returns:
        JSON update status
    """
    table_name = os.environ.get("LEADS_TABLE_NAME")
    if not table_name:
        return json.dumps({"status": "skipped", "reason": "LEADS_TABLE_NAME not configured", "would_update": len(scored_leads)})

    dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    table = dynamodb.Table(table_name)
    results = []
    for lead in scored_leads:
        try:
            table.update_item(
                Key={"lead_id": lead["lead_id"]},
                UpdateExpression="SET lead_score = :s, lead_grade = :g, scored_at = :t, recommended_action = :a",
                ExpressionAttributeValues={
                    ":s": lead.get("total_score", 0),
                    ":g": lead.get("grade"),
                    ":t": lead.get("scored_at", datetime.utcnow().isoformat()),
                    ":a": lead.get("recommended_action"),
                },
            )
            results.append({"lead_id": lead["lead_id"], "status": "updated"})
        except Exception as e:
            results.append({"lead_id": lead.get("lead_id"), "status": "failed", "error": str(e)})

    return json.dumps({"updated": sum(1 for r in results if r["status"] == "updated"), "failed": sum(1 for r in results if r["status"] == "failed"), "details": results}, indent=2)


SYSTEM_PROMPT = """You are the Lead Scoring Agent for Khyzr — a revenue operations specialist and predictive analytics expert.

Your mission is to help the sales team spend their time where it will have the most impact: on leads most likely to convert. You score and rank every lead using a multi-dimensional model so reps know exactly who to call first.

Lead scoring methodology:
- **Firmographic Fit (25%)**: Company size, industry, geography, tech stack alignment to ICP
- **Behavioral Engagement (35%)**: Website visits, pricing page visits, content downloads, webinars, demo requests
- **Intent Signals (25%)**: G2 profile views, competitor comparisons, third-party intent data (Bombora, G2 Intent)
- **Source Quality (15%)**: Lead source credibility — demo requests score highest; cold lists score lowest

Scoring tiers:
- **Grade A (80-100)**: Hot leads — immediate SDR outreach, route to senior AE
- **Grade B (60-79)**: Warm leads — SDR outreach within 48 hours
- **Grade C (40-59)**: Nurture candidates — automated email sequences
- **Grade D (0-39)**: Low priority — marketing nurture only

ICP (Ideal Customer Profile) for Khyzr:
- Company size: 200+ employees
- Industries: Financial Services, Healthcare, Manufacturing, Technology
- Titles: VP/Director+ in Engineering, Operations, Finance, or C-suite
- Tech stack: Cloud-native, existing enterprise software (Salesforce, SAP, ServiceNow)
- Intent: Active evaluation, competitor comparison, pricing research

When scoring leads:
1. Fetch leads from the CRM (filtered by source or date if specified)
2. Score each lead across all four dimensions
3. Rank and prioritize into A/B/C/D tiers
4. Write scores back to CRM
5. Report the prioritized list to sales leadership with specific recommended next actions

Always explain your scoring rationale so reps can understand why a lead was rated high or low."""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[fetch_leads, score_lead, batch_score_and_rank, update_crm_scores],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Score all inbound leads from the last 48 hours and prioritize for SDR outreach")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Score and rank all inbound leads from today. Prioritize the top 10 for immediate SDR outreach and update their scores in the CRM."
    }
    print(json.dumps(run(input_data)))
