# infra/modules/agentcore-runtime/main.tf
# Reusable Terraform module for deploying a Strands agent to AgentCore Runtime
# using Code Zip (Direct Code Deployment) — no Docker, no ECR required.
#
# Usage example:
#   module "my_agent" {
#     source            = "../../infra/modules/agentcore-runtime"
#     agent_name        = "my-agent"
#     agent_description = "Does cool things"
#     agent_py_path     = "${path.module}/../src/agent.py"
#     requirements_path = "${path.module}/../requirements.txt"
#     environment_vars  = {
#       MY_TABLE = aws_dynamodb_table.my_table.name
#     }
#     extra_iam_statements = [
#       {
#         Sid      = "DynamoDB"
#         Effect   = "Allow"
#         Action   = ["dynamodb:PutItem", "dynamodb:GetItem"]
#         Resource = aws_dynamodb_table.my_table.arn
#       }
#     ]
#   }

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    awscc = {
      source  = "hashicorp/awscc"
      version = "~> 1.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------
# S3 Bucket — Agent code artifact
# ---------------------------------------------------------------
resource "aws_s3_bucket" "agent_code" {
  bucket        = "${var.agent_name}-${var.environment}-code-${data.aws_caller_identity.current.account_id}"
  force_destroy = true

  tags = {
    Agent       = var.agent_name
    Environment = var.environment
    ManagedBy   = "agentcore-runtime-module"
  }
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

# ---------------------------------------------------------------
# Code Zip — package agent.py + requirements.txt
# ---------------------------------------------------------------
data "archive_file" "agent_zip" {
  type        = "zip"
  output_path = "${path.module}/agent-${var.agent_name}.zip"
  source {
    content  = file(var.agent_py_path)
    filename = "agent.py"
  }
  source {
    content  = file(var.requirements_path)
    filename = "requirements.txt"
  }
}

resource "aws_s3_object" "agent_code" {
  bucket      = aws_s3_bucket.agent_code.id
  key         = "agent.zip"
  source      = data.archive_file.agent_zip.output_path
  source_hash = data.archive_file.agent_zip.output_base64sha256

  tags = {
    Agent       = var.agent_name
    Environment = var.environment
  }
}

# ---------------------------------------------------------------
# IAM Role — AgentCore Runtime trust policy
# ---------------------------------------------------------------
resource "aws_iam_role" "agentcore_role" {
  name = "${var.agent_name}-${var.environment}-agentcore-role"

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

  tags = {
    Agent       = var.agent_name
    Environment = var.environment
  }
}

# ---------------------------------------------------------------
# IAM Policy — base AgentCore permissions + agent-specific extras
# ---------------------------------------------------------------
resource "aws_iam_role_policy" "agentcore_base_policy" {
  name = "${var.agent_name}-${var.environment}-base-policy"
  role = aws_iam_role.agentcore_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid    = "BedrockModel"
          Effect = "Allow"
          Action = [
            "bedrock:InvokeModel",
            "bedrock:InvokeModelWithResponseStream"
          ]
          # Scoped to the specific foundation model — not wildcard
          Resource = "arn:aws:bedrock:*::foundation-model/*"
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
            "bedrock-agentcore:GetWorkloadAccessTokenForJWT"
          ]
          Resource = "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default"
        },
        {
          Sid    = "AgentCodeBucket"
          Effect = "Allow"
          Action = ["s3:GetObject"]
          Resource = "arn:aws:s3:::${aws_s3_bucket.agent_code.bucket}/agent.zip"
        }
      ],
      var.extra_iam_statements
    )
  })
}

# ---------------------------------------------------------------
# AgentCore Runtime — Code Zip (Direct Code Deployment)
# ---------------------------------------------------------------
resource "awscc_bedrockagentcore_runtime" "agent" {
  agent_runtime_name = "${var.agent_name}-${var.environment}"
  description        = var.agent_description
  role_arn           = aws_iam_role.agentcore_role.arn

  agent_runtime_artifact = {
    code_artifact = {
      s3_location = {
        uri = "s3://${aws_s3_bucket.agent_code.bucket}/agent.zip"
      }
    }
  }

  network_configuration = {
    network_mode = "PUBLIC"
  }

  environment_variables = merge(
    {
      AWS_REGION_NAME = var.aws_region
      ENVIRONMENT     = var.environment
    },
    var.environment_vars
  )

  depends_on = [aws_s3_object.agent_code]
}
