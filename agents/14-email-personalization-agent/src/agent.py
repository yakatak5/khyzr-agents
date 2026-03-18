"""
Email Personalization Agent
============================
Generates hyper-personalized cold and nurture email sequences tailored to
ICP segments and buyer intent signals. Maximizes open rates, reply rates,
and downstream conversion for sales and marketing.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def fetch_prospect_context(email: str) -> str:
    """
    Fetch contextual data about a prospect to personalize outreach.

    Args:
        email: Prospect email address

    Returns:
        JSON prospect profile with firmographic, behavioral, and intent data
    """
    table_name = os.environ.get("PROSPECTS_TABLE_NAME")
    if table_name:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = dynamodb.Table(table_name)
        try:
            resp = table.get_item(Key={"email": email})
            if "Item" in resp:
                return json.dumps(resp["Item"], indent=2)
        except Exception as e:
            pass

    return json.dumps({
        "email": email,
        "first_name": None,
        "last_name": None,
        "title": None,
        "company": None,
        "company_size": None,
        "industry": None,
        "recent_trigger": None,
        "pain_points": [],
        "intent_signals": [],
        "note": "Configure PROSPECTS_TABLE_NAME for real prospect data",
    }, indent=2)


@tool
def generate_cold_email_sequence(prospect_profile: dict, sequence_type: str = "5_touch", campaign_goal: str = "book_demo") -> str:
    """
    Generate a multi-touch cold email sequence personalized to the prospect.

    Args:
        prospect_profile: Prospect data dict with firmographic and intent info
        sequence_type: '3_touch', '5_touch', or '7_touch'
        campaign_goal: 'book_demo', 'free_trial', 'whitepaper_download', 'event_invite'

    Returns:
        JSON email sequence with subject lines, body, and send timing
    """
    touch_counts = {"3_touch": 3, "5_touch": 5, "7_touch": 7}
    num_touches = touch_counts.get(sequence_type, 5)

    name = prospect_profile.get("first_name", "there")
    company = prospect_profile.get("company", "your company")
    title = prospect_profile.get("title", "")
    industry = prospect_profile.get("industry", "your industry")

    cta_map = {
        "book_demo": "book a 20-minute demo",
        "free_trial": "start a free trial",
        "whitepaper_download": "download our guide",
        "event_invite": "join us at [Event Name]",
    }
    cta = cta_map.get(campaign_goal, "connect")

    sequence = {
        "prospect_email": prospect_profile.get("email"),
        "sequence_type": sequence_type,
        "campaign_goal": campaign_goal,
        "personalization_tokens": {
            "first_name": name,
            "company": company,
            "title": title,
            "industry": industry,
        },
        "emails": [
            {
                "touch": 1,
                "send_day": 0,
                "subject": f"Quick question about {company}'s workflow automation",
                "body": f"""Hi {name},

I noticed {company} is [scaling rapidly / expanding into new markets / going through a transformation] — congratulations on [specific trigger if available].

I'm reaching out because companies like {company} in the {industry} space typically struggle with [pain point 1] and [pain point 2] as they scale.

Khyzr's AI automation platform helps {industry} companies like [similar company] reduce manual work by 70% and free their teams for higher-value work.

Worth a quick 20-minute conversation to see if there's a fit?

[Calendar link]

Best,
[Rep Name]""",
                "note": "Personalize [trigger] based on LinkedIn, news, or intent signal",
            },
            {
                "touch": 2,
                "send_day": 3,
                "subject": f"Re: Quick question about {company}'s workflow automation",
                "body": f"""Hi {name},

Just following up on my earlier note.

I wanted to share something concrete: [Customer Name], a {industry} company similar to {company}, reduced their [specific process] time from [X hours] to [Y minutes] after deploying Khyzr.

Here's their story: [case study link]

If that resonates, happy to show you how we'd approach {company}'s specific situation.

[Calendar link]

Best,
[Rep Name]""",
                "note": "Use the most relevant customer case study for their industry",
            },
            {
                "touch": 3,
                "send_day": 7,
                "subject": f"A resource for {company}",
                "body": f"""Hi {name},

Not sure if this landed in the chaos of your inbox, but I thought this might be useful regardless of whether we ever work together:

[Link to relevant guide/resource tailored to {industry}]

If you ever want to explore how Khyzr could help {company} specifically, I'm happy to {cta}.

No pressure either way.

Best,
[Rep Name]""",
                "note": "Value-first touch — provide genuine value regardless of conversion",
            },
        ],
    }

    if num_touches >= 5:
        sequence["emails"].extend([
            {
                "touch": 4,
                "send_day": 14,
                "subject": f"Is [specific problem] on your roadmap, {name}?",
                "body": f"""Hi {name},

Quick one — is [specific problem relevant to their industry/title] something your team is actively working on?

If so, I have a few ideas specific to how {company} could approach it. If not, I'll stop bugging you!

Either way, a quick yes/no would help me direct my energy.

