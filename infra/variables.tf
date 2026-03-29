variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "prod"
}

variable "foundation_model" {
  description = "Bedrock foundation model ID"
  type        = string
  default     = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
}

variable "project_name" {
  description = "Project name prefix for all resources"
  type        = string
  default     = "khyzr"
}
