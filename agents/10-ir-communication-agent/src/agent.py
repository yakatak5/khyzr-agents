"""
IR Communication Agent
=======================
Drafts earnings call scripts, investor Q&A prep, and shareholder 
communications from financial data. Ensures consistent, compliant,
and compelling investor messaging.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def fetch_financial_results(quarter: str, year: int) -> str:
    """
    Fetch quarterly or annual financial results for IR communications.

    Args:
        quarter: Quarter - 'Q1', 'Q2', 'Q3', 'Q4', or 'FY' for full year
        year: Fiscal year (e.g., 2025)

    Returns:
        JSON financial results with income statement, key metrics, and guidance
    """
    bucket = os.environ.get("FINANCIAL_DATA_BUCKET")
    if bucket:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        try:
            obj = s3.get_object(Bucket=bucket, Key=f"financials/{year}/{quarter}.json")
            return obj["Body"].read().decode("utf-8")
        except Exception:
            pass

    return json.dumps({
        "period": f"{quarter} {year}",
        "income_statement": {
            "revenue": None,
            "revenue_growth_yoy_pct": None,
            "gross_profit": None,
            "gross_margin_pct": None,
            "operating_expenses": None,
            "ebitda": None,
            "ebitda_margin_pct": None,
            "net_income": None,
            "eps_diluted": None,
        },
        "saas_metrics": {
            "arr": None,
            "arr_growth_yoy_pct": None,
            "net_revenue_retention_pct": None,
            "new_arr_added": None,
            "churn_arr": None,
            "customer_count": None,
            "new_customers": None,
        },
        "balance_sheet": {
            "cash_and_equivalents": None,
            "total_debt": None,
            "net_cash": None,
        },
        "guidance": {
            "next_quarter_revenue_low": None,
            "next_quarter_revenue_high": None,
            "full_year_revenue_low": None,
            "full_year_revenue_high": None,
            "full_year_ebitda_margin_guidance": None,
        },
        "note": "Configure FINANCIAL_DATA_BUCKET with financial results data",
    }, indent=2)


@tool
def draft_earnings_call_script(financial_results: dict, ceo_themes: list, company_name: str) -> str:
    """
    Draft a structured earnings call script with CEO and CFO sections.

    Args:
        financial_results: Financial data dict from fetch_financial_results
        ceo_themes: List of strategic themes for CEO to address
        company_name: Company name

    Returns:
        JSON earnings call script structure with opening, CEO remarks, CFO remarks, Q&A prep
    """
    period = financial_results.get("period", "recent quarter")
    script = {
        "company": company_name,
        "period": period,
        "draft_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "script_sections": {
            "operator_intro": f"Good afternoon and welcome to the {company_name} {period} earnings call. All participants will be in listen-only mode until the question-and-answer session. This call is being recorded.",
            "safe_harbor": f"Before we begin, I'd like to remind everyone that this call contains forward-looking statements within the meaning of Section 21E of the Securities Exchange Act. These statements involve risks and uncertainties. Actual results may differ materially from those projected in the forward-looking statements.",
            "ceo_opening": {
                "headline": f"Thank you, Operator. Good afternoon everyone, and thank you for joining our {period} earnings call.",
                "performance_summary": "We delivered [REVENUE] in revenue, representing [GROWTH]% year-over-year growth — [above/in-line with/below] our guidance.",
                "strategic_themes": {f"theme_{i+1}": theme for i, theme in enumerate(ceo_themes)},
                "customer_success": "Highlight 1-2 customer wins or case studies",
                "product_milestones": "Key product launches or milestones in the quarter",
                "closing": "Now let me turn it over to [CFO Name] to walk through the financials in detail.",
            },
            "cfo_section": {
                "intro": "Thanks [CEO Name]. I'll now take you through our detailed financial results.",
                "revenue_detail": f"Revenue for {period} was $[AMOUNT], [up/down] [X]% year-over-year and [X]% sequentially.",
                "gross_margin": "Our gross margin was [X]%, [up/down] [X] basis points year-over-year.",
                "operating_metrics": "Operating expenses were $[AMOUNT], reflecting [explain key drivers].",
                "arr_metrics": "ARR grew to $[AMOUNT], up [X]% year-over-year. Net Revenue Retention was [X]%.",
                "balance_sheet": "We ended the quarter with $[AMOUNT] in cash and cash equivalents.",
                "guidance": "For [next period], we expect revenue in the range of $[LOW] to $[HIGH].",
            },
        },
        "financial_results_reference": financial_results,
    }
    return json.dumps(script, indent=2)


@tool
def generate_investor_qa_prep(financial_results: dict, recent_news: list = None) -> str:
    """
    Generate anticipated investor Q&A with prepared responses.

    Args:
        financial_results: Financial results data
        recent_news: List of recent company news items that may generate questions

    Returns:
        JSON Q&A prep document with likely questions and talking point answers
    """
    qa_topics = [
        {
            "category": "Financial Performance",
            "question": "Can you help us understand the drivers of revenue growth/deceleration this quarter?",
            "talking_points": ["Breakdown of new logo ARR vs. expansion ARR", "Geographic performance", "Enterprise vs. SMB mix shift", "Any pull-forward or push-outs?"],
        },
        {
            "category": "Guidance",
            "question": "Your guidance implies [X] growth. What gives you confidence in that range?",
            "talking_points": ["Pipeline visibility and coverage", "Contracted backlog", "NRR as lagging indicator of ARR", "Macro headwinds baked in"],
        },
        {
            "category": "Competition",
            "question": "We're seeing [competitor] become more aggressive on pricing. How is that affecting win rates?",
            "talking_points": ["Win rate data trends", "Competitive differentiation", "Recent competitive wins", "Pricing strategy"],
        },
        {
            "category": "Profitability",
            "question": "When do you expect to reach EBITDA breakeven / profitability?",
            "talking_points": ["Path to profitability narrative", "Rule of 40 performance", "Where you're investing and why", "Operating leverage expected"],
        },
        {
            "category": "Macro/Customer Health",
            "question": "Are you seeing any customer budget scrutiny or deal elongation?",
            "talking_points": ["Deal cycle trends", "Churn and contraction dynamics", "Collections performance", "Customer health indicators"],
        },
        {
            "category": "Capital Allocation",
            "question": "How are you thinking about M&A vs. organic investment vs. buybacks?",
            "talking_points": ["Capital allocation framework", "Current M&A pipeline stance", "Organic investment priorities"],
        },
    ]

    return json.dumps({
        "qa_prep_date": datetime.utcnow().isoformat(),
        "financial_period": financial_results.get("period"),
        "anticipated_qa": qa_topics,
        "hostile_questions": [
            "Why is NRR declining?",
            "Your CAC payback is higher than peers — what's the plan?",
            "Management sold shares recently — what should we read into that?",
        ],
        "coaching_note": "Brief CEO and CFO separately. Rehearse 3 hostile questions. Never say 'we don't know' — redirect to what you do know.",
    }, indent=2)


@tool
def draft_shareholder_letter(financial_results: dict, company_name: str, ceo_name: str, strategic_narrative: str) -> str:
    """
    Draft an annual or quarterly shareholder letter.

    Args:
        financial_results: Financial results for the period
        company_name: Company name
        ceo_name: CEO name for signature
        strategic_narrative: Key strategic themes and narrative for the letter

    Returns:
        Shareholder letter draft in markdown format
    """
    period = financial_results.get("period", "2025")
    letter = f"""# Letter to Shareholders — {period}