Thanks,
[Rep Name]""",
                "note": "Pattern interrupt — yes/no question to re-engage",
            },
            {
                "touch": 5,
                "send_day": 21,
                "subject": f"Closing the loop, {name}",
                "body": f"""Hi {name},

I'll stop reaching out after this — I don't want to be the person who clogs your inbox.

But before I do, I wanted to leave this here: [compelling one-line value stat].

If the timing is ever right for {company} to explore AI automation, I'd love to reconnect. You can book time whenever works: [calendar link]

Thanks for your time,
[Rep Name]""",
                "note": "Breakup email — creates urgency and often generates replies",
            },
        ])

    return json.dumps(sequence, indent=2)


@tool
def generate_nurture_sequence(segment: str, lifecycle_stage: str, pain_point: str) -> str:
    """
    Generate a nurture email sequence for a given segment and lifecycle stage.

    Args:
        segment: ICP segment name (e.g., 'enterprise_fintech', 'mid_market_healthcare')
        lifecycle_stage: 'awareness', 'consideration', 'evaluation', 'post_trial'
        pain_point: Primary pain point being addressed

    Returns:
        JSON nurture sequence with 4-week email cadence
    """
    nurture = {
        "segment": segment,
        "lifecycle_stage": lifecycle_stage,
        "pain_point": pain_point,
        "sequence_length": "4 weeks",
        "send_frequency": "Weekly",
        "emails": [
            {
                "week": 1,
                "theme": "Education",
                "subject": f"How {segment.split('_')[0]} companies solve {pain_point}",
                "content_type": "educational_article",
                "cta": "Read the guide",
            },
            {
                "week": 2,
                "theme": "Social Proof",
                "subject": f"How [Customer Name] reduced {pain_point} by 60%",
                "content_type": "case_study",
                "cta": "Read the case study",
            },
            {
                "week": 3,
                "theme": "Product Education",
                "subject": f"See how Khyzr addresses {pain_point}",
                "content_type": "product_walkthrough_video",
                "cta": "Watch the 3-minute demo",
            },
            {
                "week": 4,
                "theme": "Conversion",
                "subject": f"Ready to see Khyzr in your environment?",
                "content_type": "personalized_cta",
                "cta": "Book a demo",
            },
        ],
    }
    return json.dumps(nurture, indent=2)


@tool
def send_email_via_ses(to_email: str, subject: str, body: str, from_email: str = None) -> str:
    """
    Send a single email via AWS SES.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        body: Email body (plain text or HTML)
        from_email: Sender email (falls back to SES_SENDER_EMAIL env var)

    Returns:
        JSON send status
    """
    sender = from_email or os.environ.get("SES_SENDER_EMAIL", "")
    if not sender:
        return json.dumps({"error": "No sender email configured. Set SES_SENDER_EMAIL or pass from_email."})

    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    try:
        resp = ses.send_email(
            Source=sender,
            Destination={"ToAddresses": [to_email]},
            Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}},
        )
        return json.dumps({"status": "sent", "message_id": resp["MessageId"], "to": to_email})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


SYSTEM_PROMPT = """You are the Email Personalization Agent for Khyzr — a world-class B2B copywriter and demand generation specialist.

Your mission is to craft email sequences that feel genuinely personal, deliver real value, and drive measurable pipeline results. You understand that the best sales emails don't feel like sales emails.

Personalization principles you apply:
- **Specificity beats generality**: Reference their company, role, recent news, or industry pain — not generic claims
- **Value before ask**: Give something useful before requesting their time
- **Short wins**: Emails under 150 words outperform long emails — cut ruthlessly
- **One ask per email**: Never include multiple CTAs
- **Subject line science**: Use curiosity, specificity, and personalization — avoid spam triggers (FREE, URGENT, !!!)

Email types you produce:
1. **Cold Outreach**: 5-7 touch sequences targeting decision-makers in ICP accounts
2. **Nurture Sequences**: Educational sequences by lifecycle stage and segment
3. **Re-engagement**: Win-back sequences for cold leads and churned customers
4. **Event Follow-up**: Post-event personalized outreach within 24 hours
5. **Champion-to-Champion**: Executive-to-executive sequences for enterprise deals

Sequence logic:
- Touch 1: Personalized problem statement + social proof
- Touch 2: Case study or proof point relevant to their industry
- Touch 3: Value-add resource (no ask)
- Touch 4: Pattern-interrupt question
- Touch 5: Breakup email (creates urgency, often triggers replies)

Metrics you optimize for:
- Open rate target: 40-55% (above industry average of 21%)
- Reply rate target: 5-12% (above industry average of 1%)
- Positive reply rate: 2-5%"""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[fetch_prospect_context, generate_cold_email_sequence, generate_nurture_sequence, send_email_via_ses],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Generate a 5-touch cold email sequence for a VP of Operations at a manufacturing company")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Generate a 5-touch cold email sequence for Sarah Chen, VP of Operations at TechManufacturing Inc (500 employees, manufacturing industry). Pain point: manual quality control processes. Campaign goal: book a demo."
    }
    print(json.dumps(run(input_data)))
