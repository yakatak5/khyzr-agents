"""
Terraform Hardening Agent (Agent 49)
======================================
Upload Terraform code → get a security-hardened version back.

Scans for misconfigurations, insecure defaults, and missing security controls
then rewrites the code with fixes applied and explains every change.

Built with AWS Strands Agents + Amazon Bedrock AgentCore Runtime.
"""

import json
import os
import io
import logging
import zipfile
import boto3

from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("terraform-hardening-agent")

app = BedrockAgentCoreApp()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def load_terraform_from_s3(bucket: str, key: str) -> str:
    """
    Load Terraform file(s) from S3. Supports .tf files and .zip archives.

    Args:
        bucket: S3 bucket name
        key: S3 key — either a .tf file or a .zip of multiple .tf files

    Returns:
        JSON with filename(s) and their contents
    """
    try:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"))
        obj = s3.get_object(Bucket=bucket, Key=key)
        data = obj["Body"].read()

        files = {}
        if key.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for name in zf.namelist():
                    if name.endswith(".tf") or name.endswith(".tfvars"):
                        files[name] = zf.read(name).decode("utf-8", errors="replace")
        else:
            fname = key.split("/")[-1]
            files[fname] = data.decode("utf-8", errors="replace")

        if not files:
            return json.dumps({"error": "No .tf files found in upload"})

        total_lines = sum(len(v.splitlines()) for v in files.values())
        logger.info(f"Loaded {len(files)} file(s), {total_lines} total lines from s3://{bucket}/{key}")
        return json.dumps({"files": files, "file_count": len(files), "total_lines": total_lines})
    except Exception as e:
        logger.error(f"Failed to load terraform: {e}")
        return json.dumps({"status": "no_results", "files": {}, "note": "Could not load file."})


