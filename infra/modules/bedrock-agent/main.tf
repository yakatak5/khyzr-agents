data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_iam_role" "bedrock_agent_role" {
  name = "${var.agent_name}-${var.environment}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "bedrock.amazonaws.com" }
      # Prevent confused-deputy attack — restrict to this account only
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
        ArnLike = {
          "aws:SourceArn" = "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:agent/*"
        }
      }
    }]
  })

  tags = {
    Project     = "khyzr-agents"
    Environment = var.environment
    AgentName   = var.agent_name
  }
}

resource "aws_iam_role_policy" "bedrock_agent_policy" {
  name = "${var.agent_name}-${var.environment}-policy"
  role = aws_iam_role.bedrock_agent_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvokeModel"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        # Scoped to the specific model — NOT wildcard Resource = "*"
        Resource = "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/${var.foundation_model}"
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        # Scoped to this account and region — NOT arn:aws:logs:*:*:*
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock/*"
      }
    ]
  })
}

resource "aws_bedrockagent_agent" "agent" {
  agent_name              = "${var.agent_name}-${var.environment}"
  description             = var.agent_description
  foundation_model        = var.foundation_model
  agent_resource_role_arn = aws_iam_role.bedrock_agent_role.arn
  instruction             = var.instruction
  idle_session_ttl_in_seconds = 600

  tags = {
    Project     = "khyzr-agents"
    Environment = var.environment
    AgentName   = var.agent_name
  }

  depends_on = [aws_iam_role_policy.bedrock_agent_policy]
}

resource "aws_bedrockagent_agent_alias" "live" {
  agent_id         = aws_bedrockagent_agent.agent.agent_id
  agent_alias_name = "live"
}
