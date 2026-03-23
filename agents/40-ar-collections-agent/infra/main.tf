terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
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
  default     = "anthropic.claude-sonnet-4-5-v1:0"
  description = "Bedrock foundation model ID for the agent"
}

variable "project_name" {
  default     = "khyzr"
  description = "Project prefix used in resource names"
}

locals {
  agent_name = "${var.project_name}-ar-collections-${var.environment}"
  tags = {
    Project     = "khyzr-agents"
    Agent       = "ar-collections"
    Environment = var.environment
  }
}

# ---------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------
data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------
# DynamoDB -- AR Collections status store
# ---------------------------------------------------------------
resource "aws_dynamodb_table" "ar_collections_table" {
  name         = local.agent_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "account_id"
  range_key    = "updated_at"

  attribute {
    name = "account_id"
    type = "S"
  }
  attribute {
    name = "updated_at"
    type = "S"
  }

  # Encryption at rest using AWS-owned key
  server_side_encryption {
    enabled = true
  }

  # Point-in-time recovery
  point_in_time_recovery {
    enabled = true
  }

  tags = local.tags
}

# ---------------------------------------------------------------
# S3 Bucket -- AR aging reports
# ---------------------------------------------------------------
resource "aws_s3_bucket" "ar_reports" {
  bucket        = "${local.agent_name}-reports-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
  tags          = local.tags
}

resource "aws_s3_bucket_versioning" "ar_reports" {
  bucket = aws_s3_bucket.ar_reports.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Block ALL public access
resource "aws_s3_bucket_public_access_block" "ar_reports" {
  bucket                  = aws_s3_bucket.ar_reports.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enforce encryption at rest
resource "aws_s3_bucket_server_side_encryption_configuration" "ar_reports" {
  bucket = aws_s3_bucket.ar_reports.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Deny all non-HTTPS requests + cross-account access
resource "aws_s3_bucket_policy" "ar_reports_policy" {
  bucket = aws_s3_bucket.ar_reports.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyNonSSL"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [
          aws_s3_bucket.ar_reports.arn,
          "${aws_s3_bucket.ar_reports.arn}/*"
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
        Resource  = [
          aws_s3_bucket.ar_reports.arn,
          "${aws_s3_bucket.ar_reports.arn}/*"
        ]
        Condition = {
          StringNotEquals = {
            "aws:PrincipalAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
  depends_on = [aws_s3_bucket_public_access_block.ar_reports]
}

# Demo aging report -- JSON (pre-loaded for testing)
resource "aws_s3_object" "demo_aging_report" {
  bucket       = aws_s3_bucket.ar_reports.id
  key          = "reports/aging-report-demo.json"
  content_type = "application/json"
  content = jsonencode({
    report_date = "2024-03-12"
    currency    = "USD"
    summary = {
      total_ar      = 1847500.00
      current       = 820000.00
      days_1_30     = 385000.00
      days_31_60    = 312500.00
      days_61_90    = 198000.00
      days_91_plus  = 132000.00
    }
    accounts = [
      {
        account_id        = "ACC-10021"
        company_name      = "Nexus Technologies Inc."
        contact_email     = "ap@nexustech.com"
        contact_name      = "Sarah Chen"
        invoice_number    = "INV-2024-0891"
        invoice_date      = "2024-01-10"
        due_date          = "2024-02-09"
        days_overdue      = 32
        balance           = 48500.00
        payment_history   = "good"
        last_payment_date = "2023-12-15"
      },
      {
        account_id        = "ACC-10045"
        company_name      = "Meridian Logistics Group"
        contact_email     = "finance@meridianlogistics.com"
        contact_name      = "Robert Okafor"
        invoice_number    = "INV-2024-0742"
        invoice_date      = "2023-12-20"
        due_date          = "2024-01-19"
        days_overdue      = 53
        balance           = 127000.00
        payment_history   = "slow_pay"
        last_payment_date = "2023-10-08"
      },
      {
        account_id        = "ACC-10078"
        company_name      = "Cascade Retail Corp"
        contact_email     = "payments@cascaderetail.com"
        contact_name      = "Linda Park"
        invoice_number    = "INV-2024-0615"
        invoice_date      = "2023-11-15"
        due_date          = "2023-12-15"
        days_overdue      = 88
        balance           = 89500.00
        payment_history   = "poor"
        last_payment_date = "2023-08-20"
      },
      {
        account_id        = "ACC-10092"
        company_name      = "Summit Healthcare Partners"
        contact_email     = "billing@summithealthcare.com"
        contact_name      = "Michael Torres"
        invoice_number    = "INV-2024-0582"
        invoice_date      = "2023-11-01"
        due_date          = "2023-12-01"
        days_overdue      = 102
        balance           = 42000.00
        payment_history   = "poor"
        last_payment_date = "2023-07-15"
      }
    ]
  })
  tags = local.tags
}

# Demo aging report -- Excel (.xlsx)
resource "aws_s3_object" "demo_aging_report_xlsx" {
  bucket       = aws_s3_bucket.ar_reports.id
  key          = "reports/aging-report-demo.xlsx"
  source       = "${path.module}/../src/demo_aging_report.xlsx"
  content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  etag         = filemd5("${path.module}/../src/demo_aging_report.xlsx")
  tags         = local.tags
}

# ---------------------------------------------------------------
# S3 Bucket -- OpenAPI schema (Bedrock reads it from S3)
# ---------------------------------------------------------------
resource "aws_s3_bucket" "schema_bucket" {
  bucket        = "${local.agent_name}-schema-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
  tags          = local.tags
}

resource "aws_s3_bucket_public_access_block" "schema_bucket" {
  bucket                  = aws_s3_bucket.schema_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "schema_bucket" {
  bucket = aws_s3_bucket.schema_bucket.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_policy" "schema_bucket_policy" {
  bucket = aws_s3_bucket.schema_bucket.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyNonSSL"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [
          aws_s3_bucket.schema_bucket.arn,
          "${aws_s3_bucket.schema_bucket.arn}/*"
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
        Resource  = [
          aws_s3_bucket.schema_bucket.arn,
          "${aws_s3_bucket.schema_bucket.arn}/*"
        ]
        Condition = {
          StringNotEquals = {
            "aws:PrincipalAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
  depends_on = [aws_s3_bucket_public_access_block.schema_bucket]
}

resource "aws_s3_object" "openapi_schema" {
  bucket       = aws_s3_bucket.schema_bucket.id
  key          = "openapi.json"
  source       = "${path.module}/../src/openapi.json"
  content_type = "application/json"
  etag         = filemd5("${path.module}/../src/openapi.json")
  tags         = local.tags
}

# ---------------------------------------------------------------
# Lambda -- Action Group executor
# ---------------------------------------------------------------

# Package the Lambda source
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../src/agent.py"
  output_path = "${path.module}/lambda_package.zip"
}

# Lambda IAM Role
resource "aws_iam_role" "lambda_role" {
  name = "${local.agent_name}-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
  tags = local.tags
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "${local.agent_name}-lambda-policy"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        # Scoped to this function's log group only
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.agent_name}-tools:*"
      },
      {
        Sid    = "DynamoDBCollections"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem"
        ]
        # Scoped to this specific table only
        Resource = aws_dynamodb_table.ar_collections_table.arn
      },
      {
        Sid    = "S3ReportsBucket"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        # Scoped to this specific bucket only
        Resource = [
          aws_s3_bucket.ar_reports.arn,
          "${aws_s3_bucket.ar_reports.arn}/*"
        ]
      },
      {
        Sid    = "BedrockModel"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        # Scoped to the specific foundation model -- not wildcard
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.foundation_model}"
      }
    ]
  })
}

