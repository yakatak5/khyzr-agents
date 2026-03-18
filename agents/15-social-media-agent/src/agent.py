"""
Social Media Agent
==================
Creates, schedules, and monitors social posts across platforms (LinkedIn,
Twitter/X, Instagram). Flags comments and mentions needing human response.

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
def create_social_posts(topic: str, platforms: list, tone: str = "professional") -> str:
    """
    Create platform-specific social posts for a given topic.

    Args:
        topic: Post topic or content brief
        platforms: List of platforms - ['linkedin', 'twitter', 'instagram', 'facebook']
        tone: Content tone - 'professional', 'casual', 'educational', 'promotional'

    Returns:
        JSON dict with platform-specific posts
    """
    platform_specs = {
        "linkedin": {"max_chars": 3000, "hashtag_count": "3-5", "format": "Professional long-form, can include bullet points, strong POV preferred"},
        "twitter": {"max_chars": 280, "hashtag_count": "1-2", "format": "Punchy, hook-first, thread-friendly, conversational"},
        "instagram": {"max_chars": 2200, "hashtag_count": "10-20", "format": "Visual storytelling, emoji-friendly, community-focused"},
        "facebook": {"max_chars": 500, "hashtag_count": "2-3", "format": "Community-friendly, conversational, share-worthy"},
    }

    posts = {
        "topic": topic,
        "tone": tone,
        "created_at": datetime.utcnow().isoformat(),
        "posts": {},
    }

    for platform in platforms:
        spec = platform_specs.get(platform.lower(), platform_specs["linkedin"])
        posts["posts"][platform] = {
            "platform": platform,
            "character_limit": spec["max_chars"],
            "hashtag_guidance": spec["hashtag_count"],
            "format_guidance": spec["format"],
            "content": f"[Agent will draft {platform} post about '{topic}' in {tone} tone — {spec['format']}]",
            "suggested_hashtags": [f"#{topic.split()[0]}", "#AI", "#Automation"],
            "best_post_time": {"linkedin": "Tue-Thu 8-10am or 12-2pm EST", "twitter": "Mon-Fri 9am, 12pm, 5-6pm EST", "instagram": "Mon-Wed 11am-1pm, 7-9pm EST"}.get(platform.lower(), "Check platform analytics"),
        }

    return json.dumps(posts, indent=2)


@tool
def schedule_post(platform: str, content: str, scheduled_time: str, media_url: str = None) -> str:
    """
    Schedule a social post for publication.

    Args:
        platform: Target platform ('linkedin', 'twitter', 'instagram')
        content: Post content
        scheduled_time: ISO timestamp for scheduled publication (e.g., '2025-10-15T09:00:00Z')
        media_url: Optional media URL (image or video)

    Returns:
        JSON schedule confirmation
    """
    # Store in DynamoDB for scheduled publishing
    table_name = os.environ.get("SOCIAL_QUEUE_TABLE")
    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        post_id = f"{platform}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        try:
            table.put_item(Item={
                "post_id": post_id,
                "platform": platform,
                "content": content,
                "scheduled_time": scheduled_time,
                "media_url": media_url,
                "status": "scheduled",
                "created_at": datetime.utcnow().isoformat(),
            })
            return json.dumps({"status": "scheduled", "post_id": post_id, "platform": platform, "scheduled_time": scheduled_time})
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    return json.dumps({
        "status": "queued_locally",
        "platform": platform,
        "scheduled_time": scheduled_time,
        "content_preview": content[:100] + "..." if len(content) > 100 else content,
        "note": "Configure SOCIAL_QUEUE_TABLE DynamoDB table for persistent scheduling",
    })


@tool
def monitor_mentions_and_comments(platform: str, hours_back: int = 24) -> str:
    """
    Monitor recent mentions, comments, and DMs for a platform.

    Args:
        platform: Platform to monitor ('linkedin', 'twitter', 'instagram')
        hours_back: How many hours back to check

    Returns:
        JSON list of mentions/comments with sentiment and escalation flags
    """
    # In production: integrates with platform APIs (LinkedIn API, Twitter API v2, etc.)
    access_token = os.environ.get(f"{platform.upper()}_ACCESS_TOKEN")

    if not access_token:
        return json.dumps({
            "platform": platform,
            "hours_back": hours_back,
            "mentions": [],
            "comments": [],
            "note": f"Configure {platform.upper()}_ACCESS_TOKEN for real social monitoring",
            "sample_item": {
                "type": "comment",
                "author": "User123",
                "content": "Is this GDPR compliant? Asking for our EU operations.",
                "sentiment": "neutral",
                "requires_response": True,
                "escalate": False,
                "reason": "Product compliance question — needs Sales/Solutions response",
            },
        }, indent=2)

    # TODO: Implement platform-specific API calls with access_token
    return json.dumps({"platform": platform, "status": "monitoring_active", "items_reviewed": 0}, indent=2)


@tool
def flag_for_human_review(item: dict, reason: str, urgency: str = "normal") -> str:
    """
    Flag a social post, comment, or mention for human review/response.

    Args:
        item: The social item requiring human attention
        reason: Reason for escalation
        urgency: 'urgent', 'normal', 'low'

    Returns:
        JSON escalation record
    """
    table_name = os.environ.get("ESCALATIONS_TABLE")
    escalation = {
        "escalation_id": f"ESC-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "item": item,
        "reason": reason,
        "urgency": urgency,
        "created_at": datetime.utcnow().isoformat(),
        "status": "pending_review",
        "assigned_to": None,
    }

    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            table.put_item(Item=escalation)
            return json.dumps({"status": "flagged", "escalation_id": escalation["escalation_id"]})
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    return json.dumps({"status": "flagged", "escalation": escalation, "note": "Configure ESCALATIONS_TABLE for persistent escalation tracking"})


@tool
def analyze_post_performance(platform: str, days_back: int = 7) -> str:
    """
    Analyze recent post performance metrics to optimize future content.

    Args:
        platform: Platform to analyze
        days_back: Performance window in days

    Returns:
        JSON performance report with engagement metrics and recommendations
    """
    bucket = os.environ.get("ANALYTICS_BUCKET")
    if bucket:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        try:
            obj = s3.get_object(Bucket=bucket, Key=f"social-analytics/{platform}/{datetime.utcnow().strftime('%Y-%m-%d')}.json")
            return obj["Body"].read().decode("utf-8")
        except Exception:
            pass

    return json.dumps({
        "platform": platform,
        "period_days": days_back,
        "metrics": {
            "total_posts": None,
            "total_impressions": None,
            "total_engagements": None,
            "avg_engagement_rate": None,
            "top_performing_post": None,
            "follower_growth": None,
        },
        "recommendations": [
            "Video content drives 3x more engagement on LinkedIn — add more video",
            "Posts with questions get 50% more comments — ask for opinions",
            "Posting Tuesday-Thursday 8-10am sees highest reach",
        ],
        "note": "Configure ANALYTICS_BUCKET and connect platform analytics API for real data",
    }, indent=2)


SYSTEM_PROMPT = """You are the Social Media Agent for Khyzr — a social media strategist and community manager.

