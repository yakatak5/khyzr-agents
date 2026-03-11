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
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "bedrock_model_id" {
  type    = string
  default = "anthropic.claude-sonnet-4-5"
}

variable "audit_recipients" {
  description = "Comma-separated list of emails to receive audit packages"
  type        = string
  default     = ""
  # e.g. "auditor@firm.com,cfo@company.com,controller@company.com"
}

variable "ses_sender_email" {
  description = "SES-verified sender email address"
  type        = string
  default     = ""
}

variable "schedule_expression" {
  description = "EventBridge schedule for automated audit runs (e.g. month-end)"
  type        = string
  default     = "cron(0 6 1 * ? *)"  # 6 AM UTC on the 1st of every month
}

variable "audit_period_label" {
  description = "Human-readable label for scheduled audit runs"
  type        = string
  default     = "Monthly Audit"
}

# -----------------------------------------------------------------------
# Data sources
# -----------------------------------------------------------------------

data "aws_caller_identity" "current" {}

# -----------------------------------------------------------------------
# S3 bucket for audit packages
# -----------------------------------------------------------------------

resource "aws_s3_bucket" "audit" {
  bucket = "audit-trail-packages-${var.environment}-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name        = "Audit Trail Packages"
    Environment = var.environment
    Agent       = "audit-trail-agent"
  }
}

resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id

  rule {
    id     = "archive-audit-packages"
    status = "Enabled"

    filter { prefix = "packages/" }

    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "audit" {
  bucket                  = aws_s3_bucket.audit.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# -----------------------------------------------------------------------
# IAM role for Lambda
# -----------------------------------------------------------------------

resource "aws_iam_role" "agent_lambda" {
  name = "audit-trail-agent-lambda-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "agent_lambda" {
  name = "audit-trail-agent-policy"
  role = aws_iam_role.agent_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # CloudWatch Logs
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        # Bedrock
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}"
      },
      {
        # S3 audit bucket — full read/write for packages and supporting docs
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:DeleteObject",
        ]
        Resource = [
          aws_s3_bucket.audit.arn,
          "${aws_s3_bucket.audit.arn}/*",
        ]
      },
      {
        # SES email delivery
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = "*"
      },
      {
        # SSM for any secrets (DB credentials, ERP API keys, etc.)
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/audit-trail-agent/*"
      },
      {
        # RDS Data API (if using Aurora Serverless for GL data)
        Effect   = "Allow"
        Action   = ["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"]
        Resource = "*"
      },
      {
        # Athena (if querying GL data via S3/Glue)
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
        ]
        Resource = "*"
      }
    ]
  })
}

# -----------------------------------------------------------------------
# ECR repository
# -----------------------------------------------------------------------

resource "aws_ecr_repository" "agent" {
  name                 = "audit-trail-agent-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "agent" {
  repository = aws_ecr_repository.agent.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 5 }
      action       = { type = "expire" }
    }]
  })
}

# -----------------------------------------------------------------------
# Lambda function
# -----------------------------------------------------------------------

resource "aws_lambda_function" "agent" {
  function_name = "audit-trail-agent-${var.environment}"
  role          = aws_iam_role.agent_lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.agent.repository_url}:latest"
  timeout       = 600   # 10 minutes — large audit periods may have many transactions
  memory_size   = 1024

  environment {
    variables = {
      AUDIT_BUCKET      = aws_s3_bucket.audit.bucket
      BEDROCK_MODEL_ID  = var.bedrock_model_id
      AWS_REGION_NAME   = var.aws_region
      ENVIRONMENT       = var.environment
      AUDIT_RECIPIENTS  = var.audit_recipients
      SES_SENDER_EMAIL  = var.ses_sender_email
    }
  }

  tags = {
    Name        = "Audit Trail Documentation Agent"
    Environment = var.environment
    Agent       = "audit-trail-agent"
  }

  depends_on = [aws_ecr_repository.agent]

  lifecycle {
    ignore_changes = [image_uri]
  }
}

resource "aws_cloudwatch_log_group" "agent" {
  name              = "/aws/lambda/${aws_lambda_function.agent.function_name}"
  retention_in_days = 90  # Keep audit logs longer than typical
}

# -----------------------------------------------------------------------
# EventBridge — monthly scheduled run (1st of each month)
# -----------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "monthly_run" {
  name                = "audit-trail-agent-monthly-${var.environment}"
  description         = "Trigger Audit Trail Agent at start of each month"
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "monthly_run" {
  rule      = aws_cloudwatch_event_rule.monthly_run.name
  target_id = "AuditTrailAgentLambda"
  arn       = aws_lambda_function.agent.arn

  # The payload uses dynamic dates — for production, use a Step Functions
  # state machine or a thin Lambda wrapper to compute the previous month's dates
  input = jsonencode({
    audit_period       = "Monthly Audit"
    start_date         = "REPLACE_WITH_PRIOR_MONTH_START"  # Use Step Functions for dynamic dates
    end_date           = "REPLACE_WITH_PRIOR_MONTH_END"
    transaction_types  = ["INVOICE", "PAYMENT", "JOURNAL"]
  })
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.monthly_run.arn
}

# -----------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------

output "lambda_function_arn" {
  value = aws_lambda_function.agent.arn
}

output "ecr_repository_url" {
  value = aws_ecr_repository.agent.repository_url
}

output "audit_bucket" {
  value = aws_s3_bucket.audit.bucket
}

output "invoke_command" {
  value = "aws lambda invoke --function-name ${aws_lambda_function.agent.function_name} --payload '{\"audit_period\":\"Q4 2024\",\"start_date\":\"2024-10-01\",\"end_date\":\"2024-12-31\"}' --cli-binary-format raw-in-base64-out response.json"
}
