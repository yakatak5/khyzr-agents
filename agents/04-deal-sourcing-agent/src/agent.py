"""
Deal Sourcing Agent
===================
Scans databases, financials, and news to identify and rank M&A acquisition
targets by strategic fit, financial health, and market positioning.

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
def search_acquisition_targets(industry: str, criteria: dict) -> str:
    """
    Search for potential acquisition targets in a given industry.

    Args:
        industry: Target industry or sector (e.g., 'enterprise SaaS', 'healthcare tech')
        criteria: Dict with filters: {'min_revenue': 5000000, 'max_revenue': 100000000,
                  'geography': 'US', 'stage': 'Series B+', 'keywords': ['AI', 'automation']}

    Returns:
        JSON list of potential targets with basic firmographic data
    """
    # In production: integrates with PitchBook, Crunchbase, or custom database
    crunchbase_key = os.environ.get("CRUNCHBASE_API_KEY")
    results = []

    if crunchbase_key:
        try:
            resp = httpx.post(
                "https://api.crunchbase.com/api/v4/searches/organizations",
                headers={"X-cb-user-key": crunchbase_key},
                json={
                    "field_ids": ["identifier", "short_description", "founded_on", "revenue_range", "num_employees_enum", "website_url"],
                    "query": [
                        {"type": "predicate", "field_id": "facet_ids", "operator_id": "includes", "values": ["company"]},
                        {"type": "predicate", "field_id": "short_description", "operator_id": "contains", "values": criteria.get("keywords", [industry])},
                    ],
                    "limit": 10,
                },
                timeout=20,
            )
            data = resp.json()
            results = data.get("entities", [])
        except Exception as e:
            results = [{"error": str(e), "note": "Crunchbase API call failed"}]
    else:
        results = [
            {
                "name": "Example Target Co",
                "description": f"A {industry} company matching criteria",
                "estimated_revenue": criteria.get("min_revenue", 10000000),
                "stage": criteria.get("stage", "Series B"),
                "geography": criteria.get("geography", "US"),
                "note": "Configure CRUNCHBASE_API_KEY for real data",
            }
        ]

    return json.dumps({
        "industry": industry,
        "criteria": criteria,
        "targets_found": len(results),
        "results": results,
        "search_date": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def analyze_target_financials(company_name: str, ticker: str = None) -> str:
    """
    Analyze financial health and valuation metrics for an acquisition target.

    Args:
        company_name: Company name
        ticker: Stock ticker if publicly traded (optional)

    Returns:
        JSON financial profile with revenue, growth rate, margins, valuation multiples
    """
    financial_profile = {
        "company": company_name,
        "ticker": ticker,
        "analysis_date": datetime.utcnow().isoformat(),
        "financial_metrics": {
            "revenue_ttm": None,
            "revenue_growth_yoy": None,
            "gross_margin": None,
            "ebitda_margin": None,
            "net_revenue_retention": None,
            "arr": None,
        },
        "valuation_metrics": {
            "estimated_ev": None,
            "revenue_multiple": None,
            "ebitda_multiple": None,
            "comparable_transactions": [],
        },
        "financial_health": {
            "cash_position": None,
            "debt_level": None,
            "burn_rate": None,
            "runway_months": None,
        },
    }

    # Attempt SEC filing lookup for public companies
    if ticker:
        try:
            headers = {"User-Agent": "DealSourcingAgent contact@khyzr.ai"}
            resp = httpx.get(
                f"https://data.sec.gov/submissions/CIK{ticker.upper()}.json",
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                financial_profile["sec_data_available"] = True
                financial_profile["company_official_name"] = data.get("name")
                financial_profile["recent_filings"] = [
                    {"form": f["form"], "date": f["filingDate"]}
                    for f in data.get("filings", {}).get("recent", {}).get("filingDate", [])[:5]
                ] if "filings" in data else []
        except Exception:
            financial_profile["sec_data_available"] = False

    return json.dumps(financial_profile, indent=2)


@tool
def score_strategic_fit(target_name: str, acquirer_strategy: dict, target_profile: dict) -> str:
    """
    Score a target's strategic fit against the acquirer's strategy using weighted criteria.

    Args:
        target_name: Name of the acquisition target
        acquirer_strategy: Dict with acquirer's strategic priorities and gaps
                          {'goals': ['expand to EU', 'add AI capabilities'],
                           'capability_gaps': ['ML infrastructure', 'healthcare compliance'],
                           'geographic_targets': ['EU', 'APAC']}
        target_profile: Dict with target's attributes
                       {'capabilities': [...], 'geographies': [...], 'customers': [...]}

    Returns:
        JSON strategic fit scorecard with weighted scores by dimension
    """
    dimensions = {
        "capability_fit": {
            "weight": 0.25,
            "description": "Does the target fill capability gaps?",
            "score": None,  # 1-10
        },
        "customer_synergy": {
            "weight": 0.20,
            "description": "Cross-sell / upsell potential with existing customer base",
            "score": None,
        },
        "revenue_synergy": {
            "weight": 0.20,
            "description": "Potential combined revenue uplift",
            "score": None,
        },
        "geographic_fit": {
            "weight": 0.15,
            "description": "Market expansion value",
            "score": None,
        },
        "technology_fit": {
            "weight": 0.10,
            "description": "Technology stack compatibility and IP value",
            "score": None,
        },
        "cultural_fit": {
            "weight": 0.10,
            "description": "Leadership, values, and organizational compatibility",
            "score": None,
        },
    }

    return json.dumps({
        "target": target_name,
        "acquirer_strategy": acquirer_strategy,
        "scoring_dimensions": dimensions,
        "total_weighted_score": None,
        "rank": None,
        "recommendation": "Pending agent analysis and scoring",
        "scored_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def generate_target_brief(targets: list, brief_format: str = "executive_summary") -> str:
    """
    Generate a ranked deal sourcing brief from analyzed targets.

    Args:
        targets: List of scored target dicts
        brief_format: 'executive_summary', 'full_brief', or 'board_memo'

    Returns:
        Structured brief template for the agent to populate
    """
    brief = {
        "document": f"Deal Sourcing Brief — {datetime.utcnow().strftime('%B %Y')}",
        "format": brief_format,
        "targets_analyzed": len(targets),
        "sections": {
            "market_scan_summary": "Overview of targets identified and screening criteria applied",
            "ranked_targets": "Targets ranked by strategic fit score (highest to lowest)",
            "top_recommendation": "Primary recommended target with rationale",
            "financial_overview": "Estimated valuations and deal size ranges",
            "next_steps": "Recommended diligence process and timeline",
            "appendix": "Detailed profiles for all screened targets",
        },
        "targets": targets,
    }
    return json.dumps(brief, indent=2)


@tool
def save_deal_brief(content: str, brief_name: str) -> str:
    """
    Save deal sourcing brief to S3.

    Args:
        content: Brief content in markdown
        brief_name: Brief identifier

    Returns:
        S3 URI
    """
    bucket = os.environ.get("DEAL_DOCS_BUCKET", "khyzr-deal-sourcing")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    key = f"briefs/{timestamp}-{brief_name.replace(' ', '-').lower()}.md"
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=content.encode("utf-8"), ContentType="text/markdown")
        return json.dumps({"status": "saved", "s3_uri": f"s3://{bucket}/{key}"})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


SYSTEM_PROMPT = """You are the Deal Sourcing Agent for Khyzr — a senior M&A analyst and investment banker specializing in technology acquisitions.

