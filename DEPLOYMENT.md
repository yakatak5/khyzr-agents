# Khyzr Agents — Deployment Guide

Complete step-by-step instructions for deploying all 46 Khyzr AI agents to AWS.

---

## 1. AWS Account Setup & Bedrock Model Access

### 1.1 Enable Bedrock Model Access

Before deploying, you must request access to Claude Sonnet in Amazon Bedrock:

1. Log in to the [AWS Console](https://console.aws.amazon.com)
2. Navigate to **Amazon Bedrock** → **Model access** (left sidebar)
3. Click **Modify model access**
4. Select **Anthropic Claude Sonnet** (and optionally Claude Haiku for cost optimization)
5. Submit the access request — approval is typically instant or within a few minutes
6. Verify status shows **Access granted**

### 1.2 Verify AWS CLI Access

```bash
# Verify CLI is configured
aws sts get-caller-identity

# Expected output:
# {
#     "UserId": "AIDAEXAMPLE...",
#     "Account": "123456789012",
#     "Arn": "arn:aws:iam::123456789012:user/your-username"
# }
```

---

## 2. IAM Permissions Required

The deploying IAM user/role needs the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:*",
        "ecr:*",
        "iam:CreateRole",
        "iam:PutRolePolicy",
        "iam:AttachRolePolicy",
        "iam:PassRole",
        "iam:GetRole",
        "iam:DeleteRole",
        "iam:DeleteRolePolicy",
        "s3:*",
        "logs:*",
        "events:*",
        "ssm:PutParameter",
        "ssm:GetParameter",
        "bedrock:InvokeModel"
      ],
      "Resource": "*"
    }
  ]
}
```

You can attach the managed `PowerUserAccess` policy for initial deployment (tighten for production).

---

## 3. Terraform Setup

### 3.1 Install Terraform

```bash
# macOS (Homebrew)
brew install terraform

# Linux
wget https://releases.hashicorp.com/terraform/1.7.0/terraform_1.7.0_linux_amd64.zip
unzip terraform_1.7.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/

# Verify
terraform --version
# Terraform v1.7.0 or later
```

### 3.2 (Optional) Configure Remote State

For team deployments, configure S3 backend in `infra/main.tf`:

```hcl
backend "s3" {
  bucket = "your-terraform-state-bucket"
  key    = "khyzr-agents/terraform.tfstate"
  region = "us-east-1"
}
```

Create the S3 bucket first:
```bash
aws s3 mb s3://your-terraform-state-bucket --region us-east-1
aws s3api put-bucket-versioning \
  --bucket your-terraform-state-bucket \
  --versioning-configuration Status=Enabled
```

---

## 4. Environment Configuration

### 4.1 Create tfvars File

Create `infra/terraform.tfvars`:

```hcl
aws_region       = "us-east-1"
environment      = "prod"
foundation_model = "anthropic.claude-sonnet-4-5-v1:0"
project_name     = "khyzr"
```

### 4.2 Agent-Specific Configuration

Each agent has its own `infra/terraform.tfvars` for agent-specific settings (API keys, recipients, etc.). Review and populate before deploying:

```bash
# Example: Market Intelligence Agent
cat agents/01-market-intelligence-agent/infra/terraform.tfvars

# Update with your values
vim agents/01-market-intelligence-agent/infra/terraform.tfvars
```

---

## 5. Deploy All Agents

### Option A: Deploy Script (Recommended)

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Deploy all 46 agents
./scripts/deploy-all.sh
```

### Option B: Manual Terraform

```bash
cd infra
terraform init -upgrade
terraform plan -out=tfplan
terraform apply tfplan
```

Expected output: ~46 Lambda functions, ~46 ECR repositories, IAM roles, CloudWatch log groups, and EventBridge rules created.

**⏱️ Estimated time:** 15-25 minutes for initial deploy of all 46 agents.

---

## 6. Deploy Individual Agents

Deploy a single agent without affecting others:

```bash
# Via deploy script
./scripts/deploy-agent.sh agents/36-ap-automation-agent

# Via Terraform directly
cd agents/36-ap-automation-agent/infra
terraform init
terraform apply -var="environment=prod"
```

---

## 7. Build & Push Container Images

After Terraform creates ECR repositories, build and push Docker images:

```bash
# Set variables
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"
ENVIRONMENT="prod"

# Login to ECR
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com

# Build and push a single agent
AGENT="market-intelligence-agent"
docker build -t $AGENT agents/01-market-intelligence-agent/
docker tag $AGENT:latest \
  $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$AGENT-$ENVIRONMENT:latest
docker push \
  $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$AGENT-$ENVIRONMENT:latest
```

---

## 8. Testing Agents

### 8.1 Test via AWS CLI

```bash
# Invoke a Lambda agent
aws lambda invoke \
  --function-name market-intelligence-agent-prod \
  --payload '{"competitors":["OpenAI","Anthropic"],"topic":"product launches"}' \
  --cli-binary-format raw-in-base64-out \
  response.json

# Check the response
cat response.json | python3 -m json.tool
```

