"""
Scenario Modeling Agent
=======================
Builds and runs multiple business scenarios dynamically based on variable 
assumptions from leadership. Produces financial projections, sensitivity 
analyses, and scenario comparison reports.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def build_revenue_scenario(scenario_name: str, assumptions: dict) -> str:
    """
    Build a revenue scenario based on input assumptions.

    Args:
        scenario_name: Scenario label (e.g., 'base', 'bull', 'bear', 'downside_stress')
        assumptions: Dict with key drivers:
            {
                'starting_arr': 10000000,
                'growth_rate_y1': 0.40,
                'growth_rate_y2': 0.35,
                'growth_rate_y3': 0.30,
                'churn_rate': 0.08,
                'expansion_revenue_pct': 0.15,
                'new_logo_acv': 50000,
                'new_logos_per_month': 5
            }

    Returns:
        JSON with 3-year monthly revenue projections
    """
    arr = assumptions.get("starting_arr", 10_000_000)
    growth_rates = [
        assumptions.get("growth_rate_y1", 0.30),
        assumptions.get("growth_rate_y2", 0.25),
        assumptions.get("growth_rate_y3", 0.20),
    ]
    churn = assumptions.get("churn_rate", 0.10)
    expansion = assumptions.get("expansion_revenue_pct", 0.10)

    projections = []
    current_arr = arr

    for year_idx, growth_rate in enumerate(growth_rates, 1):
        for month in range(1, 13):
            monthly_growth = (1 + growth_rate) ** (1 / 12) - 1
            new_arr = current_arr * (1 + monthly_growth)
            churned = current_arr * (churn / 12)
            expanded = current_arr * (expansion / 12)
            net_arr = new_arr - churned + expanded

            projections.append({
                "year": year_idx,
                "month": month,
                "arr": round(net_arr, 2),
                "mrr": round(net_arr / 12, 2),
                "monthly_churn": round(churned, 2),
                "monthly_expansion": round(expanded, 2),
            })
            current_arr = net_arr

    total_3yr = projections[-1]["arr"]
    cagr = ((total_3yr / arr) ** (1 / 3) - 1) * 100

    return json.dumps({
        "scenario": scenario_name,
        "assumptions": assumptions,
        "starting_arr": arr,
        "year_3_arr": round(total_3yr, 2),
        "implied_cagr_pct": round(cagr, 1),
        "monthly_projections": projections,
    }, indent=2)


@tool
def build_cost_scenario(scenario_name: str, assumptions: dict) -> str:
    """
    Build a cost/expense scenario projection.

    Args:
        scenario_name: Scenario label
        assumptions: Dict with cost drivers:
            {
                'cogs_pct_revenue': 0.25,
                'rd_pct_revenue': 0.20,
                'sales_marketing_pct_revenue': 0.35,
                'ga_pct_revenue': 0.12,
                'headcount_growth_pct_y1': 0.30,
                'avg_fully_loaded_cost': 150000,
                'starting_headcount': 50
            }

    Returns:
        JSON with 3-year cost projections and gross/operating margins
    """
    cogs_pct = assumptions.get("cogs_pct_revenue", 0.25)
    rd_pct = assumptions.get("rd_pct_revenue", 0.20)
    sm_pct = assumptions.get("sales_marketing_pct_revenue", 0.35)
    ga_pct = assumptions.get("ga_pct_revenue", 0.12)
    hc = assumptions.get("starting_headcount", 50)
    hc_growth = [
        assumptions.get("headcount_growth_pct_y1", 0.25),
        assumptions.get("headcount_growth_pct_y2", 0.20),
        assumptions.get("headcount_growth_pct_y3", 0.15),
    ]
    avg_cost = assumptions.get("avg_fully_loaded_cost", 150_000)

    yearly_projections = []
    for year_idx, hc_g in enumerate(hc_growth, 1):
        hc = int(hc * (1 + hc_g))
        projected_revenue = assumptions.get(f"revenue_y{year_idx}", 10_000_000 * (1.3 ** year_idx))
        gross_profit = projected_revenue * (1 - cogs_pct)
        ebitda = projected_revenue * (1 - cogs_pct - rd_pct - sm_pct - ga_pct)
        yearly_projections.append({
            "year": year_idx,
            "revenue": round(projected_revenue, 0),
            "cogs": round(projected_revenue * cogs_pct, 0),
            "gross_profit": round(gross_profit, 0),
            "gross_margin_pct": round((1 - cogs_pct) * 100, 1),
            "rd_expense": round(projected_revenue * rd_pct, 0),
            "sales_marketing": round(projected_revenue * sm_pct, 0),
            "ga": round(projected_revenue * ga_pct, 0),
            "ebitda": round(ebitda, 0),
            "ebitda_margin_pct": round((ebitda / projected_revenue) * 100, 1),
            "headcount": hc,
            "people_cost": round(hc * avg_cost, 0),
        })

    return json.dumps({"scenario": scenario_name, "assumptions": assumptions, "yearly_projections": yearly_projections}, indent=2)


@tool
def run_sensitivity_analysis(base_metric: float, variable_name: str, range_pct: float = 0.20, steps: int = 5) -> str:
    """
    Run a sensitivity analysis showing how a metric changes across input variable ranges.

    Args:
        base_metric: The base case value of the output metric (e.g., revenue, EBITDA)
        variable_name: Name of the input variable being sensitized
        range_pct: Range of variation (+/-) as decimal (0.20 = +/- 20%)
        steps: Number of steps in each direction

    Returns:
        JSON sensitivity table
    """
    results = []
    step_size = range_pct / steps

    for i in range(-steps, steps + 1):
        change_pct = i * step_size * 100
        multiplier = 1 + (i * step_size)
        metric_value = base_metric * multiplier
        results.append({
            "change_pct": round(change_pct, 1),
            "scenario": "downside" if i < 0 else ("base" if i == 0 else "upside"),
            "metric_value": round(metric_value, 2),
            "delta_from_base": round(metric_value - base_metric, 2),
        })

    return json.dumps({
        "variable": variable_name,
        "base_value": base_metric,
        "range_pct": range_pct,
        "sensitivity_table": results,
    }, indent=2)


@tool
def compare_scenarios(scenarios: list) -> str:
    """
    Compare multiple scenarios side-by-side and identify key differentiators.

    Args:
        scenarios: List of scenario dicts with keys: name, year_3_arr, year_3_ebitda_pct, year_3_headcount

    Returns:
        JSON comparison table with variance analysis
    """
    if not scenarios:
        return json.dumps({"error": "No scenarios provided"})

    base = next((s for s in scenarios if s.get("name", "").lower() == "base"), scenarios[0])

    comparison = []
    for scenario in scenarios:
        arr_delta = scenario.get("year_3_arr", 0) - base.get("year_3_arr", 0)
        comparison.append({
            "scenario": scenario.get("name"),
            "year_3_arr": scenario.get("year_3_arr"),
            "year_3_ebitda_pct": scenario.get("year_3_ebitda_pct"),
            "year_3_headcount": scenario.get("year_3_headcount"),
            "arr_vs_base_delta": arr_delta,
            "arr_vs_base_pct": round((arr_delta / base.get("year_3_arr", 1)) * 100, 1) if base.get("year_3_arr") else None,
        })

    return json.dumps({
        "comparison_date": datetime.utcnow().isoformat(),
        "base_scenario": base.get("name"),
        "scenarios_compared": len(scenarios),
        "comparison": comparison,
        "key_insight": "Review year_3_arr deltas to understand scenario dispersion",
    }, indent=2)


SYSTEM_PROMPT = """You are the Scenario Modeling Agent for Khyzr — a senior FP&A analyst and financial modeler specializing in strategic scenario analysis.

