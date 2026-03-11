aws_region          = "us-east-1"
environment         = "dev"
bedrock_model_id    = "anthropic.claude-sonnet-4-5"
schedule_expression = "cron(0 6 1 * ? *)"   # 6 AM UTC on the 1st of every month
audit_recipients    = "auditor@firm.com,cfo@yourcompany.com,controller@yourcompany.com"
ses_sender_email    = "audit-agent@yourcompany.com"   # Must be SES-verified
