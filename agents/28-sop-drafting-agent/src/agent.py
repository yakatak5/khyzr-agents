"""
SOP Drafting Agent
==================
Converts process descriptions, recordings, or notes into structured,
formatted Standard Operating Procedures ready for team use.

Built with AWS Strands Agents + Amazon Bedrock (Claude Sonnet).
"""

import json
import os
import boto3
from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel


@tool
def parse_process_description(raw_description: str, process_name: str) -> str:
    """
    Parse a raw process description and extract structured steps.

    Args:
        raw_description: Unstructured description of the process
        process_name: Name of the process/SOP

    Returns:
        JSON structured process with identified steps, roles, and inputs/outputs
    """
    # Structure the description for SOP generation
    parsed = {
        "process_name": process_name,
        "raw_description": raw_description,
        "word_count": len(raw_description.split()),
        "structure_analysis": {
            "identified_steps": [],
            "identified_roles": [],
            "identified_systems": [],
            "decision_points": [],
            "inputs_outputs": {},
        },
        "parsing_instructions": "Agent will analyze text to extract steps, roles, decisions, and dependencies",
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    # Basic extraction: sentences that look like steps
    sentences = raw_description.split(". ")
    step_indicators = ["first", "then", "next", "after", "finally", "step", "click", "select", "enter", "navigate", "open", "create", "verify", "review", "submit", "approve"]
    
    for i, sentence in enumerate(sentences):
        s_lower = sentence.lower()
        if any(indicator in s_lower for indicator in step_indicators) or len(sentence.split()) > 5:
            parsed["structure_analysis"]["identified_steps"].append({
                "order": i + 1,
                "raw_step": sentence.strip(),
                "action_type": "procedural",
            })
    
    # Identify roles
    role_indicators = ["manager", "analyst", "engineer", "team", "department", "lead", "coordinator", "admin", "approver", "reviewer"]
    words = raw_description.lower().split()
    for word in words:
        for role in role_indicators:
            if role in word:
                parsed["structure_analysis"]["identified_roles"].append(word)
    
    parsed["structure_analysis"]["identified_roles"] = list(set(parsed["structure_analysis"]["identified_roles"]))
    
    return json.dumps(parsed, indent=2)


@tool
def transcribe_audio_description(s3_uri: str) -> str:
    """
    Transcribe an audio recording of a process description using Amazon Transcribe.

    Args:
        s3_uri: S3 URI of the audio file (e.g., s3://bucket/recordings/process.mp4)

    Returns:
        JSON with transcription text and job details
    """
    transcribe = boto3.client("transcribe", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    job_name = f"sop-transcription-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    try:
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": s3_uri},
            MediaFormat=s3_uri.rsplit(".", 1)[-1] if "." in s3_uri else "mp4",
            LanguageCode="en-US",
            OutputBucketName=os.environ.get("TRANSCRIPTION_OUTPUT_BUCKET", "khyzr-transcriptions"),
        )
        return json.dumps({"status": "transcription_started", "job_name": job_name, "note": "Poll job status — transcription typically completes in 1-5 minutes"})
    except Exception as e:
        return json.dumps({"error": str(e), "note": "Configure TRANSCRIPTION_OUTPUT_BUCKET and ensure Transcribe permissions"})


@tool
def generate_sop_document(process_name: str, steps: list, metadata: dict) -> str:
    """
    Generate a formatted SOP document from structured steps.

    Args:
        process_name: Name of the SOP
        steps: List of step dicts with: step_number, action, responsible_party, inputs, outputs, notes
        metadata: SOP metadata: owner, department, version, review_date, purpose, scope

    Returns:
        Markdown-formatted SOP document
    """
    version = metadata.get("version", "1.0")
    owner = metadata.get("owner", "TBD")
    department = metadata.get("department", "Operations")
    purpose = metadata.get("purpose", f"Define the standard process for {process_name}")
    scope = metadata.get("scope", "All team members responsible for this process")
    review_date = metadata.get("review_date", (datetime.utcnow().replace(year=datetime.utcnow().year + 1)).strftime("%Y-%m-%d"))
    
    sop_md = f"""# Standard Operating Procedure: {process_name}

---

| Field | Value |
|-------|-------|
| **SOP ID** | SOP-{datetime.utcnow().strftime('%Y%m%d')}-{process_name[:3].upper()} |
| **Version** | {version} |
| **Owner** | {owner} |
| **Department** | {department} |
| **Effective Date** | {datetime.utcnow().strftime('%Y-%m-%d')} |
| **Next Review Date** | {review_date} |
| **Status** | Draft |

---

## 1. Purpose

{purpose}

## 2. Scope

{scope}

## 3. Prerequisites

Before beginning this procedure, ensure:
- [ ] You have the necessary system access and permissions
- [ ] Required inputs/materials are available
- [ ] Any predecessor processes have been completed

## 4. Procedure

"""
    
    for i, step in enumerate(steps, 1):
        action = step.get("action", step.get("raw_step", f"Step {i}"))
        responsible = step.get("responsible_party", "Assigned team member")
        inputs = step.get("inputs", [])
        outputs = step.get("outputs", [])
        notes = step.get("notes", "")
        
        sop_md += f"""### Step {i}: {action[:80]}

**Responsible Party:** {responsible}  
"""
        if inputs:
            sop_md += f"**Inputs Required:** {', '.join(inputs) if isinstance(inputs, list) else inputs}  
"
        if outputs:
            sop_md += f"**Expected Output:** {', '.join(outputs) if isinstance(outputs, list) else outputs}  
"
        sop_md += f"
{action}

"
        if notes:
            sop_md += f"> **Note:** {notes}

"

    sop_md += f"""
## 5. Quality Checks

| Check | Criteria | Responsible |
|-------|----------|-------------|
| Completion verification | All steps completed, outputs produced | {owner} |
| Accuracy check | Outputs meet expected quality standards | Reviewer |
| Documentation | All records updated in relevant systems | {owner} |

## 6. Exceptions and Escalations

If any step cannot be completed as described, escalate to the {department} manager immediately. Document the exception with: what happened, why it deviated, and corrective action taken.

## 7. Change History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| {version} | {datetime.utcnow().strftime('%Y-%m-%d')} | {owner} | Initial draft |

---
*This SOP was generated by the Khyzr SOP Drafting Agent. Review with subject matter experts before finalizing.*
"""
    
    # Save to S3
    bucket = os.environ.get("SOP_DOCS_BUCKET", "khyzr-sop-documents")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    key = f"sops/{process_name.replace(' ', '-').lower()}-v{version}.md"
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=sop_md.encode("utf-8"), ContentType="text/markdown")
        return json.dumps({"status": "saved", "s3_uri": f"s3://{bucket}/{key}", "preview": sop_md[:500]})
    except Exception as e:
        return json.dumps({"status": "generated", "error": str(e), "sop_document": sop_md})


