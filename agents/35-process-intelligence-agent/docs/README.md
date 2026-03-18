# Process Intelligence Agent

**Category:** Operations  
**Status:** Production-ready  
**Framework:** AWS Strands Agents SDK + Amazon Bedrock (Claude Sonnet)

## Overview

Analyzes operational workflow data to identify throughput bottlenecks and recommend corrective actions

## Architecture

```
35-process-intelligence-agent/
├── src/
│   └── agent.py          # Strands agent implementation
├── Dockerfile             # Container definition
├── requirements.txt       # Python dependencies
├── infra/
│   ├── main.tf           # Terraform (Bedrock AgentCore)
│   └── terraform.tfvars  # Agent-specific variables
└── docs/
    └── README.md         # This file
```

## Quick Start

### Local Development

```bash
cd agents/35-process-intelligence-agent
pip install -r requirements.txt
echo '{"message": "Run default task"}' | python src/agent.py
```

### Docker

```bash
docker build -t 35-process-intelligence-agent .
docker run -e AWS_REGION=us-east-1 \
           -e BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5 \
           35-process-intelligence-agent
```

### Deploy to AWS

```bash
cd infra
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AWS_REGION` | No | AWS region (default: us-east-1) |
| `BEDROCK_MODEL_ID` | No | Bedrock model ID (default: us.anthropic.claude-sonnet-4-5) |
| `AWS_ACCESS_KEY_ID` | Yes* | AWS credentials (*or use IAM role) |
| `AWS_SECRET_ACCESS_KEY` | Yes* | AWS credentials (*or use IAM role) |

## Input Format

```json
{
  "message": "Your instruction to the agent"
}
```

## Output Format

```json
{
  "result": "Agent response and actions taken"
}
```

## Example Usage

```bash
echo '{"message": "Run a comprehensive analysis and generate a report"}' | python src/agent.py
```

## AWS Resources Created

- `aws_bedrockagent_agent` — Bedrock Agent resource
- `aws_bedrockagent_agent_alias` — Live deployment alias
- `aws_iam_role` — Execution role with Bedrock permissions
- `aws_iam_role_policy` — Minimum required permissions

## Related Agents

See the [main repository README](../../README.md) for the full list of 46 agents.