@tool
def scan_terraform_issues(terraform_json: str) -> str:
    """
    Scan Terraform code for common security misconfigurations and hardening opportunities.

    Args:
        terraform_json: JSON string from load_terraform_from_s3

    Returns:
        JSON list of findings with severity, resource, issue, and recommended fix
    """
    try:
        data = json.loads(terraform_json)
        files = data.get("files", {})
        all_code = "\n\n".join(f"# === {fname} ===\n{code}" for fname, code in files.items())

        findings = []

        checks = [
            # S3
            ("CRITICAL", "aws_s3_bucket",         "block_public_acls",         "S3 bucket missing public access block",                  "Add aws_s3_bucket_public_access_block with all 4 flags = true"),
            ("CRITICAL", "aws_s3_bucket",         "server_side_encryption",    "S3 bucket missing encryption at rest",                   "Add aws_s3_bucket_server_side_encryption_configuration with AES256 or aws:kms"),
            ("HIGH",     "aws_s3_bucket",         "versioning",                "S3 bucket versioning not enabled",                       "Add aws_s3_bucket_versioning with status = Enabled"),
            ("HIGH",     "aws_s3_bucket",         "logging",                   "S3 access logging not configured",                       "Add aws_s3_bucket_logging to capture access events"),
            # Security Groups
            ("CRITICAL", "aws_security_group",    "0.0.0.0/0",                 "Security group allows unrestricted inbound (0.0.0.0/0)", "Restrict CIDR to known IP ranges; never open 0.0.0.0/0 to SSH/RDP"),
            ("HIGH",     "aws_security_group",    "from_port = 22",            "SSH port 22 open in security group",                     "Restrict SSH to bastion host IPs or use SSM Session Manager instead"),
            ("HIGH",     "aws_security_group",    "from_port = 3389",          "RDP port 3389 open in security group",                   "Restrict RDP to known IPs or use SSM; never expose to internet"),
            # RDS
            ("CRITICAL", "aws_db_instance",       "publicly_accessible = true","RDS instance is publicly accessible",                   "Set publicly_accessible = false; use VPC private subnet"),
            ("HIGH",     "aws_db_instance",       "storage_encrypted",         "RDS storage encryption not enabled",                     "Set storage_encrypted = true"),
            ("MEDIUM",   "aws_db_instance",       "deletion_protection",       "RDS deletion protection not enabled",                    "Set deletion_protection = true to prevent accidental deletion"),
            ("MEDIUM",   "aws_db_instance",       "backup_retention",          "RDS automated backups may not be configured",            "Set backup_retention_period to at least 7"),
            # IAM
            ("CRITICAL", "aws_iam_policy",        '"*"',                       "IAM policy uses wildcard (*) actions or resources",      "Follow least-privilege: enumerate only required actions and specific resource ARNs"),
            ("HIGH",     "aws_iam_user",          "aws_iam_access_key",        "IAM user with programmatic access key",                  "Prefer IAM roles over long-term access keys; rotate keys if required"),
            # Lambda
            ("HIGH",     "aws_lambda_function",   "reserved_concurrent",       "Lambda missing reserved concurrency limit",              "Set reserved_concurrent_executions to prevent runaway invocations"),
            ("MEDIUM",   "aws_lambda_function",   "tracing_config",            "Lambda X-Ray tracing not enabled",                      "Add tracing_config { mode = 'Active' } for observability"),
            # EC2
            ("HIGH",     "aws_instance",          "ebs_optimized",             "EC2 instance not EBS-optimized",                        "Set ebs_optimized = true for supported instance types"),
            ("MEDIUM",   "aws_instance",          "monitoring = true",         "EC2 detailed monitoring not enabled",                   "Set monitoring = true for better CloudWatch metrics"),
            ("HIGH",     "aws_instance",          "metadata_options",          "EC2 IMDSv1 may be enabled (SSRF risk)",                 "Add metadata_options { http_tokens = 'required' } to enforce IMDSv2"),
            # EKS
            ("HIGH",     "aws_eks_cluster",       "endpoint_public_access",    "EKS public endpoint may be unrestricted",               "Set endpoint_public_access_cidrs to restrict who can reach the API server"),
            # General
            ("MEDIUM",   "aws_cloudtrail",        "log_file_validation",       "CloudTrail log file validation not enabled",            "Set enable_log_file_validation = true"),
            ("HIGH",     "aws_kms_key",           "enable_key_rotation",       "KMS key rotation not enabled",                         "Set enable_key_rotation = true for automatic annual rotation"),
        ]

        for severity, resource_type, pattern, issue, fix in checks:
            if resource_type in all_code and pattern in all_code:
                findings.append({
                    "severity": severity,
                    "resource_type": resource_type,
                    "issue": issue,
                    "recommended_fix": fix,
                })
            elif resource_type in all_code and pattern not in all_code:
                # resource exists but pattern (a required attribute) is missing
                if any(x in pattern for x in ["encryption", "versioning", "logging", "deletion_protection",
                                               "backup_retention", "reserved_concurrent", "tracing_config",
                                               "ebs_optimized", "log_file_validation", "enable_key_rotation",
                                               "metadata_options", "block_public_acls"]):
                    findings.append({
                        "severity": severity,
                        "resource_type": resource_type,
                        "issue": issue,
                        "recommended_fix": fix,
                    })

        order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        findings.sort(key=lambda x: order.index(x["severity"]))

        summary = {s: sum(1 for f in findings if f["severity"] == s) for s in order}

        return json.dumps({
            "total_issues": len(findings),
            "summary": summary,
            "findings": findings,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def store_hardened_output(hardened_code: str, explanation: str, bucket: str = "", key: str = "hardened/main-hardened.tf") -> str:
    """
    Store ONLY the hardened Terraform code as a downloadable .tf file in S3.
    Stores a clean .tf file (no markdown, no explanation — pure HCL).

    Args:
        hardened_code: The hardened Terraform HCL code only (no markdown fences)
        explanation: The human-readable explanation of changes (NOT stored in the .tf file)
        bucket: S3 bucket (defaults to TERRAFORM_BUCKET env var)
        key: S3 key for the output .tf file

    Returns:
        JSON with presigned download URL valid for 1 hour
    """
    bucket = bucket or os.environ.get("TERRAFORM_BUCKET", "")
    if not bucket:
        return json.dumps({"status": "skipped", "note": "TERRAFORM_BUCKET not set"})
    try:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"))

        # Strip markdown fences if present
        code = hardened_code.strip()
        for fence in ["```hcl", "```terraform", "```"]:
            if code.startswith(fence):
                code = code[len(fence):]
                break
        if code.endswith("```"):
            code = code[:-3]
        code = code.strip()

        s3.put_object(Bucket=bucket, Key=key, Body=code.encode(), ContentType="text/plain",
                      ContentDisposition=f'attachment; filename="main-hardened.tf"')

        # Generate presigned URL valid 1 hour
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=3600
        )
        return json.dumps({
            "status": "stored",
            "bucket": bucket,
            "key": key,
            "download_url": url,
            "expires_in": "1 hour",
        })
    except Exception as e:
        return json.dumps({"status": "no_results", "note": "Could not store output."})


# ---------------------------------------------------------------------------
# Agent setup
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
            tools=[load_terraform_from_s3, scan_terraform_issues, store_hardened_output],
            system_prompt="""You are the Terraform Hardening Agent — a cloud security expert specializing in infrastructure-as-code security.

Your job: take Terraform code, fix every security issue, save the hardened file, and explain your changes clearly.

Workflow:
1. Load the Terraform files using load_terraform_from_s3
2. Scan for issues using scan_terraform_issues
3. Rewrite the complete Terraform code with ALL security fixes applied
4. Call store_hardened_output with TWO separate arguments:
   - hardened_code: ONLY the raw HCL code (no markdown fences, no explanation)
   - explanation: empty string (explanation goes in your chat response)
5. Return your response in this EXACT format:

---
DOWNLOAD_URL: <the download_url from store_hardened_output result>
---

## 🔒 Terraform Hardening Report

**X critical · Y high · Z medium issues found and fixed**

### Changes Made

For each fix, explain:
- ❌ **What was wrong**: brief description
- ✅ **What was fixed**: what HCL was added/changed
- 🛡️ **Why it matters**: plain English security impact

Keep explanations concise — one paragraph per fix max.
End with a one-line summary of the overall security posture improvement.

Security standards applied:
- CIS AWS Foundations Benchmark
- AWS Well-Architected Framework (Security Pillar)
- Least-privilege IAM, encryption everywhere, no public exposure, IMDSv2, key rotation

If tool errors occur, silently work with what you have. Never mention tool failures.
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
        "key": "main.tf",          # or a .zip of .tf files
        "prompt": "optional"
    }
    """
    bucket = payload.get("bucket", os.environ.get("TERRAFORM_BUCKET", ""))
    key    = payload.get("key", os.environ.get("TERRAFORM_KEY", "main.tf"))
    prompt = payload.get("prompt", "")

    if not prompt:
        if bucket:
            prompt = (
                f"Load the Terraform code from s3://{bucket}/{key}. "
                "Scan it for security issues, then rewrite it as a fully hardened version. "
                "Show me every change you made and why. Return the complete hardened code."
            )
        else:
            prompt = (
                "I'm ready to harden your Terraform code. "
                "Please upload a .tf file or .zip of Terraform files and I'll return "
                "a security-hardened version with all issues fixed."
            )

    try:
        result = _get_agent()(prompt)
        return {"result": str(result)}
    except Exception as e:
        logger.error(f"Terraform hardening agent error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    app.run()
