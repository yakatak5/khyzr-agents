# AR Collections Agent — Demo Guide

## What This Agent Does

End-to-end accounts receivable collections automation:

1. **Fetches** the AR aging report (JSON from S3 or Excel via `excel_source`)
2. **Scores** each account by collection risk tier (Critical/High/Medium/Low)
3. **Drafts** personalized collection emails matched to risk tier
4. **Escalates** overdue accounts to appropriate personnel
5. **Updates** collection statuses in DynamoDB

---

## Deploy

> **Prerequisites:**
> - Docker with buildx installed (required for ARM64 container builds)
> - `docker buildx create --use` if buildx builder not set up
> - AWS credentials with ECR, AgentCore, DynamoDB, S3 permissions

```bash
cd agents/40-ar-collections-agent/infra
terraform init -upgrade
terraform plan -out=tfplan
terraform apply tfplan
```

Takes ~5 minutes. Terraform will:

- ✅ Create ECR repository (`khyzr/ar-collections-agent`)
- ✅ Build ARM64 Docker image and push to ECR
- ✅ Create AgentCore Runtime with Claude Sonnet
- ✅ Create DynamoDB table (AR collections status)
- ✅ Create S3 bucket (aging reports + demo JSON + demo Excel pre-loaded)
- ✅ Create IAM role with least-privilege permissions

> **Note:** The `null_resource.docker_build_push` provisioner runs `docker buildx build --platform linux/arm64` automatically during `terraform apply`. Docker must be installed on the machine running Terraform.

---

## Run the Demo

After `terraform apply` completes, copy the `demo_invoke_command` from the Terraform outputs and run it.

### Python SDK

```python
import boto3, json

client = boto3.client("bedrock-agentcore", region_name="us-east-1")
response = client.invoke_agent_runtime(
    agentRuntimeArn="<AGENT_RUNTIME_ARN>",   # from terraform output agent_runtime_arn
    payload=json.dumps({
        "prompt": "Work the full collections queue: fetch aging AR, score all accounts, draft collection emails, escalate high-risk accounts, update statuses."
    }).encode()
)
# Response is streaming
chunks = [c.get("chunk", b"") for c in response.get("body", [])]
print(b"".join(chunks).decode())
```

### AWS CLI

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <AGENT_RUNTIME_ARN> \
  --payload '{"prompt": "Work the full collections queue: fetch aging AR, score all accounts, draft collection emails, escalate high-risk accounts, update statuses."}' \
  --region us-east-1
```

### Excel Aging Report Demo

```bash
python3 -c "
import boto3, json
client = boto3.client('bedrock-agentcore', region_name='us-east-1')
response = client.invoke_agent_runtime(
    agentRuntimeArn='<AGENT_RUNTIME_ARN>',
    payload=json.dumps({
        'prompt': 'Fetch the Excel aging report from s3://<AR_REPORTS_BUCKET>/reports/aging-report-demo.xlsx, score all accounts, draft collection emails, escalate as needed, and update statuses.'
    }).encode()
)
chunks = [c.get('chunk', b'') for c in response.get('body', [])]
print(b''.join(chunks).decode())
"
```

---

## Expected Output

The agent will call all 5 tools in sequence:

| Step | Tool | Expected Result |
|------|------|-----------------|
| 1 | `fetch_aging_report` | 4 overdue accounts, total AR $1,847,500 |
| 2 | `score_collection_risk` | ACC-10092 (Critical, score 81), ACC-10078 (High, score 72), ACC-10045 (High, score 65), ACC-10021 (Medium, score 35) |
| 3 | `draft_collection_email` | Tier-appropriate email for each account |
| 4 | `escalate_account` | Critical/High → AR Manager + CFO notified |
| 5 | `update_collection_status` | All accounts updated in DynamoDB |

Check DynamoDB to confirm status updates:

```bash
aws dynamodb scan \
  --table-name $(terraform -chdir=infra output -raw dynamodb_table_name) \
  --region us-east-1 \
  --output json | python3 -m json.tool
