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
  default     = "anthropic.claude-sonnet-4-5-v1:0"
}

variable "project_name" {
  description = "Project name prefix for all resources"
  type        = string
  default     = "khyzr"
}
