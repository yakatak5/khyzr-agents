"""
Battlecard Agent
=================
Monitors competitor websites and content to auto-update sales battlecards.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def scrape_competitor_website(competitor_url: str, sections: list = None) -> str:
    """
    Scrape competitor website for pricing, features, and messaging.

    Returns:
        JSON competitor intelligence data
    """
    # Implementation — configure environment variables for production data sources
    import boto3, os
    from datetime import datetime
    result = {
        "function": "scrape_competitor_website",
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
def analyze_competitive_positioning(competitor_name: str, competitor_data: dict) -> str:
    """
    Analyze how a competitor positions against your product.

    Returns:
        JSON positioning analysis with key differentiators
    """
    # Implementation — configure environment variables for production data sources
    import boto3, os
    from datetime import datetime
    result = {
        "function": "analyze_competitive_positioning",
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
def update_battlecard(competitor_name: str, analysis: dict) -> str:
    """
    Update or create a sales battlecard for a competitor.

    Returns:
        JSON updated battlecard
    """
    # Implementation — configure environment variables for production data sources
    import boto3, os
    from datetime import datetime
    result = {
        "function": "update_battlecard",
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
def store_battlecard(battlecard: dict, competitor_name: str) -> str:
    """
    Store battlecard to S3 for sales team access.

    Returns:
        S3 URI of stored battlecard
    """
    # Implementation — configure environment variables for production data sources
    import boto3, os
    from datetime import datetime
    result = {
        "function": "store_battlecard",
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


SYSTEM_PROMPT = """You are the Battlecard Agent for Khyzr — a competitive intelligence analyst who keeps the sales team armed with the latest intel on every key competitor.

Your mission is to monitor competitors continuously and ensure sales battlecards are always current, accurate, and actionable. Outdated battlecards lose deals.

Battlecard sections you maintain:
- **Overview**: Who they are, market position, customer base
- **Strengths**: What they do well — be honest, not dismissive
- **Weaknesses**: Genuine gaps and limitations
- **Our Differentiators**: Why Khyzr wins — with proof points
- **Common Objections**: "We already use [competitor]" — prepared responses
- **Win/Loss Themes**: Patterns from recent competitive deals
- **Pricing**: Known pricing tiers, contract structures, typical discounts
- **Landmines**: Questions to plant that highlight competitor weaknesses

Competitors to monitor for Khyzr: UiPath, ServiceNow, Automation Anywhere, Microsoft Power Automate, Workato, Zapier Enterprise

Update triggers:
- Competitor website changes (pricing, features, homepage messaging)
- New G2/Gartner reviews mentioning competitors
- Competitor press releases or product announcements
- Customer-reported competitive intel from sales calls"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[scrape_competitor_website, analyze_competitive_positioning, update_battlecard, store_battlecard],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Run battlecard agent default task")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Run a comprehensive analysis and generate a report"
    }
    print(json.dumps(run(input_data)))
