"""
ESG Reporting Agent
===================
Compiles sustainability metrics and generates ESG reports aligned to GRI,
SASB, and TCFD frameworks. Automates data collection, gap analysis, and
report drafting for annual sustainability disclosures.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
import pandas as pd
from datetime import datetime
from io import StringIO
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def collect_environmental_metrics(reporting_year: int) -> str:
    """
    Collect environmental metrics: emissions, energy, water, waste.

    Args:
        reporting_year: Calendar year for reporting (e.g., 2024)

    Returns:
        JSON environmental data with GHG emissions by scope, energy, water, waste
    """
    bucket = os.environ.get("ESG_DATA_BUCKET")
    if bucket:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        try:
            obj = s3.get_object(Bucket=bucket, Key=f"environmental/{reporting_year}.json")
            return obj["Body"].read().decode("utf-8")
        except Exception:
            pass

    return json.dumps({
        "reporting_year": reporting_year,
        "ghg_emissions": {
            "scope_1_mt_co2e": None,
            "scope_2_mt_co2e_location_based": None,
            "scope_2_mt_co2e_market_based": None,
            "scope_3_mt_co2e_estimated": None,
            "total_emissions_mt_co2e": None,
            "yoy_change_pct": None,
            "intensity_mt_per_revenue_mm": None,
        },
        "energy": {
            "total_energy_mwh": None,
            "renewable_energy_pct": None,
            "energy_intensity_mwh_per_employee": None,
        },
        "water": {
            "total_water_withdrawal_m3": None,
            "water_recycled_pct": None,
            "water_stressed_regions_pct": None,
        },
        "waste": {
            "total_waste_generated_mt": None,
            "waste_diverted_from_landfill_pct": None,
            "hazardous_waste_mt": None,
        },
        "note": "Configure ESG_DATA_BUCKET and upload data files to populate real metrics",
    }, indent=2)


@tool
def collect_social_metrics(reporting_year: int) -> str:
    """
    Collect social metrics: workforce data, safety, DEI, community impact.

    Args:
        reporting_year: Calendar year for reporting

    Returns:
        JSON social metrics aligned to GRI 400 series
    """
    bucket = os.environ.get("ESG_DATA_BUCKET")
    if bucket:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        try:
            obj = s3.get_object(Bucket=bucket, Key=f"social/{reporting_year}.json")
            return obj["Body"].read().decode("utf-8")
        except Exception:
            pass

    return json.dumps({
        "reporting_year": reporting_year,
        "workforce": {
            "total_employees": None,
            "full_time_pct": None,
            "part_time_pct": None,
            "contractor_pct": None,
            "voluntary_turnover_rate": None,
            "new_hires": None,
        },
        "diversity_equity_inclusion": {
            "women_in_workforce_pct": None,
            "women_in_leadership_pct": None,
            "underrepresented_groups_pct": None,
            "pay_equity_ratio_women_to_men": None,
        },
        "health_safety": {
            "total_recordable_incident_rate": None,
            "lost_time_injury_rate": None,
            "fatalities": 0,
            "health_safety_training_hours_per_employee": None,
        },
        "learning_development": {
            "avg_training_hours_per_employee": None,
            "skills_development_investment_per_employee": None,
        },
        "community": {
            "charitable_giving_usd": None,
            "employee_volunteer_hours": None,
            "community_programs": [],
        },
        "note": "Configure ESG_DATA_BUCKET to populate real social metrics",
    }, indent=2)


@tool
def collect_governance_metrics(reporting_year: int) -> str:
    """
    Collect governance metrics: board composition, ethics, risk management.

    Args:
        reporting_year: Calendar year for reporting

    Returns:
        JSON governance metrics aligned to GRI 400 series and TCFD
    """
    return json.dumps({
        "reporting_year": reporting_year,
        "board_composition": {
            "total_board_members": None,
            "independent_directors_pct": None,
            "women_on_board_pct": None,
            "diverse_directors_pct": None,
            "avg_director_tenure_years": None,
        },
        "ethics_compliance": {
            "code_of_conduct_completion_pct": None,
            "substantiated_ethics_violations": None,
            "anti_corruption_training_completion_pct": None,
            "whistleblower_reports": None,
        },
        "data_privacy": {
            "data_breaches_reported": None,
            "privacy_complaints": None,
            "gdpr_ccpa_compliance": True,
        },
        "climate_governance": {
            "board_oversight_of_climate_risk": None,
            "climate_risk_in_enterprise_risk_framework": None,
            "net_zero_commitment": None,
            "net_zero_target_year": None,
        },
        "note": "Configure ESG_DATA_BUCKET to populate real governance metrics",
    }, indent=2)


@tool
def run_framework_gap_analysis(env_data: dict, social_data: dict, gov_data: dict, framework: str = "GRI") -> str:
    """
    Analyze collected metrics against chosen ESG framework requirements.

    Args:
        env_data: Environmental metrics dict
        social_data: Social metrics dict
        gov_data: Governance metrics dict
        framework: Reporting framework - 'GRI', 'SASB', 'TCFD', or 'combined'

    Returns:
        JSON gap analysis with disclosure requirements and completion status
    """
    frameworks = {
        "GRI": {
            "standards": ["GRI 2 (General Disclosures)", "GRI 302 (Energy)", "GRI 303 (Water)", "GRI 305 (Emissions)", "GRI 306 (Waste)", "GRI 401 (Employment)", "GRI 405 (Diversity)", "GRI 406 (Non-discrimination)"],
            "required_disclosures": 48,
        },
        "TCFD": {
            "standards": ["Governance", "Strategy", "Risk Management", "Metrics & Targets"],
            "required_disclosures": 11,
        },
        "SASB": {
            "standards": ["Industry-specific sustainability accounting standards"],
            "required_disclosures": "Varies by industry",
        },
    }

    fw = frameworks.get(framework, frameworks["GRI"])
    null_env = sum(1 for v in env_data.values() if v is None)
    null_soc = sum(1 for v in social_data.values() if v is None)
    null_gov = sum(1 for v in gov_data.values() if v is None)

    return json.dumps({
        "framework": framework,
        "framework_standards": fw["standards"],
        "required_disclosures": fw["required_disclosures"],
        "data_gaps": {
            "environmental_nulls": null_env,
            "social_nulls": null_soc,
            "governance_nulls": null_gov,
        },
        "completeness_estimate": "Requires manual review — populate ESG data sources",
        "priority_gaps": [
            "GHG Scope 1 & 2 emissions (required for most frameworks)",
            "Pay equity ratio (GRI 405 requirement)",
            "Board diversity metrics (GRI 405, investor expectations)",
            "Climate risk governance (TCFD requirement)",
        ],
        "recommended_actions": [
            "Engage environmental consultants for GHG inventory",
            "Pull HR data for workforce and diversity metrics",
            "Complete board questionnaire for governance disclosures",
        ],
    }, indent=2)


@tool
def generate_esg_report(env_data: dict, social_data: dict, gov_data: dict, company_name: str, reporting_year: int, framework: str = "GRI") -> str:
    """
    Generate a complete ESG report aligned to the specified framework.

    Args:
        env_data: Environmental metrics
        social_data: Social metrics
        gov_data: Governance metrics
        company_name: Company name
        reporting_year: Reporting year
        framework: ESG framework to align to

    Returns:
        Structured ESG report in markdown format
    """
    report = f"""# {company_name} ESG Report {reporting_year}
