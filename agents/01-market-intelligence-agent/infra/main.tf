terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# -----------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "news_api_key" {
  description = "NewsAPI.org API key for news search"
  type        = string
  sensitive   = true
  default     = ""
}

variable "bedrock_model_id" {
  description = "Bedrock model ID to use"
  type        = string
  default     = "anthropic.claude-sonnet-4-5"
}

variable "schedule_expression" {
  description = "EventBridge schedule for automated runs (cron or rate expression)"
  type        = string
  default     = "rate(1 day)"
}

variable "default_competitors" {
  description = "JSON array of competitor names for scheduled runs"
  type        = string
  default     = "[\"Competitor A\", \"Competitor B\"]"
}

variable "briefing_recipients" {
  description = "Comma-separated list of email addresses to receive daily briefings"
  type        = string
  default     = ""
  # Example: "ceo@company.com,cto@company.com,strategy@company.com"
}

variable "ses_sender_email" {
  description = "Verified SES sender email address (must be verified in SES console)"
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------
# S3 bucket for intelligence reports
# -----------------------------------------------------------------------

resource "aws_s3_bucket" "reports" {
  bucket = "market-intelligence-reports-${var.environment}-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name        = "Market Intelligence Reports"
    Environment = var.environment
    Agent       = "market-intelligence-agent"
  }
}

resource "aws_s3_bucket_versioning" "reports" {
  bucket = aws_s3_bucket.reports.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id

  rule {
    id     = "archive-old-reports"
    status = "Enabled"

    filter {
      prefix = "reports/"
    }

    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# -----------------------------------------------------------------------
# IAM role for Lambda
# -----------------------------------------------------------------------

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "agent_lambda" {
  name = "market-intelligence-agent-lambda-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "agent_lambda" {
  name = "market-intelligence-agent-policy"
  role = aws_iam_role.agent_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # CloudWatch Logs
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        # Bedrock model invocation
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}"
      },
      {
        # S3 reports bucket
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.reports.arn,
          "${aws_s3_bucket.reports.arn}/*"
        ]
      },
      {
        # SSM Parameter Store (for API keys)
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ]
        Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/market-intelligence-agent/*"
      },
      {
        # SES — send briefing emails
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "ses:FromAddress" = var.ses_sender_email != "" ? var.ses_sender_email : "*"
          }
        }
      }
    ]
  })
}

# -----------------------------------------------------------------------
# ECR repository for container image
# -----------------------------------------------------------------------

resource "aws_ecr_repository" "agent" {
  name                 = "market-intelligence-agent-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Environment = var.environment
    Agent       = "market-intelligence-agent"
  }
}

resource "aws_ecr_lifecycle_policy" "agent" {
  repository = aws_ecr_repository.agent.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 5 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# -----------------------------------------------------------------------
# SSM Parameter for NewsAPI key
# -----------------------------------------------------------------------

resource "aws_ssm_parameter" "news_api_key" {
  count = var.news_api_key != "" ? 1 : 0

  name        = "/market-intelligence-agent/NEWS_API_KEY"
  type        = "SecureString"
  value       = var.news_api_key
  description = "NewsAPI.org API key for Market Intelligence Agent"

  tags = {
    Environment = var.environment
    Agent       = "market-intelligence-agent"
  }
}

# -----------------------------------------------------------------------
# Lambda function
# -----------------------------------------------------------------------

resource "aws_lambda_function" "agent" {
  function_name = "market-intelligence-agent-${var.environment}"
  role          = aws_iam_role.agent_lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.agent.repository_url}:latest"
  timeout       = 300   # 5 minutes — agent may make multiple tool calls
  memory_size   = 1024

  environment {
    variables = {
      INTELLIGENCE_BUCKET  = aws_s3_bucket.reports.bucket
      BEDROCK_MODEL_ID     = var.bedrock_model_id
      AWS_REGION_NAME      = var.aws_region
      ENVIRONMENT          = var.environment
      BRIEFING_RECIPIENTS  = var.briefing_recipients
      SES_SENDER_EMAIL     = var.ses_sender_email
      # NEWS_API_KEY is loaded from SSM at runtime by the agent
    }
  }

  tags = {
    Name        = "Market Intelligence Agent"
    Environment = var.environment
    Agent       = "market-intelligence-agent"
  }

  depends_on = [aws_ecr_repository.agent]

  lifecycle {
    ignore_changes = [image_uri]  # Managed by CI/CD pipeline
  }
}

resource "aws_cloudwatch_log_group" "agent" {
  name              = "/aws/lambda/${aws_lambda_function.agent.function_name}"
  retention_in_days = 30
}

# -----------------------------------------------------------------------
# EventBridge scheduled trigger (daily automated run)
# -----------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "daily_run" {
  name                = "market-intelligence-agent-daily-${var.environment}"
  description         = "Trigger Market Intelligence Agent on a schedule"
  schedule_expression = var.schedule_expression

  tags = {
    Environment = var.environment
  }
}

resource "aws_cloudwatch_event_target" "daily_run" {
  rule      = aws_cloudwatch_event_rule.daily_run.name
  target_id = "MarketIntelligenceAgentLambda"
  arn       = aws_lambda_function.agent.arn

  input = jsonencode({
    competitors = jsondecode(var.default_competitors)
    topic       = "recent strategy, product launches, partnerships, and market positioning"
    days_back   = 1
  })
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_run.arn
}

# -----------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------

output "lambda_function_arn" {
  description = "ARN of the Market Intelligence Agent Lambda"
  value       = aws_lambda_function.agent.arn
}

output "ecr_repository_url" {
  description = "ECR repository URL for pushing agent images"
  value       = aws_ecr_repository.agent.repository_url
}

output "reports_bucket" {
  description = "S3 bucket where intelligence reports are stored"
  value       = aws_s3_bucket.reports.bucket
}

output "invoke_command" {
  description = "AWS CLI command to manually invoke the agent"
  value       = "aws lambda invoke --function-name ${aws_lambda_function.agent.function_name} --payload '{\"competitors\":[\"Company A\",\"Company B\"]}' --cli-binary-format raw-in-base64-out response.json"
}
