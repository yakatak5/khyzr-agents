# Deployment Guide

## Prerequisites
1. AWS account with Bedrock model access enabled for Claude Sonnet
2. Terraform >= 1.5.0
3. AWS CLI configured (`aws configure`)
4. Docker (for container builds)
5. Request model access: AWS Console → Bedrock → Model access → Enable Claude Sonnet

## Quick Deploy (All Agents)
```bash
cd infra
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

## Single Agent Deploy
```bash
cd agents/01-market-intelligence-agent/infra
terraform init
terraform apply -var="environment=prod"
```

## Environment Configuration
Set in `infra/terraform.tfvars` or as env vars:
- `aws_region` = your AWS region
- `environment` = prod / staging / dev
- `foundation_model` = model ID (default: anthropic.claude-sonnet-4-5-v1:0)

## Build & Push Container Images
```bash
# Build and push a single agent
AGENT_DIR="agents/01-market-intelligence-agent"
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"

docker build -t market-intelligence-agent $AGENT_DIR
docker tag market-intelligence-agent:latest \
  $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/market-intelligence-agent-prod:latest

aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com

docker push $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/market-intelligence-agent-prod:latest
```

## Testing After Deploy
```bash
# Invoke via AWS CLI
aws lambda invoke \
  --function-name market-intelligence-agent-prod \
  --payload '{"competitors":["OpenAI","Anthropic"]}' \
  --cli-binary-format raw-in-base64-out \
  response.json

cat response.json
```

## Testing Locally
```bash
./scripts/test-agent.sh agents/01-market-intelligence-agent \
  '{"message": "Analyze OpenAI and Anthropic competitive moves last week"}'
```

## Costs
- Lambda: Pay per invocation (~$0.20/1M requests + compute time)
- ECR: ~$0.10/GB/month storage
- Bedrock Claude Sonnet: ~$3/1M input tokens, $15/1M output tokens
- Estimate: ~$0.01-0.05 per agent invocation depending on complexity
- All 46 agents idle = ~$0/month (serverless — no fixed costs)
