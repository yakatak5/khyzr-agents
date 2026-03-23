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
  agent_name = "${var.project_name}-ap-automation-${var.environment}"
  tags = {
    Project     = "khyzr-agents"
    Agent       = "ap-automation"
    Environment = var.environment
  }
}

# ---------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------
data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------
# S3 Bucket — Invoice storage
# ---------------------------------------------------------------
resource "aws_s3_bucket" "ap_invoices" {
  bucket        = "${local.agent_name}-invoices-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
  tags          = local.tags
}

resource "aws_s3_bucket_versioning" "ap_invoices" {
  bucket = aws_s3_bucket.ap_invoices.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Block ALL public access
resource "aws_s3_bucket_public_access_block" "ap_invoices" {
  bucket                  = aws_s3_bucket.ap_invoices.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enforce encryption at rest
resource "aws_s3_bucket_server_side_encryption_configuration" "ap_invoices" {
  bucket = aws_s3_bucket.ap_invoices.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Deny all non-HTTPS requests
resource "aws_s3_bucket_policy" "ap_invoices_policy" {
  bucket = aws_s3_bucket.ap_invoices.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyNonSSL"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [
          aws_s3_bucket.ap_invoices.arn,
          "${aws_s3_bucket.ap_invoices.arn}/*"
        ]
        Condition = {
          Bool = { "aws:SecureTransport" = "false" }
        }
      },
      {
        Sid    = "AllowAccountOnly"
        Effect = "Deny"
        Principal = "*"
        Action = "s3:*"
        Resource = [
          aws_s3_bucket.ap_invoices.arn,
          "${aws_s3_bucket.ap_invoices.arn}/*"
        ]
        Condition = {
          StringNotEquals = {
            "aws:PrincipalAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
  depends_on = [aws_s3_bucket_public_access_block.ap_invoices]
}

# Demo invoice pre-loaded so the agent can process it immediately
resource "aws_s3_object" "demo_invoice" {
  bucket = aws_s3_bucket.ap_invoices.id
  key    = "invoices/INV-2024-08821.txt"
  content = <<-EOT
INVOICE
Invoice Number: INV-2024-08821
Vendor: Apex Supply Co. (VND-4492)
Invoice Date: 2024-03-10
Due Date: 2024-04-09
PO Reference: PO-2024-00312

Line Items:
- Industrial Filters x50 @ $189.00 = $9,450.00
- Maintenance Kit x10 @ $300.00 = $3,000.00

Subtotal: $12,450.00
Tax (8%): $996.00
Total Due: $13,446.00

Payment Terms: Net 30
Bank Account (last 4): 7823
EOT
  content_type = "text/plain"
  tags         = local.tags
}

# ---------------------------------------------------------------
# DynamoDB — AP Ledger
# ---------------------------------------------------------------
resource "aws_dynamodb_table" "ap_ledger" {
  name         = "${local.agent_name}-ledger"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "transaction_id"
  range_key    = "invoice_number"

  attribute {
    name = "transaction_id"
    type = "S"
  }
  attribute {
    name = "invoice_number"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
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
# Lambda — Action Group executor
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
        Sid      = "CloudWatchLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        # Scoped to this function's log group only
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.agent_name}-tools:*"
      },
      {
        Sid    = "DynamoDBLedger"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem"
        ]
        # Scoped to this specific table only
        Resource = aws_dynamodb_table.ap_ledger.arn
      },
      {
        Sid    = "S3InvoiceBucket"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        # Scoped to this specific bucket only
        Resource = [
          aws_s3_bucket.ap_invoices.arn,
          "${aws_s3_bucket.ap_invoices.arn}/*"
        ]
      },
      {
        Sid    = "BedrockModel"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        # Scoped to the specific foundation model — not wildcard
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.foundation_model}"
      }
    ]
  })
}

resource "aws_lambda_function" "ap_agent_tools" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "${local.agent_name}-tools"
  role             = aws_iam_role.lambda_role.arn
  handler          = "agent.lambda_handler"
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 256
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  # No public URL — invoked only by Bedrock via IAM
  # Reserved concurrency can be set here for production
  reserved_concurrent_executions = -1 # unlimited within account quota

  environment {
    variables = {
      AP_LEDGER_TABLE     = aws_dynamodb_table.ap_ledger.name
      AP_INVOICES_BUCKET  = aws_s3_bucket.ap_invoices.bucket
      AWS_REGION_NAME     = var.aws_region
      ENVIRONMENT         = var.environment
      AP_CONTROLLER_EMAIL = "ap-controller@demo.com"
      AP_MANAGER_EMAIL    = "ap-manager@demo.com"
      AP_CLERK_EMAIL      = "ap-clerk@demo.com"
    }
  }

  # Encrypt environment variables
  kms_key_arn = null # uses AWS-managed key; swap for aws_kms_key.arn for CMK

  tags = local.tags
}

