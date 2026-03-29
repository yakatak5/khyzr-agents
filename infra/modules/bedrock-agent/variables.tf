variable "agent_name" {
  description = "Name of the Bedrock agent"
  type        = string
}

variable "agent_description" {
  description = "Description of the agent's purpose"
  type        = string
}

variable "instruction" {
  description = "System prompt / instruction for the agent"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "foundation_model" {
  description = "Foundation model ID for the agent"
  type        = string
  default     = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "prod"
}
