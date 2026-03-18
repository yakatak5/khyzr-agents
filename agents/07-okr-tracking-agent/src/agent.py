"""
OKR Tracking Agent
==================
Monitors goal progress across teams, flags misalignments and off-track items,
and surfaces automated progress reports to leadership.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def fetch_okr_data(team: str = None, quarter: str = None) -> str:
    """
    Retrieve OKR data from the tracking system.

    Args:
        team: Specific team to filter (None = all teams)
        quarter: Quarter to retrieve, e.g. 'Q3-2025' (None = current)

    Returns:
        JSON OKR data with objectives, key results, and current progress
    """
    quarter = quarter or f"Q{((datetime.utcnow().month - 1) // 3) + 1}-{datetime.utcnow().year}"
    table_name = os.environ.get("OKR_TABLE_NAME")

    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            scan_params = {"FilterExpression": "#q = :q", "ExpressionAttributeNames": {"#q": "quarter"}, "ExpressionAttributeValues": {":q": quarter}}
            if team:
                scan_params["FilterExpression"] += " AND team = :t"
                scan_params["ExpressionAttributeValues"][":t"] = team
            resp = table.scan(**scan_params)
            return json.dumps({"quarter": quarter, "team": team, "okrs": resp.get("Items", [])}, indent=2)
        except Exception as e:
            pass

    # Demo data structure
    sample_okrs = [
        {
            "id": "OKR-2025-Q3-ENG-01",
            "team": "Engineering",
            "quarter": quarter,
            "objective": "Ship the v3.0 platform ahead of schedule",
            "confidence_score": 7,
            "key_results": [
                {"kr": "Deploy 5 major features", "target": 5, "current": 4, "progress_pct": 80, "status": "on_track"},
                {"kr": "Achieve 99.9% uptime", "target": 99.9, "current": 99.95, "progress_pct": 100, "status": "achieved"},
                {"kr": "Reduce P1 bug count to 0", "target": 0, "current": 2, "progress_pct": 60, "status": "at_risk"},
            ],
        },
        {
            "id": "OKR-2025-Q3-SALES-01",
            "team": "Sales",
            "quarter": quarter,
            "objective": "Hit $5M in new ARR",
            "confidence_score": 5,
            "key_results": [
                {"kr": "Close 25 new enterprise deals", "target": 25, "current": 12, "progress_pct": 48, "status": "off_track"},
                {"kr": "Build pipeline of 3x target", "target": 15000000, "current": 9000000, "progress_pct": 60, "status": "at_risk"},
                {"kr": "Achieve ACV of $200K", "target": 200000, "current": 185000, "progress_pct": 92, "status": "on_track"},
            ],
        },
    ]

    filtered = [o for o in sample_okrs if not team or o["team"] == team]
    return json.dumps({"quarter": quarter, "team": team, "okrs": filtered, "note": "Configure OKR_TABLE_NAME for real data"}, indent=2)


@tool
def calculate_okr_health(okr_data: list) -> str:
    """
    Calculate health scores and flags for a set of OKRs.

    Args:
        okr_data: List of OKR objects from fetch_okr_data

    Returns:
        JSON health analysis with per-objective and per-team scores
    """
    results = []
    for okr in okr_data:
        krs = okr.get("key_results", [])
        avg_progress = sum(kr.get("progress_pct", 0) for kr in krs) / len(krs) if krs else 0
        off_track = [kr for kr in krs if kr.get("status") == "off_track"]
        at_risk = [kr for kr in krs if kr.get("status") == "at_risk"]

        health = "green" if avg_progress >= 70 else ("yellow" if avg_progress >= 40 else "red")
        results.append({
            "objective_id": okr.get("id"),
            "team": okr.get("team"),
            "objective": okr.get("objective"),
            "avg_progress_pct": round(avg_progress, 1),
            "health_status": health,
            "off_track_krs": len(off_track),
            "at_risk_krs": len(at_risk),
            "confidence_score": okr.get("confidence_score"),
            "flag": len(off_track) > 0 or avg_progress < 40,
            "flag_reason": f"{len(off_track)} KRs off track" if off_track else (f"{len(at_risk)} KRs at risk" if at_risk else None),
        })

    overall_health = sum(1 for r in results if r["health_status"] == "green")
    return json.dumps({
        "total_objectives": len(results),
        "green": sum(1 for r in results if r["health_status"] == "green"),
        "yellow": sum(1 for r in results if r["health_status"] == "yellow"),
        "red": sum(1 for r in results if r["health_status"] == "red"),
        "flagged_for_leadership": [r for r in results if r["flag"]],
        "per_objective": results,
    }, indent=2)


@tool
def detect_misalignments(okr_data: list) -> str:
    """
    Detect cross-team misalignments and dependency conflicts in OKRs.

    Args:
        okr_data: List of all OKR objects across teams

    Returns:
        JSON list of detected misalignments and recommendations
    """
    # Analyze for common misalignment patterns
    teams = {}
    for okr in okr_data:
        team = okr.get("team", "Unknown")
        if team not in teams:
            teams[team] = []
        teams[team].append(okr)

    misalignments = []

    # Check for teams with significantly different health scores (may signal dependency issues)
    health_scores = {}
    for okr in okr_data:
        team = okr.get("team", "Unknown")
        krs = okr.get("key_results", [])
        avg = sum(kr.get("progress_pct", 0) for kr in krs) / len(krs) if krs else 0
        health_scores[team] = health_scores.get(team, []) + [avg]

    avg_by_team = {t: sum(scores) / len(scores) for t, scores in health_scores.items()}

    # Flag teams significantly below company average
    if avg_by_team:
        company_avg = sum(avg_by_team.values()) / len(avg_by_team)
        for team, avg in avg_by_team.items():
            if avg < company_avg * 0.7:
                misalignments.append({
                    "type": "team_lagging",
                    "teams_affected": [team],
                    "description": f"{team} is tracking {round(company_avg - avg, 1)}% below company average",
                    "recommendation": f"Immediate leadership review for {team} OKRs; identify blockers",
                    "severity": "high",
                })

    return json.dumps({
        "misalignments_found": len(misalignments),
        "misalignments": misalignments,
        "team_averages": {t: round(v, 1) for t, v in avg_by_team.items()},
        "company_average_pct": round(sum(avg_by_team.values()) / len(avg_by_team), 1) if avg_by_team else 0,
    }, indent=2)


@tool
def generate_okr_report(health_data: dict, quarter: str, format: str = "weekly_digest") -> str:
    """
    Generate an OKR progress report for leadership.

    Args:
        health_data: Output from calculate_okr_health
        quarter: Reporting quarter
        format: 'weekly_digest', 'monthly_deep_dive', or 'board_update'

    Returns:
        JSON report structure template
    """
    report = {
        "report_type": format,
        "quarter": quarter,
        "generated_at": datetime.utcnow().isoformat(),
        "headline_metrics": {
            "objectives_on_track": health_data.get("green", 0),
            "objectives_at_risk": health_data.get("yellow", 0),
            "objectives_off_track": health_data.get("red", 0),
            "total_objectives": health_data.get("total_objectives", 0),
        },
        "sections": {
            "executive_summary": "One paragraph: overall OKR health and top 3 risks",
            "by_team": "Team-by-team breakdown with RAG status",
            "flagged_items": "Off-track and at-risk items requiring leadership attention",
            "wins": "Key results achieved or on track to exceed",
            "blockers": "Known blockers and recommended escalations",
            "recommendations": "Specific actions to improve overall OKR health",
        },
        "flagged_for_escalation": health_data.get("flagged_for_leadership", []),
    }
    return json.dumps(report, indent=2)


SYSTEM_PROMPT = """You are the OKR Tracking Agent for Khyzr — a strategic operations expert and performance management specialist.

