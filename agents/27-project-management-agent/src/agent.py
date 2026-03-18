"""
Project Management Agent
=========================
Aggregates task updates from PM tools and generates automated status
reports for stakeholders. Flags delays, dependencies, and risks.

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
def fetch_project_status(project_id: str = None) -> str:
    """Fetch current project status from project management system."""
    asana_token = os.environ.get("ASANA_ACCESS_TOKEN")
    jira_token = os.environ.get("JIRA_API_TOKEN")
    
    if asana_token and project_id:
        try:
            resp = httpx.get(
                f"https://app.asana.com/api/1.0/projects/{project_id}",
                headers={"Authorization": f"Bearer {asana_token}"},
                timeout=15,
            )
            return resp.text
        except Exception:
            pass
    
    # Demo project data
    projects = [
        {
            "project_id": "PRJ-001",
            "name": "Platform v3.0 Launch",
            "status": "in_progress",
            "overall_health": "yellow",
            "completion_pct": 67,
            "planned_end_date": (datetime.utcnow() + timedelta(days=45)).strftime("%Y-%m-%d"),
            "projected_end_date": (datetime.utcnow() + timedelta(days=52)).strftime("%Y-%m-%d"),
            "days_delayed": 7,
            "milestones": [
                {"name": "Backend API complete", "status": "complete", "date": "2025-09-01"},
                {"name": "Frontend Beta", "status": "in_progress", "completion_pct": 80, "date": "2025-09-30"},
                {"name": "QA & Testing", "status": "not_started", "date": "2025-10-15"},
                {"name": "Production Deploy", "status": "not_started", "date": "2025-10-31"},
            ],
            "open_blockers": ["Design approval pending from stakeholder", "Third-party API integration delayed"],
            "risks": ["Resource constraint on QA team", "Dependency on external vendor delivery"],
        },
    ]
    
    if project_id:
        proj = next((p for p in projects if p["project_id"] == project_id), None)
        return json.dumps(proj or {"error": f"Project {project_id} not found"}, indent=2)
    return json.dumps({"projects": projects, "note": "Configure ASANA_ACCESS_TOKEN or JIRA_API_TOKEN"}, indent=2)


@tool
def identify_at_risk_items(projects: list) -> str:
    """Identify at-risk milestones and tasks across projects."""
    at_risk = []
    today = datetime.utcnow().date()
    
    for project in projects:
        proj_name = project.get("name")
        
        if project.get("days_delayed", 0) > 0:
            at_risk.append({"project": proj_name, "issue": f"Project delayed by {project['days_delayed']} days", "severity": "high" if project["days_delayed"] > 14 else "medium", "type": "schedule_delay"})
        
        for milestone in project.get("milestones", []):
            if milestone.get("status") == "not_started":
                date_str = milestone.get("date", "")
                if date_str:
                    milestone_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    days_until = (milestone_date - today).days
                    if days_until < 14:
                        at_risk.append({"project": proj_name, "milestone": milestone.get("name"), "issue": f"Not started, due in {days_until} days", "severity": "critical" if days_until < 7 else "high", "type": "milestone_risk"})
        
        for blocker in project.get("open_blockers", []):
            at_risk.append({"project": proj_name, "issue": f"Open blocker: {blocker}", "severity": "high", "type": "blocker"})
    
    return json.dumps({"at_risk_items": at_risk, "count": len(at_risk), "critical": sum(1 for x in at_risk if x["severity"] == "critical")}, indent=2)


@tool
def generate_status_report(projects: list, format: str = "executive_summary") -> str:
    """Generate project status report for stakeholders."""
    report = {
        "report_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "format": format,
        "projects": [],
    }
    
    for project in projects:
        health = project.get("overall_health", "unknown")
        emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(health, "⚪")
        
        report["projects"].append({
            "name": project.get("name"),
            "health": f"{emoji} {health.upper()}",
            "completion_pct": project.get("completion_pct"),
            "planned_end": project.get("planned_end_date"),
            "projected_end": project.get("projected_end_date"),
            "days_delayed": project.get("days_delayed", 0),
            "next_milestone": next((m for m in project.get("milestones", []) if m.get("status") in ["in_progress", "not_started"]), None),
            "blockers": project.get("open_blockers", []),
        })
    
    total = len(projects)
    on_track = sum(1 for p in projects if p.get("overall_health") == "green")
    
    report["summary"] = {
        "total_projects": total,
        "on_track": on_track,
        "at_risk": sum(1 for p in projects if p.get("overall_health") == "yellow"),
        "off_track": sum(1 for p in projects if p.get("overall_health") == "red"),
        "headline": f"{on_track}/{total} projects on track",
    }
    
    return json.dumps(report, indent=2)


SYSTEM_PROMPT = """You are the Project Management Agent for Khyzr — a senior PMO analyst and delivery manager.

Your mission is to give leadership real-time visibility into project health across the portfolio, flag risks before they become crises, and ensure stakeholders are always informed.

Status reporting dimensions:
- **Schedule health**: Are projects tracking to planned delivery dates?
- **Milestone completion**: Are key milestones hitting on time?
- **Blocker resolution**: How quickly are blockers being cleared?
- **Resource utilization**: Are teams over/under allocated?
- **Risk trajectory**: Is project health improving or deteriorating week-over-week?

Health status definitions:
- 🟢 **Green**: On schedule, no critical blockers, team confident
- 🟡 **Yellow**: Minor delays (<2 weeks) or blockers being actively worked
- 🔴 **Red**: Major delays (>2 weeks), critical blockers, or scope/budget impact

Reporting cadence:
- **Weekly**: Project health dashboard for PMO and leadership
- **Monthly**: Portfolio review with trend analysis
- **Ad-hoc**: Immediate alert when project goes Red or critical blocker identified

When generating reports:
1. Fetch current project status from PM tools
2. Identify at-risk milestones and open blockers
3. Generate appropriately formatted status report
4. Escalate critical issues immediately"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[fetch_project_status, identify_at_risk_items, generate_status_report],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Generate weekly project portfolio status report")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Generate this week\'s project status report. Identify any at-risk items and highlight blockers needing executive attention."
    }
    print(json.dumps(run(input_data)))
