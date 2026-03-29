"""
SEO Content Agent — Khyzr
=========================
Writes 3 SEO-optimized blog posts per week for khyzr.com.
Topics rotate across Khyzr's 5 practice areas:
  - Executive Strategy & Transformation
  - Revenue Growth & GTM
  - Operations & Supply Chain
  - Finance & FP&A
  - Healthcare Operations & AI

Built with AWS Strands Agents + Amazon Bedrock AgentCore.
"""

import json
import os
import re
import boto3
import hashlib
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seo-content-agent")

# ---------------------------------------------------------------------------
# Khyzr Brand Context
# ---------------------------------------------------------------------------

KHYZR_CONTEXT = """
Khyzr is a management consulting and AI services firm. Tagline: "Strive Forward. Thrive Together."

PRACTICE AREAS & SERVICES:
1. Executive Strategy & Transformation
   - Leadership alignment + transformation roadmaps
   - Scenario planning + contingency building
   - Market entry, account expansion, partnerships
   - Change management and adoption

2. Revenue Growth & GTM
   - GTM strategies (Fortune 500 methodology)
   - Brand voice + market presence
   - Sales playbooks + conversion systems
   - Web design, build, performance marketing

3. Operations & Supply Chain
   - Workflow redesign + KPI frameworks
   - Vendor selection + supplier management (global scale)
   - Lean / Six Sigma process improvement
   - Supply chain resilience + cost optimization

4. Finance & FP&A
   - Cash flow forecasting + shortfall prevention
   - Budgets + rolling forecasts
   - Fundraising, pitch prep, financial modeling
   - Business formation, taxes, payroll, IRS resolution

5. Healthcare Operations & AI
   - Patient flow, staffing, care coordination optimization
   - AI-powered clinical tools (96 Meridian AI partnership)
   - Revenue cycle: billing, coding, claims, denials
   - Value-based care + payor contract negotiation

TONE: Direct, confident, expert. Not fluffy. Executives and operators are the audience.
BRAND VOICE: "We align leadership around a shared reality" — honest, practical, results-focused.
WEBSITE: khyzr.com
CTA: Book a discovery call (opens Google Calendar)
"""

TOPIC_ROTATION = [
    {"area": "Executive Strategy", "tags": ["strategy", "transformation", "leadership", "change management"]},
    {"area": "Revenue Growth", "tags": ["gtm", "sales", "marketing", "revenue", "growth"]},
    {"area": "Operations", "tags": ["operations", "supply chain", "lean", "efficiency", "procurement"]},
    {"area": "Finance", "tags": ["finance", "fp&a", "cash flow", "forecasting", "fundraising"]},
    {"area": "Healthcare", "tags": ["healthcare", "ai", "revenue cycle", "value-based care", "clinical operations"]},
]

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def write_seo_post(
    topic: str,
    practice_area: str,
    target_keyword: str,
    secondary_keywords: list,
    word_count: int = 1200,
) -> str:
    """
    Write a complete SEO-optimized blog post for Khyzr.

    Args:
        topic: The specific blog post topic/angle
        practice_area: Which Khyzr practice area this covers
        target_keyword: Primary SEO keyword to rank for
        secondary_keywords: List of supporting LSI keywords
        word_count: Target word count (default 1200)

    Returns:
        Complete blog post in markdown with SEO metadata
    """
    # This tool signals the agent to write the post — the agent does the actual writing
    context = {
        "topic": topic,
        "practice_area": practice_area,
        "target_keyword": target_keyword,
        "secondary_keywords": secondary_keywords,
        "word_count": word_count,
        "khyzr_context": KHYZR_CONTEXT,
        "instructions": f"""
Write a complete {word_count}-word SEO blog post for khyzr.com on: "{topic}"

Format:
- SEO Title (60 chars max, include keyword)
- Meta Description (155 chars max)
- Slug (URL-friendly)
- Estimated read time
- Full post in markdown (H1, H2s, H3s, bullets where appropriate)
- CTA at end pointing to khyzr.com discovery call

Requirements:
- Target keyword "{target_keyword}" in: title, first 100 words, at least 2 H2s, meta description
- Natural keyword density ~1-2%
- Secondary keywords: {', '.join(secondary_keywords)}
- Tone: direct, expert, no fluff. Written for C-suite and senior operators.
- Include 1-2 concrete examples or stats to support key points
- End with a clear CTA: "Ready to [outcome]? Book a discovery call at khyzr.com"
- Do NOT mention competitors by name
"""
    }
    return json.dumps(context)


