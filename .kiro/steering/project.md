# Khyzr Agents — Project Steering

## Overview
46 production AI agents built on AWS Strands Agents SDK and Amazon Bedrock AgentCore.
Covers 5 domains: Executive Strategy, Sales & Marketing, Operations, Finance & Accounting, Healthcare.

## Technology Stack
- **Agent Framework:** AWS Strands Agents SDK (`strands-agents`)
- **LLM:** Amazon Bedrock — Claude Sonnet (`us.anthropic.claude-sonnet-4-5`)
- **Infrastructure:** Terraform + AWS Lambda + ECR (Bedrock AgentCore-compatible)
- **Containers:** Docker (Python 3.11-slim), deployable to ECR + Lambda
- **Region:** us-east-1 (default)

## Agent Domains
| Range | Domain | Count |
|-------|--------|-------|
| 01–11 | Executive Strategy | 11 |
| 12–23 | Sales & Marketing | 12 |
| 24–35 | Operations | 12 |
| 36–41 | Finance & Accounting | 6 |
| 42–46 | Healthcare | 5 |

## Development Conventions
- Agent directories: `agents/XX-kebab-case-name/`
- Entry point: `src/agent.py` with `run(input_data: dict) -> dict`
- Tools use `@tool` decorator from strands
- All agents use `BedrockModel` with env-var overridable model ID
- Terraform per-agent in `agents/XX/infra/main.tf`
- System prompts: 200-400 words, role-specific, Khyzr-branded

## Environment Variables (all agents)
- `BEDROCK_MODEL_ID` — Model override (default: `us.anthropic.claude-sonnet-4-5`)
- `AWS_REGION` — AWS region (default: `us-east-1`)
- Agent-specific vars documented in each `docs/README.md`

## Key Commands
```bash
# Deploy all agents
./scripts/deploy-all.sh

# Deploy single agent
./scripts/deploy-agent.sh agents/01-market-intelligence-agent

# Test an agent locally
./scripts/test-agent.sh agents/01-market-intelligence-agent '{"message": "Analyze Tesla Q4 2025"}'

# Terraform (all agents)
cd infra && terraform init && terraform plan && terraform apply
```
