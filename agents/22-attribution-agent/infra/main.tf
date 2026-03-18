terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = var.aws_region
}}

variable "agent_name" {{
  description = "Name of the Bedrock agent"
}}

variable "agent_description" {{
  description = "Description of the agent"
}}

variable "aws_region" {{
  default = "us-east-1"
}}

variable "foundation_model" {{
  default = "anthropic.claude-sonnet-4-5-v1:0"
}}

# IAM Role for Bedrock Agent
resource "aws_iam_role" "bedrock_agent_role" {{
  name = "${{var.agent_name}}-bedrock-role"
  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = {{ Service = "bedrock.amazonaws.com" }}
    }}]
  }})
}}

resource "aws_iam_role_policy" "bedrock_agent_policy" {{
  name = "${{var.agent_name}}-policy"
  role = aws_iam_role.bedrock_agent_role.id
  policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = "*"
    }}]
  }})
}}

# Bedrock Agent
resource "aws_bedrockagent_agent" "agent" {{
  agent_name                  = var.agent_name
  description                 = var.agent_description
  foundation_model            = var.foundation_model
  agent_resource_role_arn     = aws_iam_role.bedrock_agent_role.arn
  idle_session_ttl_in_seconds = 600
}}

# Agent Alias
resource "aws_bedrockagent_agent_alias" "agent_alias" {{
  agent_id         = aws_bedrockagent_agent.agent.agent_id
  agent_alias_name = "live"
}}

output "agent_id" {{
  value = aws_bedrockagent_agent.agent.agent_id
}}

output "agent_alias" {{
  value = aws_bedrockagent_agent.agent_alias.agent_alias_id
}}