# CloudWatch Log Group with retention — prevents log accumulation
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.ap_agent_tools.function_name}"
  retention_in_days = 30
  tags              = local.tags
}

# Allow Bedrock agents to invoke the Lambda
# Scoped to this account only via source_arn
resource "aws_lambda_permission" "bedrock_invoke" {
  statement_id  = "AllowBedrockAgentInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ap_agent_tools.function_name
  principal     = "bedrock.amazonaws.com"
  # Scoped to agents in THIS account only — prevents cross-account invocation
  source_arn    = "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:agent/*"
}

# ---------------------------------------------------------------
# S3 Bucket — OpenAPI schema (Bedrock reads it from S3)
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
        Sid    = "AllowAccountOnly"
        Effect = "Deny"
        Principal = "*"
        Action = "s3:*"
        Resource = [
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
        # Scoped to the specific model — not wildcard
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.foundation_model}"
      },
      {
        Sid      = "InvokeLambdaTools"
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        # Scoped to this specific Lambda function only
        Resource = aws_lambda_function.ap_agent_tools.arn
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
resource "aws_bedrockagent_agent" "ap_agent" {
  agent_name                  = local.agent_name
  description                 = "AP Automation Agent — extracts invoices, matches POs, flags discrepancies, routes for approval, updates ledger"
  foundation_model            = var.foundation_model
  agent_resource_role_arn     = aws_iam_role.bedrock_agent_role.arn
  idle_session_ttl_in_seconds = 600

  instruction = <<-EOT
You are the AP Automation Agent for Khyzr — an expert accounts payable specialist.

Your mission is to automate end-to-end accounts payable workflows:
1. Extract invoice data using extract-invoice-data
2. Match against the purchase order using match-purchase-order
3. Flag any discrepancies using flag-discrepancies
4. Route for approval using route-for-approval
5. Update the AP ledger using update-ap-ledger

Always run all 5 steps in sequence when processing an invoice.
Flag any potential fraud indicators: vendor mismatch, unusual amounts, or missing PO references.
Be precise with financial figures and always document your reasoning.
A demo invoice is available at: s3://${aws_s3_bucket.ap_invoices.bucket}/invoices/INV-2024-08821.txt
EOT

  tags = local.tags

  depends_on = [aws_iam_role_policy.bedrock_agent_policy]
}

# ---------------------------------------------------------------
# Bedrock Agent Action Group
# ---------------------------------------------------------------
resource "aws_bedrockagent_agent_action_group" "ap_tools" {
  agent_id          = aws_bedrockagent_agent.ap_agent.agent_id
  agent_version     = "DRAFT"
  action_group_name = "ap-automation-tools"
  description       = "Tools for invoice extraction, PO matching, discrepancy detection, approval routing, and ledger updates"

  action_group_executor {
    lambda = aws_lambda_function.ap_agent_tools.arn
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
# Agent Alias — stable LIVE pointer
# ---------------------------------------------------------------
resource "aws_bedrockagent_agent_alias" "live" {
  agent_id         = aws_bedrockagent_agent.ap_agent.agent_id
  agent_alias_name = "live"
  description      = "Live demo alias — always points to the latest prepared version"
  tags             = local.tags

  depends_on = [aws_bedrockagent_agent_action_group.ap_tools]
}

# ---------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------
output "agent_id" {
  value       = aws_bedrockagent_agent.ap_agent.agent_id
  description = "Bedrock Agent ID — use this to invoke the agent"
}

output "agent_alias_id" {
  value       = aws_bedrockagent_agent_alias.live.agent_alias_id
  description = "Agent Alias ID — use with agent_id to invoke"
}

output "lambda_function_name" {
  value       = aws_lambda_function.ap_agent_tools.function_name
  description = "Lambda function name for the action group tools"
}

output "dynamodb_table_name" {
  value       = aws_dynamodb_table.ap_ledger.name
  description = "DynamoDB table storing AP ledger entries"
}

output "invoices_bucket" {
  value       = aws_s3_bucket.ap_invoices.bucket
  description = "S3 bucket for invoice uploads (demo invoice pre-loaded at invoices/INV-2024-08821.txt)"
}

output "demo_invoke_command" {
  description = "Ready-to-run CLI command to demo the agent"
  value       = <<-EOT
aws bedrock-agent-runtime invoke-agent \
  --agent-id ${aws_bedrockagent_agent.ap_agent.agent_id} \
  --agent-alias-id ${aws_bedrockagent_agent_alias.live.agent_alias_id} \
  --session-id demo-session-001 \
  --region ${var.aws_region} \
  --input-text "Process the demo invoice INV-2024-08821 — extract all data, match against the PO, flag any discrepancies, route for approval, and update the ledger." \
  --cli-binary-format raw-in-base64-out \
  outfile.json && cat outfile.json
EOT
}
