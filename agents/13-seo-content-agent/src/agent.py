"""
SEO Content Agent
=================
Researches keywords, drafts SEO-optimized blog posts, and manages content
publishing on a cadence to improve organic search rankings.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
import httpx
from datetime import datetime
from bs4 import BeautifulSoup
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def research_keywords(seed_keyword: str, industry: str = None) -> str:
    """
    Research keyword opportunities for a given topic.

    Args:
        seed_keyword: Primary keyword or topic to research
        industry: Industry context for relevance filtering

    Returns:
        JSON keyword research results with search volume estimates and difficulty
    """
    # In production: integrates with SEMrush, Ahrefs, or Google Keyword Planner API
    api_key = os.environ.get("SEMRUSH_API_KEY")
    if api_key:
        try:
            resp = httpx.get(
                "https://api.semrush.com/",
                params={"type": "phrase_related", "key": api_key, "phrase": seed_keyword, "database": "us", "export_columns": "Ph,Nq,Cp,Co,Nr", "display_limit": 20},
                timeout=15,
            )
            lines = resp.text.strip().split("\n")[1:]  # Skip header
            keywords = []
            for line in lines:
                parts = line.split(";")
                if len(parts) >= 4:
                    keywords.append({"keyword": parts[0], "monthly_volume": parts[1], "cpc": parts[2], "competition": parts[3]})
            return json.dumps({"seed_keyword": seed_keyword, "results": keywords}, indent=2)
        except Exception as e:
            pass

    # Simulated keyword data when no API key
    keywords = [
        {"keyword": seed_keyword, "monthly_volume": "1000-10000", "difficulty": 45, "intent": "informational", "priority": "high"},
        {"keyword": f"best {seed_keyword}", "monthly_volume": "500-5000", "difficulty": 38, "intent": "commercial", "priority": "high"},
        {"keyword": f"how to {seed_keyword}", "monthly_volume": "200-2000", "difficulty": 25, "intent": "informational", "priority": "medium"},
        {"keyword": f"{seed_keyword} software", "monthly_volume": "100-1000", "difficulty": 55, "intent": "commercial", "priority": "medium"},
        {"keyword": f"{seed_keyword} for enterprise", "monthly_volume": "50-500", "difficulty": 30, "intent": "commercial", "priority": "high", "note": "Long-tail, high conversion"},
    ]
    return json.dumps({"seed_keyword": seed_keyword, "industry": industry, "keywords": keywords, "note": "Configure SEMRUSH_API_KEY for real keyword data"}, indent=2)


@tool
def analyze_competitor_content(url: str) -> str:
    """
    Analyze a competitor's top-ranking content for SEO insights.

    Args:
        url: URL of competitor content to analyze

    Returns:
        JSON analysis with title, word count, headings structure, keywords found
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SEOAgent/1.0)"}
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")

        title = soup.find("title")
        meta_desc = soup.find("meta", attrs={"name": "description"})
        h1s = [h.get_text(strip=True) for h in soup.find_all("h1")]
        h2s = [h.get_text(strip=True) for h in soup.find_all("h2")]
        h3s = [h.get_text(strip=True) for h in soup.find_all("h3")]
        body_text = soup.get_text(separator=" ", strip=True)
        word_count = len(body_text.split())

        return json.dumps({
            "url": url,
            "title": title.get_text() if title else None,
            "meta_description": meta_desc.get("content") if meta_desc else None,
            "h1_tags": h1s,
            "h2_tags": h2s[:10],
            "h3_tags": h3s[:15],
            "word_count": word_count,
            "estimated_read_time_min": round(word_count / 200, 1),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "url": url})