@tool
def review_existing_sop(s3_uri: str) -> str:
    """
    Review an existing SOP for completeness, clarity, and outdated content.

    Args:
        s3_uri: S3 URI of existing SOP document

    Returns:
        JSON review with improvement recommendations
    """
    bucket, key = s3_uri.replace("s3://", "").split("/", 1)
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        content = obj["Body"].read().decode("utf-8")
        
        review = {
            "s3_uri": s3_uri,
            "word_count": len(content.split()),
            "has_purpose": "## 1. Purpose" in content or "Purpose" in content,
            "has_steps": "Step" in content or "##" in content,
            "has_owner": "Owner" in content,
            "has_review_date": "Review Date" in content or "review_date" in content.lower(),
            "recommendations": [],
        }
        
        if not review["has_purpose"]:
            review["recommendations"].append("Add a clear Purpose section explaining why this SOP exists")
        if not review["has_owner"]:
            review["recommendations"].append("Assign a clear SOP owner responsible for keeping it current")
        if not review["has_review_date"]:
            review["recommendations"].append("Set a review date — SOPs should be reviewed at least annually")
        if review["word_count"] > 3000:
            review["recommendations"].append("Consider splitting into multiple focused SOPs — this may be too complex")
        if review["word_count"] < 200:
            review["recommendations"].append("SOP may be too brief — ensure all critical steps are documented")
        
        return json.dumps(review, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


SYSTEM_PROMPT = """You are the SOP Drafting Agent for Khyzr — a process documentation specialist and quality management expert.

Your mission is to transform messy process descriptions, recordings, and notes into clear, structured, and compliant Standard Operating Procedures that any team member can follow.

SOP quality standards you apply:
- **Clarity**: Each step should be actionable — start with a verb. "Click Save" not "The save button is used"
- **Completeness**: Every step needed to execute the process from start to finish
- **Specificity**: Include system names, menu paths, field names, and validation criteria
- **Responsibility**: Every step has a clear owner or role
- **Exception handling**: What to do when things go wrong
- **Measurability**: Quality checks at key points

SOP structure you produce:
1. Header (SOP ID, version, owner, review date)
2. Purpose — why this SOP exists
3. Scope — who this applies to
4. Prerequisites — what must be true before starting
5. Numbered procedure steps with inputs/outputs
6. Quality check criteria
7. Exception and escalation guidance
8. Change history

Documentation process:
1. Parse or transcribe the raw process description
2. Structure into logical steps with clear ownership
3. Generate formatted SOP document
4. Validate for completeness and clarity
5. Save to S3 and notify SOP owner for review

Always remind users: SOPs must be reviewed by the process owner and subject matter experts before becoming official policy."""


model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[parse_process_description, transcribe_audio_description, generate_sop_document, review_existing_sop],
    system_prompt=SYSTEM_PROMPT,
)


def run(input_data: dict) -> dict:
    """Main entry point for AgentCore."""
    message = input_data.get("message", "Draft an SOP from the provided process description")
    response = agent(message)
    return {"result": str(response)}


if __name__ == "__main__":
    import sys
    input_data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {
        "message": "Create an SOP for our monthly financial close process. Steps: 1) Export all GL transactions from ERP 2) Reconcile bank accounts 3) Review and approve journal entries 4) Run variance analysis vs budget 5) Generate financial statements 6) CFO review and sign-off. Owner: Controller, Department: Finance."
    }
    print(json.dumps(run(input_data)))
