"""
Risk Monitoring Agent
=====================
Scans internal and external signals to identify emerging strategic,
operational, and geopolitical risks. Maintains a dynamic risk register
and alerts leadership to material new threats.

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
def scan_external_risk_signals(risk_categories: list, days_back: int = 7) -> str:
    """
    Scan external news and data sources for emerging risk signals.

    Args:
        risk_categories: List of risk domains to scan
            Options: 'geopolitical', 'regulatory', 'macroeconomic', 'cyber', 'supply_chain', 'reputational'
        days_back: How far back to scan

    Returns:
        JSON list of identified risk signals with source, severity estimate, and description
    """
    api_key = os.environ.get("NEWS_API_KEY")
    risk_queries = {
        "geopolitical": "sanctions OR trade war OR military conflict OR geopolitical tension",
        "regulatory": "regulatory enforcement OR SEC fine OR GDPR penalty OR antitrust OR legislation",
        "macroeconomic": "recession OR inflation OR interest rate hike OR currency crisis OR banking crisis",
        "cyber": "data breach OR ransomware OR cyberattack OR zero day OR supply chain attack",
        "supply_chain": "supply chain disruption OR port strike OR semiconductor shortage OR logistics delay",
        "reputational": "executive scandal OR brand crisis OR product recall OR whistleblower",
    }

    all_signals = []
    from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    for category in risk_categories:
        query = risk_queries.get(category, category)
        if api_key:
            try:
                resp = httpx.get(
                    "https://newsapi.org/v2/everything",
                    params={"q": query, "from": from_date, "sortBy": "relevancy", "pageSize": 5, "apiKey": api_key, "language": "en"},
                    timeout=15,
                )
                articles = resp.json().get("articles", [])
                for a in articles:
                    all_signals.append({
                        "category": category,
                        "title": a.get("title"),
                        "source": a.get("source", {}).get("name"),
                        "date": a.get("publishedAt"),
                        "summary": a.get("description"),
                        "url": a.get("url"),
                        "severity_estimate": "pending_agent_assessment",
                    })
            except Exception as e:
                all_signals.append({"category": category, "error": str(e)})
        else:
            all_signals.append({
                "category": category,
                "note": "Configure NEWS_API_KEY for real risk signal scanning",
                "sample_signal": f"Sample {category} risk signal - configure API keys for real data",
            })

    return json.dumps({"signals_found": len(all_signals), "scan_date": datetime.utcnow().isoformat(), "signals": all_signals}, indent=2)


@tool
def assess_internal_risks(business_unit: str = None) -> str:
    """
    Assess internal operational risks from internal data sources.

    Args:
        business_unit: Specific BU to assess (None = company-wide)

    Returns:
        JSON internal risk assessment
    """
    table_name = os.environ.get("RISK_TABLE_NAME")
    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            params = {}
            if business_unit:
                params = {"FilterExpression": "business_unit = :bu", "ExpressionAttributeValues": {":bu": business_unit}}
            resp = table.scan(**params)
            return json.dumps({"risks": resp.get("Items", [])}, indent=2)
        except Exception as e:
            pass

    # Internal risk categories to check
    internal_risks = [
        {
            "risk_id": "INT-001",
            "category": "operational",
            "title": "Key person dependency — CTO",
            "description": "Critical system knowledge concentrated in single individual",
            "likelihood": "medium",
            "impact": "high",
            "risk_score": 12,
            "mitigation": "Knowledge transfer sessions scheduled; succession planning in progress",
            "owner": "CEO",
            "status": "open",
            "business_unit": business_unit or "Engineering",
        },
        {
            "risk_id": "INT-002",
            "category": "financial",
            "title": "Customer concentration risk",
            "description": "Top 3 customers represent >40% of ARR",
            "likelihood": "low",
            "impact": "critical",
            "risk_score": 12,
            "mitigation": "Revenue diversification program; multi-year contracts with top 3",
            "owner": "CRO",
            "status": "open",
            "business_unit": business_unit or "Sales",
        },
    ]

    filtered = [r for r in internal_risks if not business_unit or r.get("business_unit") == business_unit]
    return json.dumps({"risks": filtered, "note": "Configure RISK_TABLE_NAME for real internal risk data"}, indent=2)


@tool
def score_and_prioritize_risks(risks: list) -> str:
    """
    Score and prioritize risks using a likelihood x impact matrix.

    Args:
        risks: List of risk objects with likelihood and impact fields

    Returns:
        JSON prioritized risk register with heat map categorization
    """
    likelihood_scores = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    impact_scores = {"low": 1, "medium": 2, "high": 3, "critical": 4}

    scored = []
    for risk in risks:
        l_score = likelihood_scores.get(risk.get("likelihood", "medium"), 2)
        i_score = impact_scores.get(risk.get("impact", "medium"), 2)
        risk_score = l_score * i_score
        heat_zone = "red" if risk_score >= 9 else ("amber" if risk_score >= 4 else "green")
        scored.append({**risk, "calculated_risk_score": risk_score, "heat_zone": heat_zone})

    scored.sort(key=lambda x: x["calculated_risk_score"], reverse=True)
    red = [r for r in scored if r["heat_zone"] == "red"]
    amber = [r for r in scored if r["heat_zone"] == "amber"]
    green = [r for r in scored if r["heat_zone"] == "green"]

    return json.dumps({
        "total_risks": len(scored),
        "red_zone": len(red),
        "amber_zone": len(amber),
        "green_zone": len(green),
        "top_10_risks": scored[:10],
        "heat_map_summary": {"red": [r.get("title", r.get("risk_id")) for r in red], "amber": [r.get("title", r.get("risk_id")) for r in amber]},
    }, indent=2)


@tool
def generate_risk_alert(risk: dict, alert_type: str = "new_risk") -> str:
    """
    Generate a formatted risk alert for leadership distribution.

    Args:
        risk: Risk object with details
        alert_type: 'new_risk', 'escalation', 'risk_materialized', 'risk_resolved'

    Returns:
        JSON alert with formatted message and recommended actions
    """
    severity_emoji = {"red": "🔴", "amber": "🟡", "green": "🟢"}.get(risk.get("heat_zone", "amber"), "🟡")
    type_label = {"new_risk": "NEW RISK IDENTIFIED", "escalation": "RISK ESCALATION", "risk_materialized": "RISK MATERIALIZED ⚠️", "risk_resolved": "RISK RESOLVED ✅"}.get(alert_type, "RISK ALERT")

    alert = {
        "alert_type": alert_type,
        "generated_at": datetime.utcnow().isoformat(),
        "subject": f"{severity_emoji} {type_label}: {risk.get('title', 'Unknown Risk')}",
        "risk_id": risk.get("risk_id"),
        "category": risk.get("category"),
        "heat_zone": risk.get("heat_zone"),
        "risk_score": risk.get("calculated_risk_score"),
        "description": risk.get("description"),
        "mitigation": risk.get("mitigation"),
        "owner": risk.get("owner"),
        "recommended_actions": [
            f"Review and validate risk assessment with {risk.get('owner', 'risk owner')}",
            "Determine if existing mitigation controls are sufficient",
            "Consider immediate escalation if red zone and no mitigation in place",
            "Update risk register with current status and next review date",
        ],
    }
    return json.dumps(alert, indent=2)


SYSTEM_PROMPT = """You are the Risk Monitoring Agent for Khyzr — a chief risk officer and risk intelligence specialist.

