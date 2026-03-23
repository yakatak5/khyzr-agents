terraform {
  required_version = ">= 1.5.0"
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

provider "aws" {
  region = var.aws_region
}

provider "awscc" {
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
  description = "Bedrock foundation model ID used by the agent"
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
        Resource = [
          aws_s3_bucket.ap_invoices.arn,
          "${aws_s3_bucket.ap_invoices.arn}/*"
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

# Demo invoice — plain text (pre-loaded for testing)
resource "aws_s3_object" "demo_invoice" {
  bucket       = aws_s3_bucket.ap_invoices.id
  key          = "invoices/INV-2024-08821.txt"
  content      = <<-EOT
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

# Demo invoice — Excel format (.xlsx)
resource "aws_s3_object" "demo_invoice_xlsx" {
  bucket       = aws_s3_bucket.ap_invoices.id
  key          = "invoices/INV-2024-08821.xlsx"
  source       = "${path.module}/../src/demo_invoice.xlsx"
  content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  etag         = filemd5("${path.module}/../src/demo_invoice.xlsx")
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

# ---------------------------------------------------------------
# Code Zip — package agent.py + requirements.txt
# ---------------------------------------------------------------
data "archive_file" "agent_zip" {
  type        = "zip"
  output_path = "${path.module}/agent.zip"
  source {
    content  = file("${path.module}/../src/agent.py")
    filename = "agent.py"
  }
  source {
    content  = file("${path.module}/../requirements.txt")
    filename = "requirements.txt"
  }
}

resource "aws_s3_object" "agent_code" {
  bucket      = aws_s3_bucket.agent_code.id
  key         = "agent.zip"
  source      = data.archive_file.agent_zip.output_path
  source_hash = data.archive_file.agent_zip.output_base64sha256
  tags        = local.tags
}

# ---------------------------------------------------------------
# IAM Role — AgentCore Runtime
# ---------------------------------------------------------------
resource "aws_iam_role" "agentcore_role" {
  name = "${local.agent_name}-agentcore-role"
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
  name = "${local.agent_name}-agentcore-policy"
  role = aws_iam_role.agentcore_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
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
          "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
          "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
        ]
        Resource = "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default"
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
        # Scoped to this specific DynamoDB table only
        Resource = aws_dynamodb_table.ap_ledger.arn
      },
      {
        Sid    = "S3InvoiceBucket"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        # Scoped to this specific S3 bucket only
        Resource = [
          aws_s3_bucket.ap_invoices.arn,
          "${aws_s3_bucket.ap_invoices.arn}/*"
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
# AgentCore Runtime — Code Zip (Direct Code Deployment)
# No Docker, no ECR, no buildx required.
# ---------------------------------------------------------------
resource "awscc_bedrockagentcore_runtime" "ap_agent" {
  agent_runtime_name = "${local.agent_name}"
  description        = "AP Automation Agent — extracts invoices, matches POs, flags discrepancies, routes for approval, updates ledger"
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

  environment_variables = {
    AP_LEDGER_TABLE     = aws_dynamodb_table.ap_ledger.name
    AP_INVOICES_BUCKET  = aws_s3_bucket.ap_invoices.bucket
    AWS_REGION_NAME     = var.aws_region
    ENVIRONMENT         = var.environment
    AP_CONTROLLER_EMAIL = "ap-controller@demo.com"
    AP_MANAGER_EMAIL    = "ap-manager@demo.com"
    AP_CLERK_EMAIL      = "ap-clerk@demo.com"
  }

  depends_on = [aws_s3_object.agent_code]
}

# ---------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------
output "agent_runtime_arn" {
  value       = awscc_bedrockagentcore_runtime.ap_agent.agent_runtime_arn
  description = "AgentCore Runtime ARN — use this to invoke the agent"
}

output "agent_runtime_id" {
  value       = awscc_bedrockagentcore_runtime.ap_agent.agent_runtime_id
  description = "AgentCore Runtime ID"
}

output "agent_code_bucket" {
  value       = aws_s3_bucket.agent_code.bucket
  description = "S3 bucket storing the agent code zip artifact"
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
  description = "Ready-to-run commands to demo the agent via Python SDK or CLI"
  value       = <<-EOT
# ── Python SDK invocation ──────────────────────────────────────────────────
python3 -c "
import boto3, json
client = boto3.client('bedrock-agentcore', region_name='${var.aws_region}')
response = client.invoke_agent_runtime(
    agentRuntimeArn='${awscc_bedrockagentcore_runtime.ap_agent.agent_runtime_arn}',
    payload=json.dumps({
        'prompt': 'Process the demo invoice INV-2024-08821 — extract data, match the PO, flag discrepancies, route for approval, and update the ledger.'
    }).encode()
)
chunks = [c.get('chunk', b'') for c in response.get('body', [])]
print(b''.join(chunks).decode())
"

# ── AWS CLI invocation ────────────────────────────────────────────────────
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn ${awscc_bedrockagentcore_runtime.ap_agent.agent_runtime_arn} \
  --payload '{"prompt": "Process invoice INV-2024-08821 — extract data, match PO, flag discrepancies, route for approval, update ledger."}' \
  --region ${var.aws_region}
EOT
}

output "excel_demo_command" {
  description = "Demo command to process the Excel invoice from S3"
  value       = "python3 -c \"import boto3,json; c=boto3.client('bedrock-agentcore',region_name='${var.aws_region}'); r=c.invoke_agent_runtime(agentRuntimeArn='${awscc_bedrockagentcore_runtime.ap_agent.agent_runtime_arn}',payload=json.dumps({'prompt':'Process the Excel invoice at s3://${aws_s3_bucket.ap_invoices.bucket}/invoices/INV-2024-08821.xlsx — extract data, match PO, flag discrepancies, route for approval, update ledger.'}).encode()); print(b''.join([ch.get('chunk',b'') for ch in r.get('body',[])]).decode())\""
}
