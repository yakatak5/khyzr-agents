"""
Threat Modeling Agent (Agent 50)
==================================
Upload an architecture diagram (PNG/JPG) → get a full STRIDE threat model report.

Phase 1: Vision — describe all components, data flows, trust boundaries from the image
Phase 2: STRIDE — systematically identify threats per component
Phase 3: Report — structured threat model with mitigations and risk ratings

Built with AWS Strands Agents + Amazon Bedrock AgentCore Runtime.
"""

import json
import os
import io
import base64
import logging
import boto3

from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("threat-modeling-agent")

app = BedrockAgentCoreApp()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def load_image_from_s3(bucket: str, key: str) -> str:
    """
    Load an architecture diagram image from S3 and return it as base64.

    Args:
        bucket: S3 bucket name
        key: S3 key (PNG or JPG file)

    Returns:
        JSON with base64 image data and media type
    """
    try:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"))
        obj = s3.get_object(Bucket=bucket, Key=key)
        data = obj["Body"].read()
        ext = key.lower().split(".")[-1]
        media_type = "image/png" if ext == "png" else "image/jpeg"
        b64 = base64.b64encode(data).decode("utf-8")
        size_kb = len(data) // 1024
        logger.info(f"Loaded image {key} ({size_kb}KB) from s3://{bucket}")
        return json.dumps({"b64": b64, "media_type": media_type, "size_kb": size_kb, "key": key})
    except Exception as e:
        logger.error(f"Failed to load image: {e}")
        return json.dumps({"status": "no_results", "note": "Could not load image."})


@tool
def analyze_architecture_image(bucket: str, key: str) -> str:
    """
    Use Bedrock vision (Claude) to analyze an architecture diagram image and
    extract all components, data flows, trust boundaries, and external entities.

    Args:
        bucket: S3 bucket containing the image
        key: S3 key of the PNG/JPG architecture diagram

    Returns:
        JSON with structured architecture description
    """
    try:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"))
        obj = s3.get_object(Bucket=bucket, Key=key)
        data = obj["Body"].read()
        ext = key.lower().split(".")[-1]
        media_type = "image/png" if ext == "png" else "image/jpeg"
        b64 = base64.b64encode(data).decode("utf-8")

        bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"))

        prompt = """Analyze this architecture diagram and extract:

1. COMPONENTS: List every service, server, database, user, external system, API, queue, etc.
   For each: name, type, description, is_external (true/false)

2. DATA_FLOWS: List every arrow/connection between components.
   For each: from, to, data_type (what data flows), protocol if visible

3. TRUST_BOUNDARIES: Identify trust zones (e.g. internet vs VPC, public vs private subnet, DMZ)
   For each: name, components_inside[]

4. ENTRY_POINTS: List all external-facing interfaces (APIs, UIs, webhooks, etc.)

5. DATA_STORES: List all databases, caches, S3 buckets, file systems

Return ONLY a JSON object with keys: components, data_flows, trust_boundaries, entry_points, data_stores.
Be thorough — missing a component means missing threats."""

        resp = bedrock.invoke_model(
            modelId=os.environ.get("VISION_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                        {"type": "text", "text": prompt}
                    ]
                }]
            })
        )
        result = json.loads(resp['body'].read())
        text = result['content'][0]['text']

        # Try to parse as JSON, otherwise return raw
        try:
            start = text.find('{')
            end   = text.rfind('}') + 1
            arch  = json.loads(text[start:end])
        except Exception:
            arch = {"raw_description": text}

        logger.info(f"Architecture analysis complete: {len(arch.get('components', []))} components found")
        return json.dumps(arch, indent=2)
    except Exception as e:
        logger.error(f"Vision analysis failed: {e}")
        return json.dumps({"status": "no_results", "note": f"Vision analysis unavailable: {str(e)[:100]}"})


