# infra/modules/agentcore-runtime/main.tf
# Reusable Terraform module for deploying a Strands agent to AgentCore Runtime.
#
# Usage example:
#   module "my_agent" {
#     source           = "../../infra/modules/agentcore-runtime"
#     agent_name       = "my-agent"
#     agent_description = "Does cool things"
#     image_uri        = "${aws_ecr_repository.my_agent.repository_url}:latest"
#     environment_vars = {
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
  }
}

data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------
# ECR Repository
# ---------------------------------------------------------------
resource "aws_ecr_repository" "agent" {
  name                 = "khyzr/${var.agent_name}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Agent       = var.agent_name
    Environment = var.environment
    ManagedBy   = "agentcore-runtime-module"
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
          Sid    = "ECRAccess"
          Effect = "Allow"
          Action = [
            "ecr:GetAuthorizationToken",
            "ecr:BatchGetImage",
            "ecr:GetDownloadUrlForLayer"
          ]
          # ecr:GetAuthorizationToken requires Resource: "*" by AWS design
          Resource = "*"
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
        }
      ],
      var.extra_iam_statements
    )
  })
}

# ---------------------------------------------------------------
# AgentCore Runtime
# ---------------------------------------------------------------
resource "awscc_bedrockagentcore_runtime" "agent" {
  agent_runtime_name = "${var.agent_name}-${var.environment}"
  description        = var.agent_description
  role_arn           = aws_iam_role.agentcore_role.arn

  agent_runtime_artifact = {
    container_configuration = {
      container_uri = var.image_uri
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
}
