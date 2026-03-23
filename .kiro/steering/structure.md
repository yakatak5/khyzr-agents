# Repository Structure

## Per-Agent Layout
```
agents/XX-agent-name/
├── src/
│   ├── agent.py          # Strands implementation + lambda_handler for Action Groups
│   └── openapi.json      # OpenAPI schema (present on demo-ready agents ⭐)
├── Dockerfile            # Python 3.11-slim container
├── requirements.txt      # strands-agents, boto3, agent-specific deps
├── infra/
│   ├── main.tf           # Full Terraform: Bedrock Agent + Lambda + IAM + (DynamoDB + S3 for ⭐)
│   └── terraform.tfvars  # Agent-specific var values
└── docs/
    ├── README.md         # What it does, inputs/outputs, env vars, examples
    └── DEMO.md           # Step-by-step demo guide (present on ⭐ agents)
```

## src/agent.py Structure (every agent)

```python
"""Agent Name — description"""
import json, os, boto3
from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel

@tool
def tool_name(param: str) -> str:
    """Tool description"""
    return json.dumps(result)

# 3-5 tools total

SYSTEM_PROMPT = """..."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(model=model, tools=[...], system_prompt=SYSTEM_PROMPT)

# ── Bedrock Action Group entry point ──────────────────────────────
def lambda_handler(event, context):
    """Routes Bedrock Action Group invocations to the correct tool."""
    api_path   = event.get("apiPath", "")
    parameters = {p["name"]: p["value"] for p in event.get("parameters", [])}
    # + parse requestBody properties into parameters
    result = route_to_tool(api_path, parameters)
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", ""),
            "apiPath": api_path,
            "httpMethod": event.get("httpMethod", "POST"),
            "httpStatusCode": 200,
            "responseBody": {"application/json": {"body": result}}
        }
    }

# ── Local / AgentCore entry point ─────────────────────────────────
def run(input_data: dict) -> dict:
    response = agent(input_data.get("message", "Run default task"))
    return {"result": str(response)}

if __name__ == "__main__":
    import sys
    data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {"message": "..."}
    print(json.dumps(run(data)))
```

## Shared Infrastructure
```
infra/
├── main.tf               # Root — calls all 46 agent modules
├── variables.tf          # Shared: aws_region, environment, foundation_model
├── outputs.tf            # All agent IDs and alias IDs
└── modules/
    └── bedrock-agent/    # Reusable module for basic agents (no Lambda)
        ├── main.tf       # IAM role (with SourceAccount condition) + Bedrock Agent + Alias
        ├── variables.tf
        └── outputs.tf
```

## Demo-Ready Agent Terraform Structure (⭐ agents)

Full `infra/main.tf` deploys all of these in one `terraform apply`:

```
aws_s3_bucket                         — invoice/data storage (encrypted, HTTPS-only, account-private)
aws_s3_bucket_public_access_block     — all public access blocked
aws_s3_bucket_server_side_encryption  — AES256 at rest
aws_s3_bucket_policy                  — deny non-SSL + deny cross-account
aws_s3_object (demo data)             — pre-loaded test data

aws_dynamodb_table                    — results/ledger storage (encrypted, PITR enabled)

aws_iam_role (lambda)                 — Lambda execution role
aws_iam_role_policy (lambda)          — least-privilege: scoped ARNs only, no wildcards

aws_lambda_function                   — action group tool executor
aws_cloudwatch_log_group              — Lambda logs, 30-day retention
aws_lambda_permission                 — allow Bedrock to invoke, scoped to this account

aws_s3_bucket (schema)                — OpenAPI schema bucket (encrypted, account-private)
aws_s3_object (openapi.json)          — tool schema Bedrock reads

aws_iam_role (bedrock agent)          — Bedrock execution role
aws_iam_role_policy (bedrock agent)   — least-privilege: model + lambda + s3 + logs

aws_bedrockagent_agent                — the agent with instruction
aws_bedrockagent_agent_action_group   — wires Lambda tools via OpenAPI schema
aws_bedrockagent_agent_alias          — "live" alias for stable invocation endpoint
```

## Scripts
```
scripts/
├── deploy-all.sh         — terraform init + plan + apply on infra/
├── deploy-agent.sh       — terraform init + apply on a single agent's infra/
└── test-agent.sh         — runs agent.py locally with JSON input
```

## IAM Security Patterns (enforced everywhere)

### Trust Policy (Bedrock roles)
```json
{
  "Condition": {
    "StringEquals": { "aws:SourceAccount": "<account-id>" },
    "ArnLike": { "aws:SourceArn": "arn:aws:bedrock:<region>:<account>:agent/*" }
  }
}
```

### Policy Resources (no wildcards)
```hcl
# ❌ Never
Resource = "*"
Resource = "arn:aws:logs:*:*:*"

# ✅ Always
Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.foundation_model}"
Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.function_name}:*"
Resource = aws_dynamodb_table.specific_table.arn
```