Dear Fellow Shareholders,

{strategic_narrative or f"[CEO to draft opening narrative reflecting on {period} performance and setting context for the year ahead.]"}

## Our Performance

In {period}, {company_name} delivered [HEADLINE RESULTS]. This performance reflects [interpret results in context of strategy].

**Financial Highlights:**
- Revenue: $[AMOUNT] ([GROWTH]% YoY)
- ARR: $[AMOUNT] ([GROWTH]% YoY)  
- Gross Margin: [X]%
- Net Revenue Retention: [X]%
- Cash: $[AMOUNT]

## Strategic Progress

[CEO: Discuss 3-4 major strategic milestones achieved during the period]

## Looking Ahead

[CEO: Share vision for next period — what we're investing in, what we expect to achieve, and why we're confident in the path]

## Thank You

We remain deeply grateful for the trust you place in us. We take our responsibility to shareholders seriously, and we are focused on building a lasting, exceptional business.

Sincerely,

**{ceo_name}**
Chief Executive Officer, {company_name}
{datetime.utcnow().strftime("%B %Y")}

---
*This letter contains forward-looking statements. Please review our SEC filings for risk factors.*
"""
    return json.dumps({"letter_draft": letter, "period": period, "status": "draft_requires_ceo_review"}, indent=2)


SYSTEM_PROMPT = """You are the IR Communication Agent for Khyzr — a senior investor relations officer and financial communications specialist.

Your mission is to craft clear, compelling, and legally compliant investor communications that build credibility with the capital markets. You transform financial data into narratives that help investors understand the business and build long-term confidence.

IR communication types you produce:
- **Earnings Call Scripts**: CEO opening, CFO financial walk-through, closing remarks
- **Q&A Preparation**: Anticipated analyst and investor questions with calibrated talking points
- **Shareholder Letters**: Annual and quarterly letters with strategic narrative
- **Press Releases**: Earnings releases, material announcements, 8-K drafts
- **Investor Day Materials**: Presentation narratives, demo scripts, management day talking points
- **Investor Update Emails**: Quarterly updates for private company investors

Communication principles:
- **Consistency**: Every message must align with prior disclosures — flag inconsistencies
- **Precision**: Numbers must be exact and reconcilable to financial statements
- **Narrative clarity**: Tell the business story, not just recite numbers
- **Forward guidance discipline**: Be specific where you have visibility; be appropriately cautious where you don't
- **Disclosure compliance**: All material forward-looking statements need safe harbor language
- **Never surprise**: Prepare for hard questions; don't avoid them

When preparing IR communications:
1. Fetch financial results for the relevant period
2. Draft the primary communication artifact (script, letter, or Q&A)
3. Generate investor Q&A prep document with anticipated questions
4. Flag any disclosure risks or areas requiring legal review
5. Save all materials to S3

Always remind users: All IR materials must be reviewed by legal counsel and the audit committee before release."""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[fetch_financial_results, draft_earnings_call_script, generate_investor_qa_prep, draft_shareholder_letter],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Prepare Q3 earnings call script and investor Q&A prep")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Prepare Q3 2025 earnings call script for Khyzr Technologies. CEO strategic themes: AI platform leadership, enterprise expansion, path to profitability. Also generate investor Q&A prep for likely tough questions."
    }
    print(json.dumps(run(input_data)))