Your mission is to proactively identify, screen, and rank acquisition targets that fit the company's strategic objectives. You provide leadership with a curated, prioritized pipeline of M&A opportunities backed by financial analysis and strategic rationale.

Deal sourcing methodology:
1. **Market Scanning**: Search target industries using defined criteria (revenue range, geography, stage, capabilities)
2. **Financial Analysis**: Assess revenue, growth rates, margins, and estimated valuations
3. **Strategic Fit Scoring**: Evaluate each target against the acquirer's strategic gaps and priorities using a weighted scorecard
4. **Prioritization**: Rank targets by combined financial attractiveness and strategic fit
5. **Brief Generation**: Produce actionable deal briefs with clear recommendations

Scoring dimensions you apply:
- Capability fill (25%): Does the target address specific gaps?
- Customer synergy (20%): Cross-sell/upsell potential
- Revenue synergy (20%): Combined revenue uplift potential
- Geographic fit (15%): Market expansion value
- Technology fit (10%): Stack compatibility and IP
- Cultural fit (10%): Organizational compatibility

Output standards:
- Every target must have a strategic fit score and financial profile
- Top recommendation must include clear rationale and suggested deal structure
- Always include estimated valuation range and comparable transactions
- Flag integration complexity and key risks explicitly
- Provide a concrete next steps section with timeline

When asked to source deals:
1. Search for targets in the specified industry/criteria
2. Analyze financials for top candidates
3. Score strategic fit for each
4. Generate a ranked brief with top recommendation
5. Save the brief to S3"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[search_acquisition_targets, analyze_target_financials, score_strategic_fit, generate_target_brief, save_deal_brief],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Source acquisition targets in enterprise AI automation")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Source acquisition targets in the healthcare AI space. We're looking for companies with $5M-$50M ARR, strong ML capabilities, and US/EU presence. Our strategic gaps are: clinical NLP, EHR integrations, and prior auth automation."
    }
    print(json.dumps(run(input_data)))