@tool
def create_content_brief(primary_keyword: str, target_word_count: int = 1500, audience: str = "enterprise") -> str:
    """
    Create a detailed content brief for a blog post or article.

    Args:
        primary_keyword: Main keyword to target
        target_word_count: Desired article length
        audience: Target audience description

    Returns:
        JSON content brief with structure, angle, and SEO guidelines
    """
    brief = {
        "primary_keyword": primary_keyword,
        "target_audience": audience,
        "target_word_count": target_word_count,
        "content_type": "blog_post",
        "created_at": datetime.utcnow().isoformat(),
        "seo_requirements": {
            "title_tag": f"Include '{primary_keyword}' near the beginning, max 60 characters",
            "meta_description": f"Include '{primary_keyword}', action-oriented, 150-160 characters",
            "url_slug": primary_keyword.lower().replace(" ", "-"),
            "primary_keyword_density": "1-2% natural usage",
            "lsi_keywords": f"Include semantic variations of '{primary_keyword}'",
        },
        "content_structure": {
            "intro": "Hook paragraph that addresses reader pain point + previews the solution (150-200 words)",
            "sections": [
                f"What is {primary_keyword}? (definition section)",
                f"Why {primary_keyword} matters for {audience}",
                f"Key benefits of {primary_keyword}",
                f"How to implement {primary_keyword}: step-by-step",
                f"Common mistakes with {primary_keyword}",
                f"Case study or example",
                "Conclusion + CTA",
            ],
            "cta": "Include at least one clear call-to-action (demo request, free trial, or download)",
        },
        "internal_linking": f"Link to 3-5 related articles. Anchor text should include '{primary_keyword}' variations.",
        "external_links": "Cite 2-3 authoritative sources. Use nofollow for competitor links.",
    }
    return json.dumps(brief, indent=2)


@tool
def publish_content(title: str, content: str, slug: str, metadata: dict = None) -> str:
    """
    Publish content to the configured CMS or S3 staging bucket.

    Args:
        title: Article title
        content: Full article content in markdown
        slug: URL slug for the article
        metadata: Additional metadata dict (tags, category, author, etc.)

    Returns:
        JSON publish status with content URL
    """
    bucket = os.environ.get("CONTENT_BUCKET", "khyzr-blog-content")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    timestamp = datetime.utcnow().strftime("%Y%m%d")

    frontmatter = f"""---
title: "{title}"
slug: "{slug}"
date: "{timestamp}"
author: "{metadata.get('author', 'Khyzr Content Team') if metadata else 'Khyzr Content Team'}"
tags: {json.dumps(metadata.get('tags', []) if metadata else [])}
category: "{metadata.get('category', 'Blog') if metadata else 'Blog'}"
status: "draft"
---

"""
    full_content = frontmatter + content
    key = f"posts/draft/{timestamp}-{slug}.md"

    try:
        s3.put_object(Bucket=bucket, Key=key, Body=full_content.encode("utf-8"), ContentType="text/markdown")
        return json.dumps({"status": "published_to_staging", "s3_uri": f"s3://{bucket}/{key}", "slug": slug, "requires_human_review": True})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e), "content_length": len(content)})


SYSTEM_PROMPT = """You are the SEO Content Agent for Khyzr — a senior content strategist and SEO specialist.

Your mission is to research high-value keyword opportunities and produce SEO-optimized content that ranks on Google and drives qualified organic traffic to the business.

SEO expertise you apply:
- **Keyword Research**: Identify primary, secondary, and long-tail keywords with favorable difficulty/volume ratios
- **Search Intent**: Match content to user intent (informational, navigational, commercial, transactional)
- **Content Structure**: Proper use of H1/H2/H3 hierarchy, featured snippet optimization, schema markup guidance
- **On-Page SEO**: Title tags, meta descriptions, URL structure, internal linking, image alt text
- **Competitor Analysis**: Identify what's ranking, why, and how to create something 10x better
- **E-E-A-T**: Expertise, Experience, Authority, Trust signals in content

Content production workflow:
1. Keyword research: Find opportunities with volume ≥ 500/month and difficulty ≤ 60
2. Competitor analysis: Review top 3-5 ranking pages for the target keyword
3. Content brief: Create detailed outline with structure, angle, and SEO requirements
4. Content draft: Write complete, publication-ready article (1500-3000 words)
5. Publish to staging: Push to S3/CMS for human review before going live

Content principles:
- Every article must solve a specific problem for a specific audience
- Lead with the answer (Google rewards content that directly answers queries)
- Use data, examples, and specifics — vague content ranks poorly
- Include a compelling CTA aligned to where the reader is in the buying journey
- Always write for humans first, search engines second

Target keyword universe for Khyzr: AI automation, workflow automation, enterprise AI, process automation, AI agents, business automation software"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[research_keywords, analyze_competitor_content, create_content_brief, publish_content],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Research keywords and draft a blog post on AI automation for enterprise")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Research keywords around 'AI workflow automation' and create a content brief for a 2000-word blog post targeting enterprise IT buyers. Then draft the full article."
    }
    print(json.dumps(run(input_data)))
