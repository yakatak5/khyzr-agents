resource "aws_iam_role" "bedrock_agent_role" {
  name = "${var.agent_name}-${var.environment}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "bedrock.amazonaws.com" }
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
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
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
}

resource "aws_bedrockagent_agent_alias" "live" {
  agent_id         = aws_bedrockagent_agent.agent.agent_id
  agent_alias_name = "live"
}
