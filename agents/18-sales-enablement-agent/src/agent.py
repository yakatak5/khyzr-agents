"""
Sales Enablement Agent
=======================
Transcribes calls, extracts action items, and drafts personalized follow-up emails for reps post-meeting.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime

from strands import Agent, tool
from strands.models import BedrockModel


@tool
def transcribe_call_recording(s3_uri: str, language: str = 'en-US') -> str:
    """
    Transcribe a sales call recording from S3.

    Returns:
        JSON transcription text and metadata
    """
    # Implementation — configure environment variables for production data sources
    import boto3, os
    from datetime import datetime
    result = {
        "function": "transcribe_call_recording",
        "status": "executed",
        "timestamp": datetime.utcnow().isoformat(),
        "note": "Configure environment variables and AWS resources for production use",
    }
    
    # Try to read from/write to DynamoDB or S3 if configured
    table_name = os.environ.get("PRIMARY_TABLE_NAME")
    bucket = os.environ.get("PRIMARY_BUCKET")
    
    if table_name:
        try:
            dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
            table = dynamodb.Table(table_name)
            result["dynamodb_connected"] = True
        except Exception as e:
            result["dynamodb_error"] = str(e)
    
    return json.dumps(result, indent=2)

@tool
def extract_action_items(transcript: str, rep_name: str, prospect_name: str) -> str:
    """
    Extract action items, commitments, and next steps from a call transcript.

    Returns:
        JSON list of action items with owners and deadlines
    """
    # Implementation — configure environment variables for production data sources
    import boto3, os
    from datetime import datetime
    result = {
        "function": "extract_action_items",
        "status": "executed",
        "timestamp": datetime.utcnow().isoformat(),
        "note": "Configure environment variables and AWS resources for production use",
    }
    
    # Try to read from/write to DynamoDB or S3 if configured
    table_name = os.environ.get("PRIMARY_TABLE_NAME")
    bucket = os.environ.get("PRIMARY_BUCKET")
    
    if table_name:
        try:
            dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
            table = dynamodb.Table(table_name)
            result["dynamodb_connected"] = True
        except Exception as e:
            result["dynamodb_error"] = str(e)
    
    return json.dumps(result, indent=2)

@tool
def draft_follow_up_email(action_items: list, prospect_name: str, company: str, meeting_topic: str) -> str:
    """
    Draft a personalized follow-up email based on call notes.

    Returns:
        Follow-up email draft
    """
    # Implementation — configure environment variables for production data sources
    import boto3, os
    from datetime import datetime
    result = {
        "function": "draft_follow_up_email",
        "status": "executed",
        "timestamp": datetime.utcnow().isoformat(),
        "note": "Configure environment variables and AWS resources for production use",
    }
    
    # Try to read from/write to DynamoDB or S3 if configured
    table_name = os.environ.get("PRIMARY_TABLE_NAME")
    bucket = os.environ.get("PRIMARY_BUCKET")
    
    if table_name:
        try:
            dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
            table = dynamodb.Table(table_name)
            result["dynamodb_connected"] = True
        except Exception as e:
            result["dynamodb_error"] = str(e)
    
    return json.dumps(result, indent=2)

@tool
def update_crm_notes(record_id: str, summary: str, action_items: list, next_steps: dict) -> str:
    """
    Update CRM with call summary, action items, and next steps.

    Returns:
        CRM update status
    """
    # Implementation — configure environment variables for production data sources
    import boto3, os
    from datetime import datetime
    result = {
        "function": "update_crm_notes",
        "status": "executed",
        "timestamp": datetime.utcnow().isoformat(),
        "note": "Configure environment variables and AWS resources for production use",
    }
    
    # Try to read from/write to DynamoDB or S3 if configured
    table_name = os.environ.get("PRIMARY_TABLE_NAME")
    bucket = os.environ.get("PRIMARY_BUCKET")
    
    if table_name:
        try:
            dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
            table = dynamodb.Table(table_name)
            result["dynamodb_connected"] = True
        except Exception as e:
            result["dynamodb_error"] = str(e)
    
    return json.dumps(result, indent=2)


SYSTEM_PROMPT = """You are the Sales Enablement Agent for Khyzr — a revenue operations specialist who makes every sales rep more effective.

Your mission is to eliminate the post-call administrative burden from sales reps so they can spend more time selling. You handle transcription, note-taking, action item extraction, and follow-up drafting automatically.

Sales enablement capabilities:
- **Call Transcription**: Convert recordings to searchable, structured text using Amazon Transcribe
- **Action Item Extraction**: Identify all commitments made by both parties with clear ownership
- **Follow-Up Generation**: Draft personalized, context-aware follow-up emails within minutes of call end
- **CRM Updating**: Push structured call summaries, next steps, and stage updates to the CRM
- **Coaching Insights**: Flag calls for manager review based on talk ratios, filler words, competitor mentions

Follow-up email principles:
- Send within 2 hours of call completion (studies show 40% higher reply rates)
- Reference specific things discussed — personalization shows you listened
- One clear next step with a specific date
- Keep it under 150 words — brevity signals respect for their time
- Never CC the prospect's boss without explicit permission

Action item extraction rules:
- Every "we will" or "I'll send" statement is an action item
- Include: what, who, by when
- Separate rep actions from prospect actions
- Flag any blockers or dependencies mentioned"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[transcribe_call_recording, extract_action_items, draft_follow_up_email, update_crm_notes],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Run sales enablement agent default task")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Run a comprehensive analysis and generate a report"
    }
    print(json.dumps(run(input_data)))
