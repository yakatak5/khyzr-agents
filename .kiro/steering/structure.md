# Repository Structure

## Per-Agent Layout
```
agents/XX-agent-name/
├── src/agent.py          # Strands implementation — entry point is run(input_data)
├── Dockerfile            # Python 3.11-slim container
├── requirements.txt      # strands-agents, boto3, agent-specific deps
├── infra/
│   ├── main.tf           # Lambda + ECR + IAM + EventBridge
│   └── terraform.tfvars  # Agent-specific var values
└── docs/
    └── README.md         # What it does, inputs/outputs, env vars, examples
```

## Shared Infrastructure
```
infra/
├── main.tf               # Root — calls all 46 agent modules
├── variables.tf          # Shared: aws_region, environment, foundation_model
├── outputs.tf            # All agent Lambda ARNs and ECR URLs
└── modules/
    └── bedrock-agent/    # Reusable Bedrock AgentCore Terraform module
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

## Scripts
```
scripts/
├── deploy-all.sh         # Deploy all 46 agents via Terraform
├── deploy-agent.sh       # Deploy single agent
└── test-agent.sh         # Run agent locally with test input
```

## Key File Patterns

### src/agent.py
Every agent follows this structure:
1. Module docstring (name + description)
2. Imports (json, os, boto3, datetime, strands)
3. `@tool` decorated functions (3-5 tools)
4. `SYSTEM_PROMPT` constant (200-400 words)
5. `model = BedrockModel(...)` instance
6. `agent = Agent(model, tools, system_prompt)` instance
7. `run(input_data: dict) -> dict` entry point
8. `if __name__ == "__main__":` local runner

### Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ .
CMD ["python", "agent.py"]
```
