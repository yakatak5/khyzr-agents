"""
Briefing Agent
==============
Aggregates relevant data points, risks, and talking points ahead of 
executive meetings or board sessions. Produces concise, structured briefing 
documents that give leaders exactly what they need to walk in prepared.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def gather_meeting_context(meeting_topic: str, attendees: list, meeting_date: str) -> str:
    """
    Gather contextual information relevant to an upcoming meeting.

    Args:
        meeting_topic: Topic or title of the meeting
        attendees: List of attendee names/roles
        meeting_date: Date of meeting (YYYY-MM-DD)

    Returns:
        JSON context object with meeting metadata and data gathering checklist
    """
    context = {
        "meeting_topic": meeting_topic,
        "meeting_date": meeting_date,
        "attendees": attendees,
        "days_until_meeting": (datetime.strptime(meeting_date, "%Y-%m-%d") - datetime.utcnow()).days if meeting_date else 0,
        "context_gathering_checklist": {
            "recent_company_news": "Last 30 days of relevant internal/external news",
            "kpi_snapshot": "Current state of key metrics relevant to topic",
            "prior_meeting_actions": "Outstanding action items from previous sessions",
            "stakeholder_positions": "Known positions/concerns of each attendee",
            "relevant_documents": "Strategy docs, reports, analyses related to topic",
            "risk_register_items": "Active risks germane to discussion topics",
            "competitive_intelligence": "Relevant competitor moves or market developments",
        },
        "recommended_sections": [
            "One-Page Summary", "Key Metrics", "Agenda Items with Context",
            "Risks & Escalations", "Pre-Read Materials", "Suggested Decisions",
        ],
    }
    return json.dumps(context, indent=2)


@tool
def fetch_recent_actions_and_decisions(owner: str = None, days_back: int = 30) -> str:
    """
    Retrieve outstanding action items and recent decisions from tracking systems.

    Args:
        owner: Filter by specific owner (optional - None returns all)
        days_back: How far back to look for recent decisions

    Returns:
        JSON list of open actions and recent decisions
    """
    table_name = os.environ.get("ACTIONS_TABLE_NAME")
    actions = []

    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            scan_params = {"FilterExpression": "attribute_not_exists(completed) OR completed = :f",
                          "ExpressionAttributeValues": {":f": False}}
            if owner:
                scan_params["FilterExpression"] += " AND #owner = :o"
                scan_params["ExpressionAttributeNames"] = {"#owner": "owner"}
                scan_params["ExpressionAttributeValues"][":o"] = owner
            response = table.scan(**scan_params)
            actions = response.get("Items", [])
        except Exception as e:
            actions = [{"error": str(e)}]
    else:
        cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
        actions = [
            {
                "id": "ACT-001",
                "description": "Review Q3 budget variance and prepare corrective actions",
                "owner": owner or "CFO",
                "due_date": (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d"),
                "status": "in_progress",
                "priority": "high",
                "note": "Configure ACTIONS_TABLE_NAME for real tracking",
            }
        ]

    return json.dumps({"actions": actions, "owner_filter": owner, "retrieved_at": datetime.utcnow().isoformat()}, indent=2)


@tool
def compile_risk_register(category: str = None, severity: str = None) -> str:
    """
    Compile relevant items from the risk register for meeting context.

    Args:
        category: Filter by category ('strategic', 'operational', 'financial', 'reputational')
        severity: Filter by severity ('critical', 'high', 'medium', 'low')

    Returns:
        JSON list of risk register items
    """
    bucket = os.environ.get("RISK_DATA_BUCKET")
    risks = []

    if bucket:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        try:
            obj = s3.get_object(Bucket=bucket, Key="risk-register/current.json")
            all_risks = json.loads(obj["Body"].read())
            risks = [r for r in all_risks
                     if (not category or r.get("category") == category)
                     and (not severity or r.get("severity") == severity)]
        except Exception as e:
            risks = [{"error": str(e)}]
    else:
        risks = [
            {
                "risk_id": "RSK-007",
                "title": "Key person dependency in engineering leadership",
                "category": "operational",
                "severity": "high",
                "likelihood": "medium",
                "mitigation": "Succession planning in progress; hiring VP Engineering",
                "owner": "CEO",
                "last_reviewed": datetime.utcnow().strftime("%Y-%m-%d"),
            }
        ]

    return json.dumps({"risks": risks, "filters": {"category": category, "severity": severity}}, indent=2)


@tool
def draft_executive_briefing(meeting_context: dict, format: str = "one_pager") -> str:
    """
    Draft a structured executive briefing document.

    Args:
        meeting_context: Dict with meeting details, topics, attendees, risks, actions
        format: 'one_pager', 'detailed', or 'talking_points'

    Returns:
        JSON briefing structure template for agent to populate
    """
    template = {
        "format": format,
        "briefing_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "meeting": meeting_context,
        "structure": {
            "one_pager": {
                "section_1": "Situation Summary (3-5 sentences: what's happening, why it matters)",
                "section_2": "Key Metrics (5-7 most relevant numbers with deltas)",
                "section_3": "Key Risks (top 3 with mitigation status)",
                "section_4": "Open Actions (outstanding items from prior sessions)",
                "section_5": "Suggested Decisions Needed (specific asks of attendees)",
                "section_6": "Pre-Read Links (documents to review ahead of meeting)",
            },
            "talking_points": {
                "opening": "How to frame the meeting objective",
                "key_points": "3-5 main points to communicate",
                "anticipated_questions": "Likely questions with prepared responses",
                "ask": "Specific decision or alignment needed",
                "close": "Next steps and owner assignments",
            },
            "detailed": {
                "executive_summary": "2-paragraph overview",
                "background": "Context and history",
                "current_state": "Where things stand today",
                "options": "Decision options with pros/cons",
                "recommendation": "Preferred path with rationale",
                "risks": "Key risks of recommendation",
                "next_steps": "Concrete actions with owners and dates",
            },
        }.get(format, {}),
    }
    return json.dumps(template, indent=2)


@tool
def save_briefing(briefing_content: str, meeting_name: str) -> str:
    """
    Save the completed briefing document to S3.

    Args:
        briefing_content: Full briefing in markdown
        meeting_name: Meeting identifier for file naming

    Returns:
        S3 URI of saved briefing
    """
    bucket = os.environ.get("BRIEFINGS_BUCKET", "khyzr-executive-briefings")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    key = f"briefings/{timestamp}-{meeting_name.replace(' ', '-').lower()}.md"
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=briefing_content.encode("utf-8"), ContentType="text/markdown")
        return json.dumps({"status": "saved", "s3_uri": f"s3://{bucket}/{key}"})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


SYSTEM_PROMPT = """You are the Briefing Agent for Khyzr — a chief of staff and executive communications specialist who prepares leaders for every important meeting and conversation.

