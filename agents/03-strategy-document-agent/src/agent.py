"""
Strategy Document Agent
=======================
Synthesizes internal data, market research, and strategic frameworks (SWOT,
Porter's Five Forces, Ansoff Matrix) into comprehensive draft strategic plans.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def run_swot_analysis(company_name: str, context: str) -> str:
    """
    Facilitate a SWOT analysis by structuring known inputs and identifying gaps.

    Args:
        company_name: Name of the company being analyzed
        context: Business context, recent developments, competitive landscape

    Returns:
        JSON SWOT framework template with analysis guidance
    """
    swot = {
        "framework": "SWOT Analysis",
        "company": company_name,
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "context_provided": context,
        "internal_factors": {
            "strengths": {
                "definition": "Internal positive attributes that give competitive advantage",
                "key_questions": [
                    "What does the company do better than competitors?",
                    "What unique resources or capabilities exist?",
                    "What do customers consistently praise?",
                    "What proprietary technology or IP is held?",
                ],
                "entries": [],
            },
            "weaknesses": {
                "definition": "Internal negative attributes that limit performance",
                "key_questions": [
                    "What could be improved?",
                    "Where does the company lack resources?",
                    "What do customers complain about?",
                    "Where do competitors have an edge?",
                ],
                "entries": [],
            },
        },
        "external_factors": {
            "opportunities": {
                "definition": "External factors the company could exploit for growth",
                "key_questions": [
                    "What market trends benefit this company?",
                    "Where are competitors weak?",
                    "What new customer needs are emerging?",
                    "What regulatory or technology shifts open doors?",
                ],
                "entries": [],
            },
            "threats": {
                "definition": "External factors that could harm the company",
                "key_questions": [
                    "What are competitors doing well?",
                    "What regulatory risks exist?",
                    "What technology disruptions loom?",
                    "What economic or geopolitical risks apply?",
                ],
                "entries": [],
            },
        },
    }
    return json.dumps(swot, indent=2)


@tool
def run_porters_five_forces(industry: str, company_name: str) -> str:
    """
    Apply Porter's Five Forces framework to assess competitive intensity.

    Args:
        industry: The industry or market segment to analyze
        company_name: Company name for context

    Returns:
        JSON structure of Porter's Five Forces analysis with ratings and commentary
    """
    forces = {
        "framework": "Porter's Five Forces",
        "industry": industry,
        "company": company_name,
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "forces": {
            "competitive_rivalry": {
                "force": "Rivalry Among Existing Competitors",
                "rating_scale": "Low / Medium / High",
                "key_factors": ["Number of competitors", "Market growth rate", "Product differentiation", "Switching costs", "Exit barriers"],
                "analysis": "To be populated based on context provided",
            },
            "supplier_power": {
                "force": "Bargaining Power of Suppliers",
                "rating_scale": "Low / Medium / High",
                "key_factors": ["Supplier concentration", "Availability of substitutes", "Switching costs to change suppliers", "Forward integration threat"],
                "analysis": "To be populated based on context provided",
            },
            "buyer_power": {
                "force": "Bargaining Power of Buyers",
                "rating_scale": "Low / Medium / High",
                "key_factors": ["Buyer concentration", "Price sensitivity", "Product differentiation", "Backward integration threat"],
                "analysis": "To be populated based on context provided",
            },
            "threat_of_substitutes": {
                "force": "Threat of Substitute Products/Services",
                "rating_scale": "Low / Medium / High",
                "key_factors": ["Availability of substitutes", "Relative price-performance of substitutes", "Buyer switching costs"],
                "analysis": "To be populated based on context provided",
            },
            "threat_of_new_entrants": {
                "force": "Threat of New Entrants",
                "rating_scale": "Low / Medium / High",
                "key_factors": ["Capital requirements", "Economies of scale", "Regulatory barriers", "Brand loyalty", "Access to distribution"],
                "analysis": "To be populated based on context provided",
            },
        },
        "overall_industry_attractiveness": "To be determined after analysis",
        "strategic_implications": "To be populated by agent",
    }
    return json.dumps(forces, indent=2)


@tool
def fetch_internal_data(data_type: str) -> str:
    """
    Retrieve internal company data relevant to strategic planning.

    Args:
        data_type: Type of data needed - 'financial', 'market_position', 'capabilities', 'customer', 'operations'

    Returns:
        JSON string of relevant internal data points
    """
    bucket = os.environ.get("STRATEGY_DATA_BUCKET")
    if bucket:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        try:
            obj = s3.get_object(Bucket=bucket, Key=f"strategy-inputs/{data_type}.json")
            return obj["Body"].read().decode("utf-8")
        except Exception as e:
            pass

    # Return structured template if no actual data source
    templates = {
        "financial": {"revenue_growth_yoy": None, "gross_margin": None, "ebitda_margin": None, "cash_runway_months": None, "note": "Configure STRATEGY_DATA_BUCKET to load real data"},
        "market_position": {"market_share_pct": None, "nps_score": None, "brand_ranking": None, "primary_segments": [], "note": "Configure STRATEGY_DATA_BUCKET to load real data"},
        "capabilities": {"core_competencies": [], "technology_assets": [], "talent_strengths": [], "ip_portfolio": [], "note": "Configure STRATEGY_DATA_BUCKET to load real data"},
        "customer": {"total_customers": None, "enterprise_pct": None, "churn_rate": None, "average_contract_value": None, "note": "Configure STRATEGY_DATA_BUCKET to load real data"},
        "operations": {"headcount": None, "key_locations": [], "infrastructure": [], "strategic_partners": [], "note": "Configure STRATEGY_DATA_BUCKET to load real data"},
    }
    return json.dumps(templates.get(data_type, {"error": f"Unknown data type: {data_type}"}), indent=2)


@tool
def structure_strategic_plan(plan_title: str, time_horizon: str, strategic_pillars: list) -> str:
    """
    Create a structured strategic plan document framework.

    Args:
        plan_title: Title of the strategic plan (e.g., '3-Year Growth Strategy 2025-2028')
        time_horizon: Planning horizon (e.g., '3 years', '18 months')
        strategic_pillars: List of strategic priority areas/pillars

    Returns:
        JSON document structure for the strategic plan
    """
    plan = {
        "document_title": plan_title,
        "time_horizon": time_horizon,
        "created_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "document_structure": {
            "section_1": {
                "title": "Executive Summary",
                "content": ["Strategic vision statement", "3-5 headline priorities", "Expected outcomes and success metrics"],
            },
            "section_2": {
                "title": "Situational Analysis",
                "content": ["Current state assessment", "SWOT analysis summary", "Porter's Five Forces insights", "Key trends shaping the industry"],
            },
            "section_3": {
                "title": "Strategic Objectives",
                "content": [f"Pillar: {p}" for p in strategic_pillars],
            },
            "section_4": {
                "title": "Strategic Initiatives",
                "content": ["Initiative roadmap by pillar", "Owner, timeline, investment required", "Interdependencies and sequencing"],
            },
            "section_5": {
                "title": "Financial Projections",
                "content": ["Revenue targets by year", "Investment requirements", "ROI and payback analysis", "Scenario analysis (base/bull/bear)"],
            },
            "section_6": {
                "title": "Organizational Enablers",
                "content": ["Talent and capability requirements", "Technology investments needed", "Cultural changes required", "Governance model"],
            },
            "section_7": {
                "title": "Execution Roadmap",
                "content": ["Year 1 priorities and milestones", "Year 2-3 roadmap", "Key decision points and gates", "Risk register"],
            },
            "section_8": {
                "title": "Measurement Framework",
                "content": ["Strategic KPIs by pillar", "Quarterly review cadence", "Board reporting metrics"],
            },
        },
    }
    return json.dumps(plan, indent=2)


@tool
def save_strategy_document(content: str, document_name: str) -> str:
    """
    Save the completed strategy document to S3.

    Args:
        content: Full strategy document content in markdown
        document_name: Document name/identifier

    Returns:
        S3 URI of saved document
    """
    bucket = os.environ.get("STRATEGY_DOCS_BUCKET", "khyzr-strategy-documents")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    key = f"strategic-plans/{timestamp}-{document_name.replace(' ', '-').lower()}.md"
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=content.encode("utf-8"), ContentType="text/markdown")
        return json.dumps({"status": "saved", "s3_uri": f"s3://{bucket}/{key}"})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


SYSTEM_PROMPT = """You are the Strategy Document Agent for Khyzr — a senior strategy consultant with deep expertise in corporate strategy, competitive analysis, and strategic planning frameworks.