@tool
def run_stride_analysis(architecture_json: str) -> str:
    """
    Run STRIDE threat analysis on the architecture description.
    STRIDE: Spoofing, Tampering, Repudiation, Information Disclosure, DoS, Elevation of Privilege

    Args:
        architecture_json: JSON string from analyze_architecture_image

    Returns:
        JSON list of identified threats with STRIDE category, component, severity, and mitigation
    """
    try:
        arch = json.loads(architecture_json)
        components  = arch.get("components", [])
        data_flows  = arch.get("data_flows", [])
        entry_points = arch.get("entry_points", [])
        data_stores  = arch.get("data_stores", [])

        threats = []

        # SPOOFING threats
        for ep in entry_points:
            name = ep if isinstance(ep, str) else ep.get("name", str(ep))
            threats.append({
                "id": f"S-{len(threats)+1:03d}",
                "stride": "Spoofing",
                "component": name,
                "threat": f"Attacker impersonates legitimate user/service at {name}",
                "severity": "HIGH",
                "likelihood": "Medium",
                "mitigation": "Implement strong authentication (MFA, mTLS, API keys with rotation). Validate identity at every trust boundary.",
                "cwe": "CWE-287"
            })

        for flow in data_flows:
            f = flow if isinstance(flow, str) else flow.get("from", "") + " → " + flow.get("to", "")
            threats.append({
                "id": f"T-{len(threats)+1:03d}",
                "stride": "Tampering",
                "component": f,
                "threat": f"Data in transit between {f} is modified by an attacker",
                "severity": "HIGH",
                "likelihood": "Medium",
                "mitigation": "Enforce TLS 1.2+ on all connections. Use message signing (HMAC/JWT) for critical flows. Enable integrity checks.",
                "cwe": "CWE-345"
            })

        for ds in data_stores:
            name = ds if isinstance(ds, str) else ds.get("name", str(ds))
            threats.append({
                "id": f"I-{len(threats)+1:03d}",
                "stride": "Information Disclosure",
                "component": name,
                "threat": f"Unauthorized access to sensitive data in {name}",
                "severity": "CRITICAL",
                "likelihood": "Medium",
                "mitigation": "Encrypt at rest (AES-256/KMS). Apply least-privilege IAM. Enable audit logging. Mask PII in logs.",
                "cwe": "CWE-200"
            })
            threats.append({
                "id": f"T-{len(threats)+1:03d}",
                "stride": "Tampering",
                "component": name,
                "threat": f"Attacker modifies or deletes data in {name}",
                "severity": "HIGH",
                "likelihood": "Low",
                "mitigation": "Enable versioning and MFA delete (S3). Use database transaction logs. Restrict write permissions by role.",
                "cwe": "CWE-494"
            })

        for comp in components:
            name = comp if isinstance(comp, str) else comp.get("name", str(comp))
            is_external = comp.get("is_external", False) if isinstance(comp, dict) else False
            comp_type = comp.get("type", "").lower() if isinstance(comp, dict) else ""

            threats.append({
                "id": f"D-{len(threats)+1:03d}",
                "stride": "Denial of Service",
                "component": name,
                "threat": f"Attacker overwhelms {name} with excessive requests",
                "severity": "MEDIUM",
                "likelihood": "Medium" if is_external else "Low",
                "mitigation": "Implement rate limiting and throttling. Use AWS WAF/Shield for external endpoints. Set Lambda concurrency limits. Enable auto-scaling.",
                "cwe": "CWE-400"
            })

            if "admin" in name.lower() or "auth" in name.lower() or "iam" in comp_type:
                threats.append({
                    "id": f"E-{len(threats)+1:03d}",
                    "stride": "Elevation of Privilege",
                    "component": name,
                    "threat": f"Attacker gains elevated privileges via {name}",
                    "severity": "CRITICAL",
                    "likelihood": "Low",
                    "mitigation": "Enforce least-privilege IAM. Require MFA for privileged actions. Log and alert on privilege escalation attempts. Rotate credentials.",
                    "cwe": "CWE-269"
                })

        # Always add repudiation threat
        threats.append({
            "id": f"R-{len(threats)+1:03d}",
            "stride": "Repudiation",
            "component": "System-wide",
            "threat": "Users deny performing actions; no audit trail exists",
            "severity": "MEDIUM",
            "likelihood": "Medium",
            "mitigation": "Enable CloudTrail, VPC Flow Logs, and application-level audit logs. Use immutable log storage. Implement digital signatures for critical transactions.",
            "cwe": "CWE-778"
        })

        summary = {s: sum(1 for t in threats if t["stride"] == s)
                   for s in ["Spoofing","Tampering","Repudiation","Information Disclosure","Denial of Service","Elevation of Privilege"]}
        by_severity = {s: sum(1 for t in threats if t["severity"] == s)
                       for s in ["CRITICAL","HIGH","MEDIUM","LOW"]}

        return json.dumps({
            "total_threats": len(threats),
            "by_stride":    summary,
            "by_severity":  by_severity,
            "threats":      threats
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def store_threat_model_report(report_content: str, bucket: str = "", key: str = "threat-model/report.md") -> str:
    """
    Store the threat model report as a downloadable markdown file in S3.

    Args:
        report_content: Full markdown threat model report
        bucket: S3 bucket (defaults to THREAT_MODEL_BUCKET env var)
        key: S3 key for the output file

    Returns:
        JSON with presigned download URL valid for 1 hour
    """
    bucket = bucket or os.environ.get("THREAT_MODEL_BUCKET", "")
    if not bucket:
        return json.dumps({"status": "skipped", "note": "THREAT_MODEL_BUCKET not set"})
    try:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"))
        s3.put_object(
            Bucket=bucket, Key=key,
            Body=report_content.encode(),
            ContentType="text/markdown",
            ContentDisposition='attachment; filename="threat-model-report.md"'
        )
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=3600
        )
        return json.dumps({"status": "stored", "download_url": url, "expires_in": "1 hour"})
    except Exception as e:
        return json.dumps({"status": "no_results", "note": "Could not store report."})


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_agent = None

def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        model = BedrockModel(
            model_id=os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"),
            region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"),
        )
        _agent = Agent(
            model=model,
            tools=[analyze_architecture_image, run_stride_analysis, store_threat_model_report],
            system_prompt="""You are the Threat Modeling Agent — a security architect who performs rigorous STRIDE threat analysis on architecture diagrams.

Workflow:
1. analyze_architecture_image(bucket, key) — extract components, flows, boundaries from the image
2. run_stride_analysis(architecture_json) — identify STRIDE threats
3. Write the full threat model report in markdown (see format below)
4. store_threat_model_report(report_content, bucket) — save it
5. Respond with:

---
DOWNLOAD_URL: <url from store_threat_model_report>
---

## 🔐 Threat Model Report

**X components · Y data flows · Z total threats (A critical, B high)**

### Architecture Summary
Brief description of what you see in the diagram.

### Threat Summary Table
| ID | STRIDE | Component | Threat | Severity |
|----|--------|-----------|--------|----------|
(one row per threat)

### Top Priority Threats
For CRITICAL and HIGH threats only — explain the threat and mitigation in 2 sentences each.

### Recommendations
5 bullet points of the most impactful security improvements.

Keep it concise and actionable. Never mention tool errors.
""",
        )
    return _agent


# ---------------------------------------------------------------------------
# AgentCore entrypoint
# ---------------------------------------------------------------------------

@app.entrypoint
def invoke(payload):
    """
    Expected payload:
    {
        "bucket": "my-bucket",
        "key": "architecture.png",
        "prompt": "optional extra context about the system"
    }
    """
    bucket = payload.get("bucket", os.environ.get("THREAT_MODEL_BUCKET", ""))
    key    = payload.get("key", os.environ.get("THREAT_MODEL_KEY", "architecture.png"))
    prompt = payload.get("prompt", "")

    if not prompt:
        if bucket:
            prompt = (
                f"Analyze the architecture diagram at s3://{bucket}/{key}. "
                "Extract all components and data flows, run full STRIDE threat analysis, "
                "generate a complete threat model report, and save it."
            )
        else:
            prompt = "I'm ready to threat model your architecture. Please upload a PNG or JPG of your architecture diagram."

    try:
        result = _get_agent()(prompt)
        return {"result": str(result)}
    except Exception as e:
        logger.error(f"Threat modeling agent error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    app.run()