Your mission is to ensure that executives walk into any meeting fully prepared: armed with the right data, aware of key risks, clear on outstanding actions, and knowing exactly what decisions need to be made.

Briefing principles you follow:
- **Brevity is a feature**: One page is better than ten. Every word must earn its place.
- **So what before what**: Always lead with the implication, not just the fact.
- **Decision-focused**: Every briefing must clearly identify what decisions are needed and by whom.
- **No surprises**: Surface risks and awkward topics in advance so leaders can prepare.
- **Stakeholder awareness**: Brief on the likely positions and concerns of all attendees.

Briefing types you create:
1. **Board/Investor Briefings**: High-level, strategic, financially-grounded
2. **Leadership Team Briefings**: Operational context, cross-functional dependencies, escalations
3. **Customer/Partner Meeting Prep**: Relationship history, open issues, objectives, talking points
4. **Board Sub-Committee Sessions**: Audit, compensation, risk committee-specific materials
5. **Executive 1-on-1s**: Performance context, relationship notes, agenda items

Process:
1. Understand the meeting: topic, attendees, date, objectives
2. Gather relevant context: recent metrics, open actions, risks, background documents
3. Compile risk register items relevant to the discussion
4. Draft the briefing in the appropriate format (one-pager, talking points, or detailed brief)
5. Save the completed briefing to S3

Write briefings that are crisp, factual, and respectful of executive time. A great briefing answers: What's happening? Why does it matter? What do we need to decide?"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[gather_meeting_context, fetch_recent_actions_and_decisions, compile_risk_register, draft_executive_briefing, save_briefing],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Prepare briefing for upcoming board meeting")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Prepare a one-page briefing for a Board meeting on 2025-10-15. Topic: Q3 performance review and Q4 plan. Attendees: CEO, CFO, 3 board members. Include open actions, key risks, and the decisions needed."
    }
    print(json.dumps(run(input_data)))