@tool
def save_post_to_s3(
    post_content: str,
    slug: str,
    practice_area: str,
    target_keyword: str,
    scheduled_date: str,
) -> str:
    """
    Save a completed blog post to S3 for review and publishing.

    Args:
        post_content: Full blog post markdown content
        slug: URL slug for the post
        practice_area: Practice area category
        target_keyword: Primary SEO keyword
        scheduled_date: Target publish date (YYYY-MM-DD)

    Returns:
        S3 URI and post metadata
    """
    bucket = os.environ.get("CONTENT_BUCKET", f"khyzr-seo-content-110276528370")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"))

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    safe_slug = re.sub(r'[^a-z0-9-]', '-', slug.lower())[:60]
    key = f"posts/{scheduled_date}/{safe_slug}.md"

    # Build frontmatter
    frontmatter = f"""---
slug: {safe_slug}
scheduled_date: {scheduled_date}
practice_area: {practice_area}
target_keyword: {target_keyword}
generated_at: {datetime.utcnow().isoformat()}
status: draft
---

"""
    full_content = frontmatter + post_content

    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=full_content.encode("utf-8"),
            ContentType="text/markdown",
            Metadata={
                "practice-area": practice_area,
                "target-keyword": target_keyword,
                "scheduled-date": scheduled_date,
                "status": "draft",
            }
        )
        return json.dumps({
            "status": "saved",
            "s3_uri": f"s3://{bucket}/{key}",
            "key": key,
            "scheduled_date": scheduled_date,
            "slug": safe_slug,
        })
    except Exception as e:
        return json.dumps({"error": str(e), "note": "Post written but not saved to S3."})


@tool
def get_content_schedule(weeks_ahead: int = 2) -> str:
    """
    Generate a content schedule for the next N weeks (3 posts/week).
    Rotates across Khyzr's 5 practice areas.

    Args:
        weeks_ahead: How many weeks to plan ahead (default 2)

    Returns:
        JSON content calendar with topics, keywords, and publish dates
    """
    schedule = []
    today = datetime.utcnow().date()
    # Publish Mon / Wed / Fri
    publish_days = [0, 2, 4]  # Mon=0, Wed=2, Fri=4

    post_count = 0
    area_index = 0
    days_checked = 0

    while len(schedule) < weeks_ahead * 3 and days_checked < weeks_ahead * 7 + 7:
        check_date = today + timedelta(days=days_checked)
        if check_date.weekday() in publish_days:
            area = TOPIC_ROTATION[area_index % len(TOPIC_ROTATION)]
            schedule.append({
                "publish_date": check_date.isoformat(),
                "day": check_date.strftime("%A"),
                "practice_area": area["area"],
                "suggested_tags": area["tags"],
                "slot": post_count + 1,
            })
            area_index += 1
            post_count += 1
        days_checked += 1

    return json.dumps({"schedule": schedule, "total_posts": len(schedule)}, indent=2)