Your mission is to synthesize internal company data, market research, and strategic frameworks into comprehensive, actionable strategic plans. You work alongside executive leadership to translate business context into rigorous, board-ready strategy documents.

Frameworks you apply expertly:
- **SWOT Analysis**: Structured internal/external factor assessment
- **Porter's Five Forces**: Industry attractiveness and competitive dynamics
- **Ansoff Matrix**: Growth strategy selection (market penetration, development, diversification)
- **BCG Matrix**: Portfolio analysis for multi-product companies
- **OKR Alignment**: Ensuring strategy translates to measurable objectives
- **Blue Ocean Strategy**: Identifying uncontested market space

Document writing standards:
- Strategic plans must be evidence-based — anchor every recommendation in data
- Use clear strategic logic: situation → insight → implication → recommendation
- Write at the executive level: precise, confident, and action-oriented
- Every strategic pillar must have associated initiatives, owners, timelines, and success metrics
- Include explicit risk/assumption statements for all major projections

When building a strategy document:
1. Gather internal data (financial performance, capabilities, market position)
2. Run appropriate analytical frameworks (SWOT, Porter's, etc.)
3. Structure the document with clear sections
4. Write the full strategy document in markdown
5. Save the completed document to S3

Your output should be a document executives can present to a board with confidence."""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[run_swot_analysis, run_porters_five_forces, fetch_internal_data, structure_strategic_plan, save_strategy_document],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Create a 3-year strategic plan")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Create a 3-year strategic plan for Khyzr Technologies, an AI automation company competing in the enterprise SaaS space. Apply SWOT and Porter's Five Forces analysis. Strategic pillars: Market Expansion, Product Innovation, Operational Excellence, Enterprise Sales."
    }
    print(json.dumps(run(input_data)))
