# Deployment — Kiro Automation Guide

## 🚀 Deploy Any Agent with One Command

When asked to **"deploy agent X"**, follow this exact workflow:

---

## Step 1 — Resolve the Agent Directory

Use the agent map in `project.md` to find the directory.
Examples:
- "deploy agent 36" → `agents/36-ap-automation-agent`
- "deploy AP automation" → `agents/36-ap-automation-agent`
- "deploy AR collections" → `agents/40-ar-collections-agent`
- "deploy expense audit" → `agents/39-expense-audit-agent`

---

## Step 2 — Pre-flight Checks

Run these before deploying:

```bash
# 1. Verify AWS credentials
aws sts get-caller-identity

# 2. Check Terraform is installed
terraform --version

# 3. Verify Bedrock model access is enabled
aws bedrock list-foundation-models --region us-east-1 \
  --query "modelSummaries[?modelId=='anthropic.claude-sonnet-4-5-v1:0'].modelId" \
  --output text

# 4. Check the agent directory exists
ls agents/<XX-agent-name>/infra/main.tf

# 5. For AgentCore agents (36, 40): verify Docker with buildx is installed
docker buildx version
# If not set up: docker buildx create --use
```

If Bedrock model access is not enabled, direct the user to:
AWS Console → Amazon Bedrock → Model access → Enable Claude Sonnet → Submit

---

## Step 3 — Deploy

```bash
cd agents/<XX-agent-name>/infra
terraform init -upgrade
terraform plan -out=tfplan
terraform apply tfplan
```

For **AgentCore agents (36, 40)**: Terraform will automatically build and push the ARM64 Docker image to ECR via the `null_resource.docker_build_push` provisioner. **Docker with buildx must be installed** on the machine running `terraform apply`.

Capture all outputs from `terraform apply`. They contain everything needed for testing.

---

## Step 4 — Extract & Present Outputs

After apply completes, run:

```bash
terraform output -json
```

### For AgentCore Runtime agents (36, 40) — present in this format:

---

### ✅ Agent XX Deployed Successfully (AgentCore Runtime)

**Resources created:**
- 🤖 AgentCore Runtime ARN: `<agent_runtime_arn>`
- 🆔 AgentCore Runtime ID: `<agent_runtime_id>`
- 📦 ECR Repository: `<ecr_repository_url>`
- 🗄️ DynamoDB Table: `<dynamodb_table_name>` *(if applicable)*
- 🪣 S3 Bucket: `<invoices_bucket or ar_reports_bucket>` *(if applicable)*

**Test it now — copy and run:**
```bash
<demo_invoke_command from terraform output>
```

**Check container logs:**
```bash
aws logs tail /aws/bedrock-agentcore/<agent_runtime_id> --follow --region us-east-1
```

**Verify DynamoDB records** *(if applicable)*:
```bash
aws dynamodb scan --table-name <dynamodb_table_name> --region us-east-1
```

---

## Step 5 — Smoke Test (AgentCore)

```bash
RUNTIME_ARN=$(terraform output -raw agent_runtime_arn)

aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --payload '{"prompt": "Run a quick self-test and confirm you are operational."}' \
  --region us-east-1
```

Report the result to the user.

---

## Rebuild & Push Docker Image Only

If the agent code changed but infrastructure didn't:

```bash
# From repo root
./scripts/build-push.sh agents/<XX-agent-name> us-east-1
```

Or re-run `terraform apply` — it detects file hash changes and re-triggers the build.

---

## Deploy All Agents

```bash
cd infra
terraform init -upgrade
terraform plan -out=tfplan
terraform apply tfplan
terraform output -json
```

---

## Teardown a Single Agent

```bash
cd agents/<XX-agent-name>/infra
terraform destroy -auto-approve
```

## Teardown All Agents

```bash
cd infra
terraform destroy -auto-approve
```

---

## Troubleshooting

### "Error: no valid credential sources"
```bash
aws configure
# or
export AWS_PROFILE=your-profile
```

### "Model access denied" / ResourceNotFoundException on foundation model
Enable Claude Sonnet in AWS Console → Bedrock → Model access

### "Docker not found" during terraform apply (AgentCore agents)
Install Docker with buildx support:
```bash
# After installing Docker:
docker buildx create --use
```

### "ARM64 build failed" (exec format error)
Set up a buildx builder with ARM64 emulation:
```bash
docker buildx create --use
# On Apple Silicon, ARM64 builds natively without emulation
```

### "Container not READY" — AgentCore runtime not starting
Check CloudWatch logs for the container:
```bash
aws logs tail /aws/bedrock-agentcore/<agent_runtime_id> --follow --region us-east-1
# Common causes: missing Python dependency, import error, bad entrypoint
```

### "Error creating Bedrock Agent: ValidationException"
The foundation model ID may have changed. Check current IDs:
```bash
aws bedrock list-foundation-models --region us-east-1 \
  --query "modelSummaries[?providerName=='Anthropic'].modelId" --output table
```
Update `foundation_model` in `terraform.tfvars`

### "AccessDenied on ecr:GetAuthorizationToken"
The AgentCore IAM role needs `ecr:GetAuthorizationToken` with `Resource: "*"` (AWS design requirement).
Verify `aws_iam_role_policy.agentcore_policy` includes the ECR statement.

### "Invalid payload" when invoking AgentCore runtime
Make sure payload is JSON-encoded bytes with a `"prompt"` key:
```python
payload=json.dumps({"prompt": "your message"}).encode()
```

### "AccessDenied on s3:GetObject" for OpenAPI schema (legacy agents)
Legacy agents only — not applicable to AgentCore agents.

### Check what's deployed
```bash
# List AgentCore runtimes
aws bedrock-agentcore list-agent-runtimes --region us-east-1

# List ECR repositories matching khyzr
aws ecr describe-repositories --region us-east-1 \
  --query "repositories[?starts_with(repositoryName,'khyzr')].repositoryName" --output table

# List all DynamoDB tables matching khyzr
aws dynamodb list-tables --region us-east-1 \
  --query "TableNames[?starts_with(@,'khyzr')]" --output table
```

---

## Cost Estimate Per Agent (Monthly)

| Usage Level | Bedrock (Claude) | AgentCore Runtime | DynamoDB | S3 | Total |
|-------------|-----------------|-------------------|----------|----|-------|
| Demo/idle | ~$0 | ~$0 | ~$0 | ~$0.01 | **~$0.01** |
| Light (100 invocations) | ~$1–5 | ~$0.05 | ~$0.01 | ~$0.01 | **~$1–5** |
| Medium (1,000 invocations) | ~$10–50 | ~$0.50 | ~$0.10 | ~$0.05 | **~$10–50** |

Fully containerized — zero compute cost when idle (AgentCore scales to zero).
