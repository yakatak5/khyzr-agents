# infra/modules/agentcore-runtime/variables.tf

variable "agent_name" {
  description = "Short name for the agent (used in resource names). Example: ap-automation"
  type        = string
}

variable "agent_description" {
  description = "Human-readable description of what the agent does"
  type        = string
}

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment label (demo, staging, prod)"
  type        = string
  default     = "prod"
}

variable "foundation_model" {
  description = "Bedrock foundation model ID for the agent to use"
  type        = string
  default     = "anthropic.claude-sonnet-4-5-v1:0"
}

variable "agent_py_path" {
  description = "Absolute or relative path to the agent's agent.py source file. Example: ${path.module}/../src/agent.py"
  type        = string
}

variable "requirements_path" {
  description = "Absolute or relative path to the agent's requirements.txt file. Example: ${path.module}/../requirements.txt"
  type        = string
}

variable "environment_vars" {
  description = "Additional environment variables to inject into the AgentCore Runtime"
  type        = map(string)
  default     = {}
}

variable "extra_iam_statements" {
  description = "Additional IAM policy statements to attach to the AgentCore role. Use for agent-specific permissions (DynamoDB, S3, SES, etc.)"
  type        = list(any)
  default     = []
}