resource "aws_lambda_function" "ar_agent_tools" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "${local.agent_name}-tools"
  role             = aws_iam_role.lambda_role.arn
  handler          = "agent.lambda_handler"
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 256
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  # No public URL -- invoked only by Bedrock via IAM
  reserved_concurrent_executions = -1  # unlimited within account quota

  environment {
    variables = {
      AR_COLLECTIONS_TABLE = aws_dynamodb_table.ar_collections_table.name
      AR_REPORTS_BUCKET    = aws_s3_bucket.ar_reports.bucket
      AWS_REGION_NAME      = var.aws_region
      ENVIRONMENT          = var.environment
      AR_MANAGER_EMAIL     = "ar-manager@demo.com"
      CFO_EMAIL            = "cfo@demo.com"
      COMPANY_NAME         = "Khyzr"
      AR_CONTACT_NAME      = "Accounts Receivable Team"
    }
  }

  # Encrypt environment variables using AWS-managed key
  kms_key_arn = null

  tags = local.tags
}

# CloudWatch Log Group with retention -- prevents log accumulation
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.ar_agent_tools.function_name}"
  retention_in_days = 30
  tags              = local.tags
}

# Allow Bedrock agents to invoke the Lambda
# Scoped to this account only via source_arn
resource "aws_lambda_permission" "bedrock_invoke" {
  statement_id  = "AllowBedrockAgentInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ar_agent_tools.function_name
  principal     = "bedrock.amazonaws.com"
  # Scoped to agents in THIS account only -- prevents cross-account invocation
  source_arn    = "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:agent/*"
}

# ---------------------------------------------------------------
# Bedrock Agent IAM Role
# ---------------------------------------------------------------
resource "aws_iam_role" "bedrock_agent_role" {
  name = "${local.agent_name}-bedrock-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "bedrock.amazonaws.com" }
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
        ArnLike = {
          "aws:SourceArn" = "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:agent/*"
        }
      }
    }]
  })
  tags = local.tags
}