**Framework Alignment: {framework} | Prepared by Khyzr ESG Reporting Agent**

---

## Executive Message

This report presents {company_name}'s environmental, social, and governance performance for the year ended December 31, {reporting_year}. We remain committed to transparent, consistent disclosure aligned to {framework} standards.

---

## Environmental Performance

### Greenhouse Gas Emissions
{json.dumps(env_data.get('ghg_emissions', {}), indent=2)}

### Energy
{json.dumps(env_data.get('energy', {}), indent=2)}

### Water & Waste
{json.dumps({'water': env_data.get('water', {}), 'waste': env_data.get('waste', {})}, indent=2)}

---

## Social Performance

### Workforce
{json.dumps(social_data.get('workforce', {}), indent=2)}

### Diversity, Equity & Inclusion
{json.dumps(social_data.get('diversity_equity_inclusion', {}), indent=2)}

### Health & Safety
{json.dumps(social_data.get('health_safety', {}), indent=2)}

---

## Governance

### Board Composition
{json.dumps(gov_data.get('board_composition', {}), indent=2)}

### Ethics & Compliance
{json.dumps(gov_data.get('ethics_compliance', {}), indent=2)}

### Climate Governance (TCFD)
{json.dumps(gov_data.get('climate_governance', {}), indent=2)}