### 8.2 Test via Python SDK

```python
import boto3
import json

client = boto3.client('lambda', region_name='us-east-1')

response = client.invoke(
    FunctionName='ap-automation-agent-prod',
    InvocationType='RequestResponse',
    Payload=json.dumps({
        "message": "Process invoice INV-2024-08821 from s3://my-bucket/invoices/"
    })
)

result = json.loads(response['Payload'].read())
print(result)
```

### 8.3 Test Locally

```bash
# Using the test script
./scripts/test-agent.sh agents/36-ap-automation-agent \
  '{"message": "Process invoice INV-2024-001 and match against PO-2024-005"}'

# Direct Python execution
echo '{"message": "Generate 13-week cash flow forecast"}' | \
  python agents/41-cash-flow-agent/src/agent.py
```

---

## 9. Monitoring & Logging

### 9.1 CloudWatch Logs

Each agent writes to `/aws/lambda/{agent-name}-{environment}`:

```bash
# View recent logs for AP Automation Agent
aws logs tail /aws/lambda/ap-automation-agent-prod --follow

# Search for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/ap-automation-agent-prod \
  --filter-pattern "ERROR"
```

### 9.2 CloudWatch Metrics

Key metrics to monitor per agent:
- `Invocations` — Total calls
- `Errors` — Failed invocations
- `Duration` — P50/P95/P99 latency
- `Throttles` — Concurrency limit hits

Create a CloudWatch Dashboard:
```bash
# Example: monitor all agents
aws cloudwatch put-dashboard \
  --dashboard-name KhyzrAgents \
  --dashboard-body file://monitoring/dashboard.json
```

### 9.3 Set Up Alerts

```bash
# Alert on agent errors
aws cloudwatch put-metric-alarm \
  --alarm-name "AP-Agent-Errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --dimensions Name=FunctionName,Value=ap-automation-agent-prod \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT:khyzr-alerts
```

---

## 10. Cost Estimation

### Per-Agent Monthly Costs (Estimated)

| Component | Cost Model | Estimate (1K invocations/month) |
|-----------|------------|----------------------------------|
| Lambda | $0.20/1M req + $0.0000166667/GB-sec | ~$0.20-$1.00 |
| ECR | $0.10/GB/month | ~$0.05 |
| Bedrock (Claude Sonnet) | $3/1M input, $15/1M output tokens | ~$1.50-$7.50 |
| CloudWatch Logs | $0.50/GB ingested | ~$0.10 |
| **Total per agent** | | **~$2-10/month** |

### Full Platform (All 46 Agents)

| Usage Level | Monthly Estimate |
|-------------|-----------------|
| Low (100 invocations/agent) | ~$50-100 |
| Medium (1,000 invocations/agent) | ~$100-500 |
| High (10,000 invocations/agent) | ~$1,000-5,000 |

**Zero idle cost** — Lambda is fully serverless; you pay only for invocations.

---

## 11. Troubleshooting

### Common Issues

#### ❌ "Bedrock model not found"
```
Error: Could not find model: us.anthropic.claude-sonnet-4-5
```
**Fix:** Enable model access in the Bedrock console for your region. Check `BEDROCK_MODEL_ID` env var.

#### ❌ "Lambda timeout"
```
Error: Task timed out after 300 seconds
```
**Fix:** Increase Lambda timeout in `infra/main.tf` (`timeout = 600`). Complex agents may need up to 10 minutes.

#### ❌ "ECR image not found"
```
Error: CannotPullContainerError: image not found
```
**Fix:** Build and push the Docker image to ECR before invoking. See Section 7.

#### ❌ "Access denied to Bedrock"
```
Error: AccessDeniedException calling InvokeModel
```
**Fix:** Verify Lambda IAM role has `bedrock:InvokeModel` permission and model access is granted.

#### ❌ "Terraform state lock"
```
Error: Error acquiring the state lock
```
**Fix:** Run `terraform force-unlock <lock-id>` or delete the lock from the S3 state bucket.

#### ❌ "S3 bucket already exists"
```
Error: BucketAlreadyOwnedByYou
```
**Fix:** Bucket names are globally unique. Update the bucket name in the agent's `infra/main.tf`.

### Debug Mode

Enable verbose Strands logging:
```bash
STRANDS_LOG_LEVEL=DEBUG python src/agent.py
```

### Getting Help

- [AWS Strands Agents Documentation](https://github.com/aws/strands-agents)
- [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- Open an issue in this repository

---

## 12. Updating Agents

### Update a Single Agent

```bash
# Update code
git pull origin main

# Rebuild and push new container
./scripts/deploy-agent.sh agents/36-ap-automation-agent

# Update Lambda to use new image
cd agents/36-ap-automation-agent/infra
terraform apply -refresh-only
```

### Update All Agents

```bash
git pull origin main
./scripts/deploy-all.sh
```

---

*For questions, open an issue or contact the Khyzr engineering team.*