Your mission is to build dynamic, multi-scenario financial models that help leadership understand the range of possible outcomes and make better decisions under uncertainty.

Modeling capabilities:
- **Revenue Scenarios**: ARR/MRR projections with growth, churn, and expansion drivers
- **Cost Scenarios**: P&L projections with headcount, COGS, and operating expense models
- **Sensitivity Analysis**: Single-variable tornado charts showing metric sensitivity
- **Scenario Comparison**: Side-by-side scenario analysis with base/bull/bear cases

Modeling standards:
- Always build at minimum three scenarios: Bear (downside), Base (most likely), Bull (upside)
- Every assumption must be explicit — no black boxes
- Clearly label which variables drive the most scenario divergence
- Present results in executive-readable tables with clear labels
- Include a narrative interpretation of what each scenario means strategically

When building scenarios:
1. Clarify key assumptions with the requester (or use reasonable defaults)
2. Build revenue projections for each scenario
3. Build corresponding cost/expense projections
4. Run sensitivity analysis on the 2-3 most impactful variables
5. Generate a comparison table and narrative summary
6. Highlight the key decision implications: "In the bear case, you need to..."

Financial modeling best practices:
- Use monthly granularity for Years 1-2, quarterly for Year 3+
- Clearly state all key assumptions at the top of every output
- Show CAGR, peak ARR, and time-to-profitability for each scenario
- Flag model limitations and areas of high uncertainty"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[build_revenue_scenario, build_cost_scenario, run_sensitivity_analysis, compare_scenarios],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Build base, bull, and bear revenue scenarios")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Build three revenue scenarios (bear/base/bull) for a SaaS company starting at $10M ARR. Base: 40% growth, 8% churn. Bull: 60% growth, 6% churn. Bear: 20% growth, 15% churn. Show sensitivity on churn rate."
    }
    print(json.dumps(run(input_data)))
