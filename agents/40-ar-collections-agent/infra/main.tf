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
        Resource = [
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
        Resource = [
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
# ECR Repository — Agent container image
# ---------------------------------------------------------------
resource "aws_ecr_repository" "agent" {
  name                 = "khyzr/ar-collections-agent"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.tags
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
        # Scoped to the specific foundation model -- not wildcard
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.foundation_model}"
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
          "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
          "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
        ]
        Resource = "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default"
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
        # Scoped to this specific DynamoDB table only
        Resource = aws_dynamodb_table.ar_collections_table.arn
      },
      {
        Sid    = "S3ReportsBucket"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        # Scoped to this specific S3 bucket only
        Resource = [
          aws_s3_bucket.ar_reports.arn,
          "${aws_s3_bucket.ar_reports.arn}/*"
        ]
      }
    ]
  })
}

# ---------------------------------------------------------------
# Docker Build & Push — ARM64 image to ECR
# NOTE: Requires Docker with buildx installed on the machine
#       running `terraform apply`. AgentCore requires ARM64 images.
# ---------------------------------------------------------------
resource "null_resource" "docker_build_push" {
  triggers = {
    agent_py_hash     = filemd5("${path.module}/../src/agent.py")
    dockerfile_hash   = filemd5("${path.module}/../Dockerfile")
    requirements_hash = filemd5("${path.module}/../requirements.txt")
  }

  provisioner "local-exec" {
    command = <<-EOT
      # Authenticate with ECR
      aws ecr get-login-password --region ${var.aws_region} | \
        docker login --username AWS --password-stdin \
        ${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com

      # Build for ARM64 (required by AgentCore Runtime) and push
      cd ${path.module}/..
      docker buildx build --platform linux/arm64 \
        -t ${aws_ecr_repository.agent.repository_url}:latest \
        --push .
    EOT
  }

  depends_on = [aws_ecr_repository.agent]
}

# ---------------------------------------------------------------
# AgentCore Runtime
# ---------------------------------------------------------------
resource "awscc_bedrockagentcore_runtime" "ar_agent" {
  agent_runtime_name = "${local.agent_name}"
  description        = "AR Collections Agent -- monitors aging AR, scores collection risk, drafts emails, escalates overdue accounts, updates collection status"
  role_arn           = aws_iam_role.agentcore_role.arn

  agent_runtime_artifact = {
    container_configuration = {
      container_uri = "${aws_ecr_repository.agent.repository_url}:latest"
    }
  }

  network_configuration = {
    network_mode = "PUBLIC"
  }

  environment_variables = {
    AR_COLLECTIONS_TABLE = aws_dynamodb_table.ar_collections_table.name
    AR_REPORTS_BUCKET    = aws_s3_bucket.ar_reports.bucket
    AWS_REGION_NAME      = var.aws_region
    ENVIRONMENT          = var.environment
    AR_MANAGER_EMAIL     = "ar-manager@demo.com"
    CFO_EMAIL            = "cfo@demo.com"
    COMPANY_NAME         = "Khyzr"
    AR_CONTACT_NAME      = "Accounts Receivable Team"
  }

  depends_on = [null_resource.docker_build_push]
}

# ---------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------
output "agent_runtime_arn" {
  value       = awscc_bedrockagentcore_runtime.ar_agent.agent_runtime_arn
  description = "AgentCore Runtime ARN — use this to invoke the agent"
}

output "agent_runtime_id" {
  value       = awscc_bedrockagentcore_runtime.ar_agent.agent_runtime_id
  description = "AgentCore Runtime ID"
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.agent.repository_url
  description = "ECR repository URL for the agent container image"
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
  description = "Ready-to-run commands to demo the agent via Python SDK or CLI"
  value       = <<-EOT
# ── Python SDK invocation ──────────────────────────────────────────────────
python3 -c "
import boto3, json
client = boto3.client('bedrock-agentcore', region_name='${var.aws_region}')
response = client.invoke_agent_runtime(
    agentRuntimeArn='${awscc_bedrockagentcore_runtime.ar_agent.agent_runtime_arn}',
    payload=json.dumps({
        'prompt': 'Work the full collections queue: fetch aging AR, score all accounts, draft collection emails, escalate high-risk accounts, update statuses.'
    }).encode()
)
chunks = [c.get('chunk', b'') for c in response.get('body', [])]
print(b''.join(chunks).decode())
"

# ── AWS CLI invocation ─────────────────────────────────────────────────────
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn ${awscc_bedrockagentcore_runtime.ar_agent.agent_runtime_arn} \
  --payload '{"prompt": "Work the full collections queue: fetch aging AR, score all accounts, draft collection emails, escalate high-risk accounts, update statuses."}' \
  --region ${var.aws_region}
EOT
}

output "excel_demo_command" {
  description = "Demo command to process the Excel aging report from S3"
  value       = "python3 -c \"import boto3,json; c=boto3.client('bedrock-agentcore',region_name='${var.aws_region}'); r=c.invoke_agent_runtime(agentRuntimeArn='${awscc_bedrockagentcore_runtime.ar_agent.agent_runtime_arn}',payload=json.dumps({'prompt':'Fetch the Excel aging report from s3://${aws_s3_bucket.ar_reports.bucket}/reports/aging-report-demo.xlsx, score all accounts, draft collection emails, escalate as needed, and update statuses.'}).encode()); print(b''.join([ch.get('chunk',b'') for ch in r.get('body',[])]).decode())\""
}