Your mission is to ensure organizational goals are transparent, measurable, and on track. You monitor OKR progress across all teams, detect early warning signals, and surface insights that help leadership intervene before misses become failures.

OKR methodology you apply:
- **Objective**: Qualitative, inspirational, time-bound goal
- **Key Results**: 3-5 measurable, binary outcomes per objective
- **Health Scoring**: Green (≥70%), Yellow (40-69%), Red (<40%) progress
- **Confidence Scores**: 1-10 leader confidence in achieving the objective
- **Check-in Cadence**: Weekly updates, monthly reviews, quarterly retrospectives

What you monitor for:
- **Off-track KRs**: KRs with less than expected progress given time elapsed
- **Low confidence scores**: Objectives where teams report <5/10 confidence
- **Cross-team dependencies**: When one team's delay blocks another's KR
- **Misalignments**: Strategic objectives without supporting team OKRs
- **Sandbagging**: KRs with suspiciously easy targets (all green, every quarter)

Reporting formats:
1. **Weekly Digest**: One-page summary, RAG status by team, top flags
2. **Monthly Deep Dive**: Full analysis with trend lines, misalignment detection
3. **Board Update**: Strategic OKR summary with company-level narrative

When tracking OKRs:
1. Fetch current OKR data for requested scope (all teams or specific team)
2. Calculate health scores and flag at-risk/off-track items
3. Detect cross-team misalignments and dependency issues
4. Generate formatted report with escalations
5. Always include specific recommended actions, not just problem identification"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[fetch_okr_data, calculate_okr_health, detect_misalignments, generate_okr_report],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Generate weekly OKR digest for all teams")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Generate a weekly OKR digest for Q3-2025. Flag anything off-track and detect any cross-team misalignments."
    }
    print(json.dumps(run(input_data)))