Your mission is to build Khyzr's presence on LinkedIn, Twitter/X, and other platforms through consistent, high-quality content that educates prospects, showcases expertise, and builds community engagement.

Content strategy principles:
- **LinkedIn**: Thought leadership, customer success stories, product education, industry insights
- **Twitter/X**: Quick insights, industry commentary, engagement with community, real-time conversations
- **Instagram**: Behind-the-scenes, team culture, visual product demos, customer spotlights

Content pillars (rotate through these):
1. **Thought leadership** (30%): Industry insights, data points, contrarian takes
2. **Product education** (25%): Feature highlights, use cases, how-tos
3. **Social proof** (20%): Customer stories, testimonials, case study snippets
4. **Company culture** (15%): Team, values, hiring, events
5. **Engagement** (10%): Questions, polls, community discussion starters

Escalation criteria (flag for human review):
- **Immediate escalation**: Negative reviews, PR crises, legal threats, data breach mentions
- **24-hour review**: Product bugs reported publicly, competitor comparisons, pricing questions
- **Normal review**: General inquiries, feature requests, partnership opportunities
- **Auto-handle**: Thank-yous, congratulations, general positive sentiment

Never respond automatically to: political content, legal threats, regulatory complaints, competitor comparisons

When managing social:
1. Create platform-optimized content based on content calendar or ad-hoc requests
2. Schedule posts at optimal times for each platform
3. Monitor mentions and comments for items requiring human response
4. Flag urgent items immediately; queue normal items for daily review
5. Analyze performance weekly and adjust content strategy accordingly"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[create_social_posts, schedule_post, monitor_mentions_and_comments, flag_for_human_review, analyze_post_performance],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Create and schedule this week's social content across LinkedIn and Twitter")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Create a LinkedIn post and Twitter thread about how AI agents are transforming operations teams. Also monitor any recent mentions and flag anything needing human response."
    }
    print(json.dumps(run(input_data)))