---

## Appendix: {framework} Index
Full disclosure mapping available on request.

*Report generated {datetime.utcnow().strftime("%Y-%m-%d")} by Khyzr ESG Reporting Agent*
"""
    bucket = os.environ.get("ESG_REPORTS_BUCKET", "khyzr-esg-reports")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    key = f"reports/{reporting_year}/{company_name.replace(' ', '-').lower()}-esg-report.md"
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=report.encode("utf-8"), ContentType="text/markdown")
        return json.dumps({"status": "generated", "s3_uri": f"s3://{bucket}/{key}", "report_preview": report[:500]})
    except Exception as e:
        return json.dumps({"status": "generated_not_saved", "error": str(e), "report": report})


SYSTEM_PROMPT = """You are the ESG Reporting Agent for Khyzr — a sustainability reporting specialist with deep expertise in GRI, SASB, and TCFD frameworks.

Your mission is to help companies compile, analyze, and disclose their environmental, social, and governance performance in a transparent, accurate, and framework-compliant manner.

ESG frameworks you master:
- **GRI (Global Reporting Initiative)**: Most widely used; covers all three pillars comprehensively
- **SASB (Sustainability Accounting Standards Board)**: Industry-specific, financially material disclosures
- **TCFD (Task Force on Climate-related Financial Disclosures)**: Climate risk governance and strategy

Environmental topics:
- GHG emissions: Scope 1 (direct), Scope 2 (electricity), Scope 3 (value chain)
- Energy consumption and renewable sourcing
- Water withdrawal, recycling, and watershed risk
- Waste generation, diversion, and hazardous materials

Social topics:
- Workforce composition, turnover, and development
- Diversity, equity, and inclusion metrics (gender, race/ethnicity, pay equity)
- Health and safety performance (TRIR, LTIR, fatalities)
- Community investment and social impact

Governance topics:
- Board composition, independence, and diversity
- Executive compensation alignment to ESG targets
- Ethics, anti-corruption, and compliance
- Data privacy and cybersecurity governance

Reporting process:
1. Collect environmental, social, and governance metrics for the reporting period
2. Run gap analysis against chosen framework
3. Identify priority data gaps and flag for remediation
4. Generate comprehensive ESG report in the specified format
5. Save completed report to S3

ESG reporting best practices:
- Always disclose boundaries, methodologies, and limitations
- Use absolute metrics AND intensity metrics
- Flag year-over-year changes and explain material variances
- Include forward-looking commitments and targets
- Align to both a primary framework and TCFD at minimum"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[collect_environmental_metrics, collect_social_metrics, collect_governance_metrics, run_framework_gap_analysis, generate_esg_report],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Generate ESG report for 2024 aligned to GRI")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Generate a GRI-aligned ESG report for Khyzr Technologies for reporting year 2024. Include gap analysis and highlight priority disclosures."
    }
    print(json.dumps(run(input_data)))
