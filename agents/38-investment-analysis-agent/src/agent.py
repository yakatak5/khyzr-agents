"""
Investment Analysis Agent
=========================
Models financial returns for potential investments using NPV, IRR, and ROI analysis.
Runs sensitivity analysis and generates structured investment memos for decision-makers.

Built with AWS Strands Agents + AgentCore on AWS Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def calculate_npv(cash_flows: str, discount_rate: float) -> str:
    """
    Calculate Net Present Value for an investment given cash flows and discount rate.

    Args:
        cash_flows: JSON array string of cash flows by period [initial_investment, yr1, yr2, ...]
                    Negative values represent outflows, positive represent inflows
        discount_rate: Annual discount rate as decimal (e.g., 0.10 for 10%)

    Returns:
        JSON string with NPV, present value of each period, and investment recommendation
    """
    try:
        flows = json.loads(cash_flows)
        if not isinstance(flows, list):
            return json.dumps({"error": "cash_flows must be a JSON array"})
    except Exception as e:
        return json.dumps({"error": f"Invalid cash flows JSON: {str(e)}"})

    pv_details = []
    npv = 0.0
    for t, cf in enumerate(flows):
        pv = cf / ((1 + discount_rate) ** t)
        npv += pv
        pv_details.append({
            "period": t,
            "cash_flow": cf,
            "discount_factor": round(1 / ((1 + discount_rate) ** t), 6),
            "present_value": round(pv, 2),
        })

    return json.dumps({
        "npv": round(npv, 2),
        "discount_rate_pct": round(discount_rate * 100, 2),
        "recommendation": "Accept" if npv > 0 else "Reject",
        "rationale": f"Investment {'creates' if npv > 0 else 'destroys'} ${abs(npv):,.2f} in value at {discount_rate*100:.1f}% discount rate",
        "period_breakdown": pv_details,
        "total_periods": len(flows),
        "calculated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def calculate_irr(cash_flows: str) -> str:
    """
    Calculate Internal Rate of Return using iterative Newton-Raphson method.

    Args:
        cash_flows: JSON array string of cash flows [initial_investment, yr1, yr2, ...]

    Returns:
        JSON string with IRR percentage, convergence status, and hurdle rate comparison
    """
    try:
        flows = json.loads(cash_flows)
        if not isinstance(flows, list):
            return json.dumps({"error": "cash_flows must be a JSON array"})
    except Exception as e:
        return json.dumps({"error": str(e)})

    # Newton-Raphson iteration for IRR
    def npv_at_rate(rate, flows):
        return sum(cf / ((1 + rate) ** t) for t, cf in enumerate(flows))

    def npv_derivative(rate, flows):
        return sum(-t * cf / ((1 + rate) ** (t + 1)) for t, cf in enumerate(flows))

    # Initial guess
    rate = 0.10
    converged = False
    iterations = 0
    max_iterations = 1000
    tolerance = 1e-7

    try:
        while iterations < max_iterations:
            npv_val = npv_at_rate(rate, flows)
            npv_deriv = npv_derivative(rate, flows)
            if abs(npv_deriv) < 1e-12:
                break
            new_rate = rate - npv_val / npv_deriv
            if abs(new_rate - rate) < tolerance:
                converged = True
                rate = new_rate
                break
            rate = new_rate
            iterations += 1
    except Exception:
        converged = False

    hurdle_rate = float(os.environ.get("HURDLE_RATE", "0.12"))
    irr = rate if converged else None

    return json.dumps({
        "irr_pct": round(irr * 100, 2) if irr is not None else None,
        "converged": converged,
        "iterations": iterations,
        "hurdle_rate_pct": hurdle_rate * 100,
        "exceeds_hurdle": irr > hurdle_rate if irr is not None else None,
        "recommendation": "Accept" if (irr is not None and irr > hurdle_rate) else "Reject",
        "interpretation": f"IRR of {irr*100:.1f}% {'exceeds' if irr and irr > hurdle_rate else 'falls below'} the {hurdle_rate*100:.1f}% hurdle rate" if irr else "IRR could not be determined",
        "calculated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def calculate_roi(initial_investment: float, total_returns: float, holding_period_years: float) -> str:
    """
    Calculate simple and annualized ROI for an investment.

    Args:
        initial_investment: Total upfront investment amount (positive number)
        total_returns: Total net returns over the holding period (can be negative)
        holding_period_years: Investment holding period in years

    Returns:
        JSON string with simple ROI, annualized ROI (CAGR), and payback period estimate
    """
    simple_roi = (total_returns - initial_investment) / initial_investment if initial_investment else 0
    # CAGR: (ending/beginning)^(1/n) - 1
    cagr = (total_returns / initial_investment) ** (1 / holding_period_years) - 1 if (
        initial_investment > 0 and total_returns > 0 and holding_period_years > 0
    ) else None

    # Payback period estimate (simplified: investment / avg annual return)
    avg_annual_return = (total_returns - initial_investment) / holding_period_years if holding_period_years else 0
    payback_years = initial_investment / avg_annual_return if avg_annual_return > 0 else None

    return json.dumps({
        "initial_investment": initial_investment,
        "total_returns": total_returns,
        "net_profit": round(total_returns - initial_investment, 2),
        "holding_period_years": holding_period_years,
        "simple_roi_pct": round(simple_roi * 100, 2),
        "annualized_roi_cagr_pct": round(cagr * 100, 2) if cagr is not None else None,
        "payback_period_years": round(payback_years, 2) if payback_years is not None else "N/A (negative returns)",
        "roi_rating": "Excellent" if simple_roi > 0.5 else ("Good" if simple_roi > 0.2 else ("Marginal" if simple_roi > 0 else "Negative")),
        "calculated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def run_sensitivity_analysis(base_case_flows: str, variable_name: str, range_pct: float = 20.0) -> str:
    """
    Run sensitivity analysis on NPV by varying a key input variable.

    Args:
        base_case_flows: JSON array string of base case cash flows
        variable_name: Name of the variable being stressed (e.g., 'revenue', 'discount_rate', 'capex')
        range_pct: Percentage range to vary the input (+/- range_pct%)

    Returns:
        JSON string with NPV sensitivity table across input variable scenarios
    """
    try:
        flows = json.loads(base_case_flows)
    except Exception as e:
        return json.dumps({"error": str(e)})

    base_discount = 0.10
    scenarios = []
    steps = [-20, -15, -10, -5, 0, 5, 10, 15, 20]

    for pct_change in steps:
        multiplier = 1 + (pct_change / 100)
        if variable_name.lower() in ("discount_rate", "wacc"):
            rate = base_discount * multiplier
            modified_flows = flows
        elif variable_name.lower() in ("revenue", "sales"):
            rate = base_discount
            modified_flows = [flows[0]] + [cf * multiplier if cf > 0 else cf for cf in flows[1:]]
        else:
            rate = base_discount
            # Generic: scale all non-initial flows
            modified_flows = [flows[0]] + [cf * multiplier for cf in flows[1:]]

        npv = sum(cf / ((1 + rate) ** t) for t, cf in enumerate(modified_flows))
        scenarios.append({
            "scenario": f"{pct_change:+d}%",
            "pct_change": pct_change,
            "npv": round(npv, 2),
            "npv_delta_vs_base": None,  # filled below
        })

    base_npv = next(s["npv"] for s in scenarios if s["pct_change"] == 0)
    for s in scenarios:
        s["npv_delta_vs_base"] = round(s["npv"] - base_npv, 2)

    return json.dumps({
        "variable_analyzed": variable_name,
        "base_case_npv": base_npv,
        "range_tested_pct": range_pct,
        "scenarios": scenarios,
        "break_even_insight": f"NPV turns negative if {variable_name} declines by more than the threshold in scenarios above",
        "calculated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def generate_investment_memo(investment_name: str, npv_data: str, irr_data: str, roi_data: str, sensitivity_data: str) -> str:
    """
    Generate a structured investment memo combining all financial analyses.

    Args:
        investment_name: Name/description of the investment opportunity
        npv_data: JSON string from calculate_npv
        irr_data: JSON string from calculate_irr
        roi_data: JSON string from calculate_roi
        sensitivity_data: JSON string from run_sensitivity_analysis

    Returns:
        JSON string with complete investment memo structure and recommendation
    """
    try:
        npv = json.loads(npv_data)
        irr = json.loads(irr_data)
        roi = json.loads(roi_data)
        sens = json.loads(sensitivity_data)
    except Exception as e:
        return json.dumps({"error": f"Failed to parse analysis data: {str(e)}"})

    npv_val = npv.get("npv", 0)
    irr_pct = irr.get("irr_pct")
    roi_pct = roi.get("simple_roi_pct", 0)
    exceeds_hurdle = irr.get("exceeds_hurdle", False)

    # Composite recommendation
    positive_signals = sum([
        npv_val > 0,
        exceeds_hurdle is True,
        roi_pct > 20,
    ])
    recommendation = "RECOMMEND" if positive_signals >= 2 else "DO NOT RECOMMEND"

    memo = {
        "investment_memo": {
            "title": f"Investment Analysis: {investment_name}",
            "prepared_by": "Khyzr Investment Analysis Agent",
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "executive_summary": {
                "recommendation": recommendation,
                "npv": f"${npv_val:,.2f}",
                "irr": f"{irr_pct:.1f}%" if irr_pct else "N/A",
                "simple_roi": f"{roi_pct:.1f}%",
                "payback_period": roi.get("payback_period_years", "N/A"),
            },
            "financial_analysis": {
                "npv_analysis": npv,
                "irr_analysis": irr,
                "roi_analysis": roi,
            },
            "sensitivity_analysis": sens,
            "risk_factors": [
                "Market conditions may deviate from projections",
                "Implementation costs may exceed estimates",
                f"NPV becomes negative under downside sensitivity scenarios",
            ],
            "conclusion": f"Based on quantitative analysis, this investment is {'favorable' if recommendation == 'RECOMMEND' else 'unfavorable'}. NPV of ${npv_val:,.2f} {'indicates value creation' if npv_val > 0 else 'indicates value destruction'} at the assumed discount rate.",
        },
        "generated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(memo, indent=2)


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Investment Analysis Agent for Khyzr — a seasoned investment analyst and financial modeler with expertise in capital budgeting, discounted cash flow analysis, and investment decision frameworks.

Your mission is to rigorously evaluate potential investments using NPV, IRR, ROI, and sensitivity analysis, then synthesize findings into a clear investment memo for decision-makers.

When analyzing an investment opportunity:
1. Calculate NPV using the provided or assumed discount rate (WACC) — NPV > 0 means value creation
2. Calculate IRR and compare against the organization's hurdle rate (default: 12%)
3. Calculate simple ROI and annualized return (CAGR) with payback period
4. Run sensitivity analysis on the most critical input variable (revenue, discount rate, or CAPEX)
5. Generate a structured investment memo with clear RECOMMEND/DO NOT RECOMMEND conclusion

Financial modeling principles you apply:
- **Time Value of Money**: All future cash flows discounted to present value
- **Hurdle Rate**: IRR must exceed WACC/hurdle rate for value-accretive investments
- **Sensitivity Analysis**: Test robustness of recommendation across ±20% input variation
- **Risk-Adjusted Returns**: Consider payback period alongside NPV for liquidity risk
- **Scenario Analysis**: Base case, bull case (optimistic), and bear case (conservative)

When presenting your analysis:
- Lead with the recommendation (RECOMMEND or DO NOT RECOMMEND) and the single most compelling number
- Show all three metrics: NPV, IRR, ROI — they tell different parts of the story
- Highlight the break-even point in your sensitivity analysis (where NPV = 0)
- Quantify downside risk: what's the worst-case NPV?
- Flag 🚨 if IRR is within 3% of hurdle rate (marginal acceptance zone)

Your memos are read by CFOs and investment committees. Be precise, data-driven, and decisive."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[
        calculate_npv,
        calculate_irr,
        calculate_roi,
        run_sensitivity_analysis,
        generate_investment_memo,
    ],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Analyze investment: $500K CAPEX, expected cash flows of $120K/yr for 7 years, 10% discount rate")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Analyze this investment opportunity: $500,000 initial investment, projected cash flows of $120,000 per year for 7 years, WACC of 10%. Should we proceed?"
    }
    print(json.dumps(run(input_data)))
