terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------------------------------------------------------------
# Variables
# ---------------------------------------------------------------
variable "aws_region" {
  default     = "us-east-1"
  description = "AWS region to deploy into"
}

variable "environment" {
  default     = "demo"
  description = "Deployment environment label"
}

variable "foundation_model" {
  default     = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
  description = "Bedrock foundation model ID used by the agent"
}

variable "project_name" {
  default     = "khyzr"
  description = "Project prefix used in resource names"
}

variable "agent_zip_path" {
  default     = ""
  description = "Path to the agent zip file to upload (leave empty to skip code upload)"
}

locals {
  agent_name         = "${var.project_name}-seo-content-${var.environment}"
  agentcore_runtime  = "${var.project_name}_seo_content_${var.environment}"
  tags = {
    Project     = "khyzr-agents"
    Agent       = "seo-content"
    Environment = var.environment
  }
}

# ---------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------
data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------
# S3 Bucket — Agent code artifact (Code Zip deployment)
# ---------------------------------------------------------------
resource "aws_s3_bucket" "agent_code" {
  bucket        = "${local.agent_name}-code-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
  tags          = local.tags
}

resource "aws_s3_bucket_versioning" "agent_code" {
  bucket = aws_s3_bucket.agent_code.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "agent_code" {
  bucket = aws_s3_bucket.agent_code.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "agent_code" {
  bucket                  = aws_s3_bucket.agent_code.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Upload the agent zip if provided
resource "aws_s3_object" "agent_code" {
  count  = var.agent_zip_path != "" ? 1 : 0
  bucket = aws_s3_bucket.agent_code.id
  key    = "agent.zip"
  source = var.agent_zip_path
  etag   = filemd5(var.agent_zip_path)
  tags   = local.tags
}

# ---------------------------------------------------------------
# S3 Bucket — SEO content / posts storage
# ---------------------------------------------------------------
resource "aws_s3_bucket" "seo_content" {
  bucket        = "${local.agent_name}-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
  tags          = local.tags
}

resource "aws_s3_bucket_versioning" "seo_content" {
  bucket = aws_s3_bucket.seo_content.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "seo_content" {
  bucket = aws_s3_bucket.seo_content.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "seo_content" {
  bucket                  = aws_s3_bucket.seo_content.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Deny all non-HTTPS requests + cross-account access
resource "aws_s3_bucket_policy" "seo_content_policy" {
  bucket = aws_s3_bucket.seo_content.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyNonSSL"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.seo_content.arn,
          "${aws_s3_bucket.seo_content.arn}/*"
        ]
        Condition = {
          Bool = { "aws:SecureTransport" = "false" }
        }
      },
      {
        Sid       = "AllowAccountOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.seo_content.arn,
          "${aws_s3_bucket.seo_content.arn}/*"
        ]
        Condition = {
          StringNotEquals = {
            "aws:PrincipalAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
  depends_on = [aws_s3_bucket_public_access_block.seo_content]
}

# ---------------------------------------------------------------
# IAM Role — AgentCore Runtime
# ---------------------------------------------------------------
resource "aws_iam_role" "agentcore_role" {
  name = "khyzr-seo-content-${var.environment}-agentcore-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock-agentcore.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
      }
    }]
  })
  tags = local.tags
}

resource "aws_iam_role_policy" "agentcore_policy" {
  name = "khyzr-seo-content-${var.environment}-agentcore-policy"
  role = aws_iam_role.agentcore_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvokeAll"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/*",
          "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/*",
          "arn:aws:bedrock:*:*:inference-profile/*"
        ]
      },
      {
        Sid    = "CloudWatch"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "bedrock-agentcore"
          }
        }
      },
      {
        Sid    = "XRay"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
          "xray:GetSamplingRules",
          "xray:GetSamplingTargets"
        ]
        Resource = "*"
      },
      {
        Sid    = "WorkloadIdentity"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:GetWorkloadAccessToken",
          "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
          "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
        ]
        Resource = "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default"
      },
      {
        Sid    = "S3ContentBucket"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Resource = [
          aws_s3_bucket.seo_content.arn,
          "${aws_s3_bucket.seo_content.arn}/*"
        ]
      },
      {
        Sid    = "AgentCodeBucket"
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = "arn:aws:s3:::${aws_s3_bucket.agent_code.bucket}/agent.zip"
      }
    ]
  })
}

# ---------------------------------------------------------------
# AgentCore Runtime — deployed via AWS CLI (null_resource)
# AgentCore runtimes are not natively supported by any Terraform
# provider; we use the AWS CLI via local-exec provisioner.
# ---------------------------------------------------------------
resource "null_resource" "agentcore_runtime" {
  # Re-run whenever the role ARN or code bucket changes
  triggers = {
    role_arn     = aws_iam_role.agentcore_role.arn
    code_bucket  = aws_s3_bucket.agent_code.bucket
    runtime_name = local.agentcore_runtime
  }

  provisioner "local-exec" {
    command = <<-EOF
      set -e

      RUNTIME_NAME="${local.agentcore_runtime}"
      ROLE_ARN="${aws_iam_role.agentcore_role.arn}"
      CODE_BUCKET="${aws_s3_bucket.agent_code.bucket}"
      REGION="${var.aws_region}"

      ARTIFACT=$(cat <<ENDJSON
      {"s3": {"s3Uri": "s3://$CODE_BUCKET/agent.zip"}}
      ENDJSON
      )

      NETWORK_CONFIG='{"networkMode": "PUBLIC"}'

      # Check if runtime already exists
      EXISTING=$(aws bedrock-agentcore get-agent-runtime \
        --agent-runtime-id "$RUNTIME_NAME" \
        --region "$REGION" \
        --query 'agentRuntimeId' \
        --output text 2>/dev/null || echo "NOT_FOUND")

      if [ "$EXISTING" = "NOT_FOUND" ]; then
        echo "Creating AgentCore runtime: $RUNTIME_NAME"
        aws bedrock-agentcore create-agent-runtime \
          --agent-runtime-name "$RUNTIME_NAME" \
          --agent-runtime-artifact "$ARTIFACT" \
          --role-arn "$ROLE_ARN" \
          --network-configuration "$NETWORK_CONFIG" \
          --region "$REGION"
      else
        echo "Updating AgentCore runtime: $RUNTIME_NAME"
        aws bedrock-agentcore update-agent-runtime \
          --agent-runtime-id "$RUNTIME_NAME" \
          --agent-runtime-artifact "$ARTIFACT" \
          --role-arn "$ROLE_ARN" \
          --network-configuration "$NETWORK_CONFIG" \
          --region "$REGION"
      fi

      echo "AgentCore runtime deployment complete: $RUNTIME_NAME"
    EOF
  }

  depends_on = [
    aws_iam_role_policy.agentcore_policy,
    aws_s3_bucket.agent_code
  ]
}

# ---------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------
output "agentcore_runtime_name" {
  value       = local.agentcore_runtime
  description = "AgentCore Runtime name"
}

output "agent_code_bucket" {
  value       = aws_s3_bucket.agent_code.bucket
  description = "S3 bucket storing the agent code zip artifact"
}

output "seo_content_bucket" {
  value       = aws_s3_bucket.seo_content.bucket
  description = "S3 bucket for SEO content and posts"
}

output "agentcore_role_arn" {
  value       = aws_iam_role.agentcore_role.arn
  description = "IAM role ARN for the AgentCore runtime"
}
