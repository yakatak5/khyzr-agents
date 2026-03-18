"""
Process Intelligence Agent
==========================
Analyzes operational workflow data to identify throughput bottlenecks,
measure cycle times, and recommend corrective actions to improve efficiency.

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
def analyze_workflow_data(workflow_id: str, time_period_days: int = 30) -> str:
    """
    Analyze workflow data for a given process over a specified time period.

    Args:
        workflow_id: Identifier for the workflow/process to analyze
        time_period_days: Number of days of historical data to analyze

    Returns:
        JSON string with workflow steps, average durations, and volume metrics
    """
    # Simulated workflow data - in production, pulls from process mining DB or event logs
    workflow_data = {
        "workflow_id": workflow_id,
        "analysis_period_days": time_period_days,
        "total_cases": 1250,
        "completed_cases": 1180,
        "in_progress_cases": 70,
        "steps": [
            {"step": "intake", "avg_duration_hours": 2.1, "volume": 1250, "completion_rate": 0.99},
            {"step": "validation", "avg_duration_hours": 4.8, "volume": 1245, "completion_rate": 0.94},
            {"step": "processing", "avg_duration_hours": 18.5, "volume": 1170, "completion_rate": 0.88},
            {"step": "review", "avg_duration_hours": 12.3, "volume": 1030, "completion_rate": 0.97},
            {"step": "approval", "avg_duration_hours": 36.2, "volume": 999, "completion_rate": 0.92},
            {"step": "completion", "avg_duration_hours": 1.5, "volume": 919, "completion_rate": 0.99},
        ],
        "avg_end_to_end_hours": 75.4,
        "sla_target_hours": 72.0,
        "sla_breach_rate": 0.18,
        "generated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(workflow_data, indent=2)


@tool
def identify_bottlenecks(workflow_data: str) -> str:
    """
    Identify throughput bottlenecks from analyzed workflow data.

    Args:
        workflow_data: JSON string from analyze_workflow_data

    Returns:
        JSON string identifying bottleneck steps, severity, and contributing factors
    """
    try:
        data = json.loads(workflow_data)
        steps = data.get("steps", [])
    except Exception:
        steps = []

    bottlenecks = []
    for step in steps:
        duration = step.get("avg_duration_hours", 0)
        completion = step.get("completion_rate", 1.0)
        volume = step.get("volume", 0)

        severity = "low"
        factors = []

        if duration > 24:
            severity = "high"
            factors.append(f"High average duration ({duration:.1f}h)")
        elif duration > 8:
            severity = "medium"
            factors.append(f"Elevated duration ({duration:.1f}h)")

        if completion < 0.90:
            severity = "high"
            factors.append(f"Low completion rate ({completion*100:.0f}%)")
        elif completion < 0.95:
            if severity != "high":
                severity = "medium"
            factors.append(f"Below-target completion ({completion*100:.0f}%)")

        if factors:
            bottlenecks.append({
                "step": step.get("step"),
                "severity": severity,
                "avg_duration_hours": duration,
                "completion_rate": completion,
                "contributing_factors": factors,
            })

    bottlenecks.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["severity"]])
    return json.dumps({"bottlenecks": bottlenecks, "total_identified": len(bottlenecks)}, indent=2)


@tool
def calculate_process_metrics(workflow_id: str) -> str:
    """
    Calculate key process performance indicators including throughput, cycle time, and efficiency.

    Args:
        workflow_id: Identifier for the workflow to measure

    Returns:
        JSON string with KPIs: throughput rate, cycle time percentiles, WIP, efficiency ratio
    """
    metrics = {
        "workflow_id": workflow_id,
        "calculated_at": datetime.utcnow().isoformat(),
        "throughput": {
            "cases_per_day": 39.3,
            "cases_per_week": 275.2,
            "trend_vs_prior_period": "+4.2%",
        },
        "cycle_time_hours": {
            "p50_median": 68.5,
            "p75": 82.1,
            "p90": 104.7,
            "p95": 128.3,
            "avg": 75.4,
        },
        "work_in_progress": {
            "current_wip": 70,
            "avg_wip": 64.8,
            "max_wip_observed": 112,
        },
        "efficiency_metrics": {
            "process_efficiency": 0.72,
            "rework_rate": 0.08,
            "first_pass_yield": 0.84,
            "sla_compliance_rate": 0.82,
        },
        "little_law_validation": {
            "theoretical_cycle_time_hours": 64.2,
            "actual_vs_theoretical_ratio": 1.17,
            "excess_wip_indicator": True,
        },
    }
    return json.dumps(metrics, indent=2)


@tool
def generate_improvement_recommendations(bottlenecks: str, metrics: str) -> str:
    """
    Generate prioritized improvement recommendations based on bottleneck analysis and metrics.

    Args:
        bottlenecks: JSON string from identify_bottlenecks
        metrics: JSON string from calculate_process_metrics

    Returns:
        JSON string with ranked improvement recommendations and expected impact
    """
    try:
        bn_data = json.loads(bottlenecks)
        bn_list = bn_data.get("bottlenecks", [])
    except Exception:
        bn_list = []

    recommendations = [
        {
            "priority": 1,
            "recommendation": "Automate approval routing with rules-based engine",
            "target_step": "approval",
            "expected_cycle_time_reduction_pct": 40,
            "expected_roi": "High",
            "effort": "Medium",
            "implementation_weeks": 6,
            "rationale": "Approval step accounts for 48% of total cycle time; most cases follow predictable rules.",
        },
        {
            "priority": 2,
            "recommendation": "Implement parallel processing for validation and initial review",
            "target_step": "validation",
            "expected_cycle_time_reduction_pct": 25,
            "expected_roi": "High",
            "effort": "Low",
            "implementation_weeks": 2,
            "rationale": "Validation and early review can run concurrently, eliminating sequential wait time.",
        },
        {
            "priority": 3,
            "recommendation": "Add real-time WIP limits and queue management",
            "target_step": "processing",
            "expected_cycle_time_reduction_pct": 15,
            "expected_roi": "Medium",
            "effort": "Low",
            "implementation_weeks": 3,
            "rationale": "WIP exceeds optimal levels, causing queueing delays in the processing stage.",
        },
        {
            "priority": 4,
            "recommendation": "Introduce intake pre-screening to reduce downstream rework",
            "target_step": "intake",
            "expected_cycle_time_reduction_pct": 10,
            "expected_roi": "Medium",
            "effort": "Medium",
            "implementation_weeks": 4,
            "rationale": "Rework rate of 8% adds significant hidden cycle time; earlier quality checks reduce this.",
        },
    ]

    return json.dumps({
        "recommendations": recommendations,
        "total_potential_cycle_time_reduction_pct": 55,
        "highest_priority_action": recommendations[0]["recommendation"],
        "generated_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def save_process_report(report_content: str, workflow_id: str, report_type: str = "analysis") -> str:
    """
    Save a process intelligence report to S3.

    Args:
        report_content: The full report in markdown or JSON format
        workflow_id: Workflow identifier for organizing reports
        report_type: Type of report (analysis, bottleneck, recommendations)

    Returns:
        JSON string with storage status and S3 URI
    """
    bucket = os.environ.get("REPORTS_BUCKET", "khyzr-process-reports")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    key = f"process-intelligence/{workflow_id}/{report_type}/{timestamp}.md"

    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=report_content.encode("utf-8"),
            ContentType="text/markdown",
            Metadata={"workflow_id": workflow_id, "report_type": report_type},
        )
        return json.dumps({"status": "saved", "s3_uri": f"s3://{bucket}/{key}", "key": key})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e), "note": "Report generated but not persisted."})


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Process Intelligence Agent for Khyzr — an expert in operational process analysis, workflow optimization, and continuous improvement methodologies.

Your mission is to analyze operational workflow data, identify throughput bottlenecks, measure process performance, and deliver prioritized recommendations that drive efficiency gains.

When analyzing a process or workflow:
1. Retrieve and analyze workflow execution data for the specified time period
2. Calculate key process metrics: throughput, cycle time (P50/P75/P90/P95), WIP levels, and efficiency ratios
3. Identify bottlenecks using duration analysis, completion rates, and Little's Law validation
4. Classify bottleneck severity (High/Medium/Low) with supporting evidence
5. Generate prioritized improvement recommendations with expected ROI and implementation effort
6. Save the complete analysis report to S3 for stakeholder review

Your analysis framework draws on Lean Six Sigma, Theory of Constraints, and process mining principles. You understand:
- **Cycle Time vs. Lead Time**: Distinguish between value-add and wait time
- **Throughput Analysis**: Measure flow rates and identify capacity constraints
- **WIP Management**: Apply Little's Law to diagnose queueing issues
- **Bottleneck Theory**: Identify the constraint step that limits overall throughput
- **First Pass Yield**: Quantify rework's hidden impact on capacity

When presenting findings:
- Lead with the most critical bottleneck and its business impact
- Quantify everything: reduction percentages, hours saved, SLA improvement
- Rank recommendations by ROI/effort ratio (quick wins first)
- Flag SLA breach risks with 🚨 when breach rate exceeds 15%
- Format reports in clean markdown with executive summary upfront

Always maintain a data-driven, objective tone. Your goal is actionable insight, not just metrics."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[
        analyze_workflow_data,
        identify_bottlenecks,
        calculate_process_metrics,
        generate_improvement_recommendations,
        save_process_report,
    ],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Analyze workflow WF-001 for the last 30 days and identify bottlenecks")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Analyze workflow WF-001 for the past 30 days. Identify bottlenecks, calculate metrics, and generate improvement recommendations."
    }
    print(json.dumps(run(input_data)))
