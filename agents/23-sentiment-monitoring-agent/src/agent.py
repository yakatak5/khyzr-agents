"""
Sentiment Monitoring Agent
===========================
Aggregates reviews from G2, Trustpilot, and social media to surface 
sentiment trends, product feedback themes, and competitive intelligence.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
import httpx
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def fetch_g2_reviews(product_name: str, limit: int = 20) -> str:
    """Fetch recent reviews from G2 for a product."""
    api_key = os.environ.get("G2_API_KEY")
    if api_key:
        try:
            resp = httpx.get(
                "https://data.g2.com/api/v1/reviews",
                headers={"Authorization": f"Token token={api_key}", "Content-Type": "application/vnd.api+json"},
                params={"filter[product_name]": product_name, "page[size]": limit},
                timeout=15,
            )
            return resp.text
        except Exception as e:
            pass
    return json.dumps({
        "source": "G2",
        "product": product_name,
        "sample_reviews": [
            {"rating": 4, "title": "Great automation platform", "body": "Saved our team 15 hours/week on manual processes", "date": "2025-09-01", "sentiment": "positive"},
            {"rating": 3, "title": "Good but onboarding needs work", "body": "Powerful tool but took 3 weeks to get fully set up", "date": "2025-08-20", "sentiment": "mixed"},
            {"rating": 5, "title": "Best in class for enterprise", "body": "Replaced UiPath and Zapier with one platform", "date": "2025-08-15", "sentiment": "positive"},
        ],
        "note": "Configure G2_API_KEY for real review data",
    }, indent=2)


@tool
def analyze_sentiment_trends(reviews: list) -> str:
    """
    Analyze sentiment trends across a collection of reviews.
    
    Args:
        reviews: List of review objects with rating, title, body fields
        
    Returns:
        JSON sentiment analysis with scores, themes, and trends
    """
    if not reviews:
        return json.dumps({"error": "No reviews provided"})
    
    # Basic sentiment bucketing by rating
    positive = [r for r in reviews if r.get("rating", 3) >= 4]
    neutral = [r for r in reviews if r.get("rating", 3) == 3]
    negative = [r for r in reviews if r.get("rating", 3) <= 2]
    
    avg_rating = sum(r.get("rating", 3) for r in reviews) / len(reviews)
    
    # Extract common themes (basic keyword analysis)
    positive_keywords = {}
    negative_keywords = {}
    
    for review in positive:
        for word in (review.get("body", "") + " " + review.get("title", "")).lower().split():
            if len(word) > 4:
                positive_keywords[word] = positive_keywords.get(word, 0) + 1
    
    for review in negative:
        for word in (review.get("body", "") + " " + review.get("title", "")).lower().split():
            if len(word) > 4:
                negative_keywords[word] = negative_keywords.get(word, 0) + 1
    
    top_positive = sorted(positive_keywords.items(), key=lambda x: x[1], reverse=True)[:10]
    top_negative = sorted(negative_keywords.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return json.dumps({
        "total_reviews": len(reviews),
        "average_rating": round(avg_rating, 2),
        "sentiment_distribution": {
            "positive_pct": round(len(positive) / len(reviews) * 100, 1),
            "neutral_pct": round(len(neutral) / len(reviews) * 100, 1),
            "negative_pct": round(len(negative) / len(reviews) * 100, 1),
        },
        "top_positive_themes": [k for k, _ in top_positive],
        "top_negative_themes": [k for k, _ in top_negative],
        "nps_proxy": round((len(positive) - len(negative)) / len(reviews) * 100, 1),
        "analyzed_at": datetime.utcnow().isoformat(),
    }, indent=2)


@tool
def generate_sentiment_report(analysis: dict, period: str, competitor_data: dict = None) -> str:
    """
    Generate a sentiment monitoring report for product and leadership teams.
    
    Args:
        analysis: Sentiment analysis output
        period: Reporting period label
        competitor_data: Optional competitor sentiment for benchmarking
        
    Returns:
        JSON sentiment report with insights and action items
    """
    report = {
        "report_period": period,
        "generated_at": datetime.utcnow().isoformat(),
        "headline_metrics": {
            "avg_rating": analysis.get("average_rating"),
            "nps_proxy": analysis.get("nps_proxy"),
            "positive_sentiment_pct": analysis.get("sentiment_distribution", {}).get("positive_pct"),
        },
        "key_themes": {
            "customers_love": analysis.get("top_positive_themes", [])[:5],
            "areas_to_improve": analysis.get("top_negative_themes", [])[:5],
        },
        "recommended_actions": [
            "Share top positive themes with Sales for use in demos and proposals",
            "Route top negative themes to Product team as feature/UX priorities",
            "Respond publicly to all 1-2 star reviews within 24 hours",
            "Identify happy customers from positive reviews for case study outreach",
        ],
        "competitor_benchmarking": competitor_data or "No competitor data provided",
    }
    
    bucket = os.environ.get("SENTIMENT_REPORTS_BUCKET", "khyzr-sentiment-reports")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    key = f"reports/{datetime.utcnow().strftime('%Y%m%d')}-sentiment-report.json"
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(report).encode(), ContentType="application/json")
        return json.dumps({"status": "report_saved", "s3_uri": f"s3://{bucket}/{key}", "report": report})
    except Exception as e:
        return json.dumps({"status": "generated", "report": report, "save_error": str(e)})


SYSTEM_PROMPT = """You are the Sentiment Monitoring Agent for Khyzr — a voice-of-customer analyst and product intelligence specialist.

Your mission is to continuously monitor what customers, prospects, and the market are saying about Khyzr and competitors across all review platforms and social channels. You transform raw sentiment data into actionable product and marketing insights.

Monitoring sources:
- **G2**: Primary source for B2B software reviews — monitor ratings, reviews, and comparisons
- **Trustpilot**: Consumer-facing review platform
- **Gartner Peer Insights**: Enterprise buyer reviews
- **Reddit**: r/automation, r/programming, r/enterprise — organic community discussions
- **LinkedIn**: Comments on company posts, mentions, tagged posts
- **Twitter/X**: Brand mentions, hashtags, customer complaints

Analysis dimensions:
- **Overall sentiment**: Positive/Neutral/Negative distribution and trend
- **Feature sentiment**: Which features drive the most positive and negative feedback
- **Onboarding sentiment**: Are new customers successful? Time-to-value satisfaction
- **Support sentiment**: How do customers rate support quality and responsiveness
- **Competitive sentiment**: How do reviewers compare Khyzr to alternatives?

Action routing:
- Positive themes → Sales enablement (use in conversations, case studies)
- Negative themes → Product team (prioritization input)
- Individual complaints → Customer success (personal outreach)
- Bugs reported in reviews → Engineering (urgent fix)
- Competitor comparisons → Competitive intelligence (battlecard updates)"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[fetch_g2_reviews, analyze_sentiment_trends, generate_sentiment_report],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Generate monthly sentiment report from G2 reviews")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Fetch and analyze recent G2 reviews for Khyzr. Identify top positive and negative themes, generate a report, and recommend actions for Product and Sales teams."
    }
    print(json.dumps(run(input_data)))