```

---

## Risk Tier Framework

| Tier | Criteria | Email Tone | Escalation |
|------|----------|------------|------------|
| **Low** | 1-30 days, good history | Friendly reminder | None |
| **Medium** | 31-60 days or slow-pay | Formal notice + payment plan | AR Manager |
| **High** | 61-90 days or large balance | Urgent — 48h deadline | AR Manager + direct call |
| **Critical** | 90+ days or poor history | Final demand | AR Manager + CFO + agency referral |

---

## Demo Accounts

| Account | Company | Days Overdue | Balance | History | Expected Tier |
|---------|---------|-------------|---------|---------|---------------|
| ACC-10021 | Nexus Technologies Inc. | 32 | $48,500 | good | **Medium** |
| ACC-10045 | Meridian Logistics Group | 53 | $127,000 | slow_pay | **High** |
| ACC-10078 | Cascade Retail Corp | 88 | $89,500 | poor | **High** |
| ACC-10092 | Summit Healthcare Partners | 102 | $42,000 | poor | **Critical** |

---

## Architecture

```
User / CLI / SDK
       │
       │  invoke_agent_runtime (payload: {"prompt": "..."})
       ▼
AgentCore Runtime (ARM64 container on bedrock-agentcore.amazonaws.com)
       │
       │  Strands Agent orchestrates tool calls (Claude Sonnet)
       ▼
   agent.py (BedrockAgentCoreApp)
       ├── fetch_aging_report      → S3 fetch (JSON or Excel .xlsx)
       ├── score_collection_risk   → risk tier calculation
       ├── draft_collection_email  → tier-appropriate email drafting
       ├── escalate_account        → internal notifications
       └── update_collection_status → DynamoDB write
               │
               ▼
           DynamoDB (AR Collections)
           S3 (Aging Reports)
```

---

## File Structure

```
agents/40-ar-collections-agent/
├── src/
│   ├── agent.py                  # BedrockAgentCoreApp + all 5 tool functions
│   └── demo_aging_report.xlsx    # Demo Excel aging report (pre-loaded to S3)
├── infra/
│   └── main.tf                   # Terraform — AgentCore + ECR + DynamoDB + S3 + IAM
├── docs/
│   └── DEMO.md                   # This file
├── requirements.txt              # Python dependencies (includes bedrock-agentcore)
└── Dockerfile                    # ARM64 container build (required by AgentCore)
```

---

## Build & Push Docker Image Manually

If you need to rebuild the image without running `terraform apply`:

```bash
# From repo root
./scripts/build-push.sh agents/40-ar-collections-agent us-east-1

# Or manually:
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="$ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/khyzr/ar-collections-agent"

aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com"

docker buildx build --platform linux/arm64 \
  -t "$ECR_REPO:latest" \
  --push \
  agents/40-ar-collections-agent/
```

---

## Teardown

```bash
cd agents/40-ar-collections-agent/infra
terraform destroy
```

Removes all AWS resources. No ongoing costs after destroy.

> **Note:** `force_delete = true` is set on the ECR repo and `force_destroy = true` on S3 buckets, so Terraform will clean them up automatically.

---

## Troubleshooting

**"Docker not found" during terraform apply**
→ Install Docker with buildx support. Then: `docker buildx create --use`

**"ARM64 build failed" (exec format error)**
→ Run `docker buildx create --use` to set up a buildx builder with ARM64 emulation.
→ On Apple Silicon Macs, ARM64 builds natively.

**"Container not READY" in AgentCore**
→ Check CloudWatch logs: `/aws/bedrock-agentcore/<runtime-id>`
```bash
aws logs tail /aws/bedrock-agentcore/$(terraform -chdir=infra output -raw agent_runtime_id) --follow
```

**"ResourceNotFoundException" on DynamoDB write**
→ The env var `AR_COLLECTIONS_TABLE` must match the actual table name. Verify:
```bash
terraform -chdir=infra output dynamodb_table_name
```

**"AccessDeniedException" invoking Bedrock model**
→ Ensure `anthropic.claude-sonnet-4-5-v1:0` is enabled in your account under **Bedrock → Model access**.

**"Invalid payload" error**
→ Make sure the payload is JSON-encoded bytes with a `"prompt"` key:
```python
payload=json.dumps({"prompt": "your message here"}).encode()
```
