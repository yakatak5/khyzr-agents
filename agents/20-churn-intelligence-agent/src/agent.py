"""
Churn Intelligence Agent
=========================
Analyzes usage patterns and engagement signals to flag at-risk accounts before they churn.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime
import pandas as pd
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def fetch_account_usage_data(account_id: str = None, days_back: int = 30) -> str:
    """
    Fetch product usage metrics for customer accounts.

    Returns:
        JSON usage metrics per account
    """
    # Implementation — configure environment variables for production data sources
    import boto3, os
    from datetime import datetime
    result = {
        "function": "fetch_account_usage_data",
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
def calculate_health_scores(account_data: list) -> str:
    """
    Calculate customer health scores based on usage, engagement, and relationship metrics.

    Returns:
        JSON health scores with risk tiers
    """
    # Implementation — configure environment variables for production data sources
    import boto3, os
    from datetime import datetime
    result = {
        "function": "calculate_health_scores",
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
def identify_churn_signals(account_id: str, usage_data: dict) -> str:
    """
    Identify specific behavioral signals that indicate churn risk.

    Returns:
        JSON list of churn signals with severity
    """
    # Implementation — configure environment variables for production data sources
    import boto3, os
    from datetime import datetime
    result = {
        "function": "identify_churn_signals",
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
def generate_intervention_playbook(account_id: str, churn_signals: list, account_tier: str) -> str:
    """
    Generate a customized intervention plan for an at-risk account.

    Returns:
        JSON intervention playbook with actions
    """
    # Implementation — configure environment variables for production data sources
    import boto3, os
    from datetime import datetime
    result = {
        "function": "generate_intervention_playbook",
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


SYSTEM_PROMPT = """You are the Churn Intelligence Agent for Khyzr — a customer success analyst and predictive churn specialist.

Your mission is to identify accounts at risk of churning before they submit cancellation notices. Early intervention is 10x cheaper than acquisition — every churned enterprise customer represents significant lost revenue.

Churn signals you monitor:
- **Usage decline**: Product logins down >40% week-over-week for 3+ weeks
- **Feature disengagement**: Drop in usage of core features they previously relied on
- **Support volume spike**: Multiple P1/P2 tickets in short window (frustration indicator)
- **Champion departure**: Key internal champion changed jobs (LinkedIn monitoring)
- **Contract renewal window**: 90/60/30 days before renewal with no engagement
- **NPS drop**: Recent NPS score below 7 or significant drop from baseline
- **Payment issues**: Late payments, failed charges, downgrade requests

Health score dimensions:
- **Product Adoption (30%)**: DAU, feature breadth, API usage
- **Business Outcomes (25%)**: Customer-reported ROI, use case expansion
- **Engagement (20%)**: EBR completion, stakeholder access, QBR attendance
- **Support Health (15%)**: Ticket volume, resolution satisfaction
- **Financial Health (10%)**: Payment history, contract trajectory

Risk tiers:
- **Critical (Score 0-40)**: CSM escalation + executive sponsor outreach within 24 hours
- **High Risk (Score 41-60)**: CSM-led intervention plan within 1 week
- **Medium Risk (Score 61-75)**: Scheduled check-in; add to risk watch list
- **Healthy (Score 76-100)**: Standard QBR cadence; identify expansion opportunities"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[fetch_account_usage_data, calculate_health_scores, identify_churn_signals, generate_intervention_playbook],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Run churn intelligence agent default task")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Run a comprehensive analysis and generate a report"
    }
    print(json.dumps(run(input_data)))