Your mission is to proactively identify, assess, and communicate emerging risks across all dimensions: strategic, operational, financial, compliance, geopolitical, and reputational. You operate as the early warning system for leadership.

Risk monitoring domains:
- **Strategic Risks**: Competitive disruption, business model threats, M&A risks
- **Operational Risks**: Process failures, key person dependencies, technology outages
- **Financial Risks**: Liquidity, credit, FX exposure, customer concentration
- **Compliance/Regulatory**: Evolving regulations, enforcement actions, licensing risks
- **Cyber/Technology**: Data breaches, ransomware, vendor dependencies
- **Geopolitical**: Trade policy, sanctions, political instability in key markets
- **Reputational**: Brand, ESG, leadership conduct, social media crises
- **Supply Chain**: Vendor concentration, logistics disruptions, critical input shortages

Risk assessment methodology:
- **Likelihood**: Low (rare), Medium (possible), High (likely), Critical (imminent)
- **Impact**: Low (minor disruption), Medium (notable harm), High (material damage), Critical (existential)
- **Risk Score**: Likelihood × Impact (1-16 scale)
- **Heat Zones**: Red (9-16), Amber (4-8), Green (1-3)

Response protocols:
- Red Zone: Immediate CEO/Board notification; require mitigation plan within 48 hours
- Amber Zone: Weekly leadership review; owner must update status monthly
- Green Zone: Quarterly review; monitor for escalation triggers

When monitoring risks:
1. Scan external signals for emerging risks in specified categories
2. Assess internal operational risks from available data
3. Score and prioritize all identified risks using the heat map methodology
4. Generate targeted alerts for red/amber zone risks
5. Produce a consolidated risk briefing with recommended actions

Always distinguish between risks you've detected vs. confirmed threats. Flag uncertainty explicitly."""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[scan_external_risk_signals, assess_internal_risks, score_and_prioritize_risks, generate_risk_alert],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Perform comprehensive risk scan across all categories")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Scan for emerging risks across geopolitical, cyber, and regulatory categories. Assess internal operational risks, score everything, and flag any red zone items for immediate leadership attention."
    }
    print(json.dumps(run(input_data)))
