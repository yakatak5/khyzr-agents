# Deployment — Kiro Automation Guide

## 🚀 Deploy Any Agent with One Command

When asked to **"deploy agent X"**, follow this exact workflow:

---

## Step 1 — Resolve the Agent Directory

Use the agent map in `project.md` to find the directory.
Examples:
- "deploy agent 36" → `agents/36-ap-automation-agent`
- "deploy AP automation" → `agents/36-ap-automation-agent`
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

Capture all outputs from `terraform apply`. They contain everything needed for testing.

---

## Step 4 — Extract & Present Outputs

After apply completes, run:

```bash
terraform output -json
```

Parse and present to the user in this format:

---

### ✅ Agent XX Deployed Successfully

**Resources created:**
- 🤖 Bedrock Agent ID: `<agent_id>`
- 🔗 Agent Alias ID: `<agent_alias_id>`
- ⚡ Lambda Function: `<lambda_function_name>`
- 🗄️ DynamoDB Table: `<dynamodb_table_name>` *(if applicable)*
- 🪣 S3 Bucket: `<invoices_bucket>` *(if applicable)*

**Test it now — copy and run:**
```bash
<demo_invoke_command from terraform output>
```

**Or test via AWS Console:**
1. Go to **Amazon Bedrock → Agents**
2. Find `<agent_name>`
3. Click **Test** (top right)
4. Type your test message

**Check logs:**
```bash
aws logs tail /aws/lambda/<lambda_function_name> --follow --region us-east-1
```

**Verify DynamoDB records** *(if applicable)*:
```bash
aws dynamodb scan --table-name <dynamodb_table_name> --region us-east-1
```

---

## Step 5 — Smoke Test

Run a quick smoke test automatically after deploy:

```bash
# For agents with Lambda action groups (e.g. agent 36)
aws bedrock-agent-runtime invoke-agent \
  --agent-id <agent_id> \
  --agent-alias-id <agent_alias_id> \
  --session-id smoke-test-$(date +%s) \
  --region us-east-1 \
  --input-text "Run a quick self-test and confirm you are operational." \
  --cli-binary-format raw-in-base64-out \
  /tmp/smoke_test_output.json 2>&1

cat /tmp/smoke_test_output.json
```

Report the result to the user.

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

### "Error creating Bedrock Agent: ValidationException"
The foundation model ID may have changed. Check current IDs:
```bash
aws bedrock list-foundation-models --region us-east-1 \
  --query "modelSummaries[?providerName=='Anthropic'].modelId" --output table
```
Update `foundation_model` in `terraform.tfvars`

### "Lambda function not found" during Action Group creation
The Lambda must be deployed before the Action Group. Check `depends_on` in `main.tf`.
Run `terraform apply` again — it usually resolves on retry.

### "AccessDenied on s3:GetObject" for OpenAPI schema
Bedrock needs `s3:GetObject` permission on the schema bucket.
Verify `aws_iam_role_policy.bedrock_agent_policy` includes the schema bucket ARN.

### Check what's deployed
```bash
# List all Bedrock agents in account
aws bedrock-agent list-agents --region us-east-1

# List all Lambda functions matching khyzr
aws lambda list-functions --region us-east-1 \
  --query "Functions[?starts_with(FunctionName,'khyzr')].FunctionName" --output table

# List all DynamoDB tables matching khyzr
aws dynamodb list-tables --region us-east-1 \
  --query "TableNames[?starts_with(@,'khyzr')]" --output table
```

---

## Cost Estimate Per Agent (Monthly)

| Usage Level | Bedrock (Claude) | Lambda | DynamoDB | S3 | Total |
|-------------|-----------------|--------|----------|----|-------|
| Demo/idle | ~$0 | ~$0 | ~$0 | ~$0.01 | **~$0.01** |
| Light (100 invocations) | ~$1–5 | ~$0.01 | ~$0.01 | ~$0.01 | **~$1–5** |
| Medium (1,000 invocations) | ~$10–50 | ~$0.10 | ~$0.10 | ~$0.05 | **~$10–50** |

Fully serverless — zero cost when idle.