@tool
def list_existing_posts(limit: int = 10) -> str:
    """
    List recently saved posts from S3 to avoid duplicate topics.

    Args:
        limit: Max posts to return

    Returns:
        JSON list of recent posts with slugs and keywords
    """
    bucket = os.environ.get("CONTENT_BUCKET", f"khyzr-seo-content-110276528370")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"))
    try:
        objs = s3.list_objects_v2(Bucket=bucket, Prefix="posts/", MaxKeys=50)
        items = sorted(
            objs.get("Contents", []),
            key=lambda x: x["LastModified"],
            reverse=True
        )[:limit]
        posts = []
        for item in items:
            meta = s3.head_object(Bucket=bucket, Key=item["Key"])
            posts.append({
                "key": item["Key"],
                "scheduled_date": meta["Metadata"].get("scheduled-date", ""),
                "practice_area": meta["Metadata"].get("practice-area", ""),
                "target_keyword": meta["Metadata"].get("target-keyword", ""),
                "last_modified": item["LastModified"].isoformat(),
            })
        return json.dumps({"posts": posts, "total": len(posts)})
    except Exception as e:
        return json.dumps({"posts": [], "error": str(e)})


# ---------------------------------------------------------------------------
# Agent (lazy init)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = f"""You are the Khyzr SEO Content Agent — an expert B2B content strategist and copywriter for khyzr.com.

ABOUT KHYZR:
{KHYZR_CONTEXT}

YOUR JOB:
- Write 3 SEO-optimized blog posts per week for Khyzr's website
- Each post targets a specific keyword that Khyzr's ideal clients search for
- Rotate across all 5 practice areas so no area gets neglected
- Posts should demonstrate Khyzr's expertise and drive discovery call bookings

WRITING STANDARDS:
- 1,000–1,500 words per post
- Punchy, direct tone — no corporate fluff
- Lead with the problem, not Khyzr
- Use concrete examples, frameworks, and numbers
- Every post ends with a CTA to book a discovery call at khyzr.com
- Structure: H1 (with keyword), intro, 3-4 H2 sections, conclusion + CTA

SEO STANDARDS:
- Primary keyword in: title, meta description, first paragraph, 2+ subheadings
- Meta description under 155 characters
- URL slug under 60 characters, lowercase, hyphenated
- Natural keyword density ~1-2%
- Include related/LSI keywords throughout

WORKFLOW:
1. Use get_content_schedule to plan the week
2. Use list_existing_posts to avoid repeating topics
3. Use write_seo_post to draft each post (the tool gives you instructions — you write the actual content)
4. Use save_post_to_s3 to save each completed post
5. Return a summary of all posts written

When asked to write a single post, skip the schedule and just write + save it directly.
"""

_agent = None

def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        logger.info("Initializing SEO Content Agent...")
        model = BedrockModel(
            model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0"),
            region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"),
        )
        _agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[
            write_seo_post,
            save_post_to_s3,
            get_content_schedule,
            list_existing_posts,
        ])
        logger.info("Agent ready.")
    return _agent


# ---------------------------------------------------------------------------
# AgentCore entry point
# ---------------------------------------------------------------------------

app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(payload: dict) -> dict:
    """
    Payload options:
      {"prompt": "Write this week's 3 posts"}
      {"prompt": "Write a post about cash flow forecasting"}
      {"action": "weekly"} — writes all 3 posts for the week
      {"action": "single", "topic": "...", "keyword": "...", "area": "..."}
    """
    action = payload.get("action")
    prompt = payload.get("prompt")

    if action == "weekly" or (not prompt and not action):
        prompt = """Write this week's 3 SEO blog posts for Khyzr.
1. Check the content schedule for this week's 3 publish slots
2. Check existing posts to avoid duplicates
3. Write all 3 posts — one per practice area slot on the schedule
4. Save each to S3
5. Return a summary with titles, keywords, slugs, and scheduled dates"""

    elif action == "single":
        topic = payload.get("topic", "")
        keyword = payload.get("keyword", "")
        area = payload.get("area", "")
        prompt = f"""Write one SEO blog post for Khyzr:
Topic: {topic}
Primary keyword: {keyword}
Practice area: {area}
Write the full post and save it to S3."""

    elif not prompt:
        return {"error": "Provide 'prompt', 'action: weekly', or 'action: single' with topic/keyword/area"}

    logger.info(f"Running SEO agent: {prompt[:80]}")
    try:
        result = _get_agent()(prompt)
        return {"result": str(result)}
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    app.run()