resource "aws_iam_role_policy" "bedrock_agent_policy" {
  name = "${local.agent_name}-bedrock-policy"
  role = aws_iam_role.bedrock_agent_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvokeModel"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        # Scoped to the specific model -- not wildcard
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.foundation_model}"
      },
      {
        Sid      = "InvokeLambdaTools"
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        # Scoped to this specific Lambda function only
        Resource = aws_lambda_function.ar_agent_tools.arn
      },
      {
        Sid      = "ReadOpenAPISchema"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        # Scoped to this specific schema bucket only
        Resource = "${aws_s3_bucket.schema_bucket.arn}/*"
      },
      {
        Sid      = "CloudWatchLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        # Scoped to this account and region
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock/*"
      }
    ]
  })
}

# ---------------------------------------------------------------
# Bedrock Agent
# ---------------------------------------------------------------
resource "aws_bedrockagent_agent" "ar_agent" {
  agent_name                  = local.agent_name
  description                 = "AR Collections Agent -- monitors aging AR, scores collection risk, drafts emails, escalates overdue accounts, updates collection status"
  foundation_model            = var.foundation_model
  agent_resource_role_arn     = aws_iam_role.bedrock_agent_role.arn
  idle_session_ttl_in_seconds = 600

  instruction = <<-EOT
You are the AR Collections Agent for Khyzr -- an expert accounts receivable specialist.

Your mission is to work the collections queue end-to-end:
1. Fetch the aging AR report using fetch-aging-report
   - For Excel reports, pass excel_source with the S3 URI
   - Demo aging reports pre-loaded in S3:
     JSON:  s3://${aws_s3_bucket.ar_reports.bucket}/reports/aging-report-demo.json
     Excel: s3://${aws_s3_bucket.ar_reports.bucket}/reports/aging-report-demo.xlsx
   - You can also accept any .xlsx aging report uploaded to S3
2. Score each account by collection risk tier using score-collection-risk
3. Draft personalized collection emails using draft-collection-email
4. Escalate accounts to appropriate personnel using escalate-account
5. Update collection status using update-collection-status (writes to DynamoDB)

Always run all 5 steps in sequence when working the collections queue.
Prioritize by risk score and outstanding balance. Flag any account over $100K.
Adapt email tone to risk tier: friendly for Low, formal for Medium, urgent for High, final-demand for Critical.
EOT

  tags = local.tags

  depends_on = [aws_iam_role_policy.bedrock_agent_policy]
}

# ---------------------------------------------------------------
# Bedrock Agent Action Group
# ---------------------------------------------------------------
resource "aws_bedrockagent_agent_action_group" "ar_tools" {
  agent_id          = aws_bedrockagent_agent.ar_agent.agent_id
  agent_version     = "DRAFT"
  action_group_name = "ar-collections-tools"
  description       = "Tools for AR aging reports (JSON + Excel), risk scoring, collection emails, escalation, and status updates"

  action_group_executor {
    lambda = aws_lambda_function.ar_agent_tools.arn
  }

  api_schema {
    s3 {
      s3_bucket_name = aws_s3_bucket.schema_bucket.id
      s3_object_key  = aws_s3_object.openapi_schema.key
    }
  }

  depends_on = [
    aws_lambda_permission.bedrock_invoke,
    aws_s3_object.openapi_schema,
  ]
}

# ---------------------------------------------------------------
# Agent Alias -- stable LIVE pointer
# ---------------------------------------------------------------
resource "aws_bedrockagent_agent_alias" "live" {
  agent_id         = aws_bedrockagent_agent.ar_agent.agent_id
  agent_alias_name = "live"
  description      = "Live demo alias -- always points to the latest prepared version"
  tags             = local.tags

  depends_on = [aws_bedrockagent_agent_action_group.ar_tools]
}

# ---------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------
output "agent_id" {
  value       = aws_bedrockagent_agent.ar_agent.agent_id
  description = "Bedrock Agent ID -- use this to invoke the agent"
}

output "agent_alias_id" {
  value       = aws_bedrockagent_agent_alias.live.agent_alias_id
  description = "Agent Alias ID -- use with agent_id to invoke"
}

output "lambda_function_name" {
  value       = aws_lambda_function.ar_agent_tools.function_name
  description = "Lambda function name for the action group tools"
}

output "dynamodb_table_name" {
  value       = aws_dynamodb_table.ar_collections_table.name
  description = "DynamoDB table storing AR collection status updates"
}

output "ar_reports_bucket" {
  value       = aws_s3_bucket.ar_reports.bucket
  description = "S3 bucket for aging reports (demo reports pre-loaded)"
}

output "demo_invoke_command" {
  description = "Ready-to-run CLI command to demo the agent"
  value       = <<-EOT
aws bedrock-agent-runtime invoke-agent \
  --agent-id ${aws_bedrockagent_agent.ar_agent.agent_id} \
  --agent-alias-id ${aws_bedrockagent_agent_alias.live.agent_alias_id} \
  --session-id demo-session-001 \
  --region ${var.aws_region} \
  --input-text "Work the full collections queue — fetch the aging report from s3://${aws_s3_bucket.ar_reports.bucket}/reports/aging-report-demo.json, score all accounts, draft collection emails, escalate as needed, and update statuses." \
  --cli-binary-format raw-in-base64-out \
  outfile.json && cat outfile.json
EOT
}
