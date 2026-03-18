output "agent_id" {
  description = "Bedrock agent ID"
  value       = aws_bedrockagent_agent.agent.agent_id
}

output "agent_arn" {
  description = "Bedrock agent ARN"
  value       = aws_bedrockagent_agent.agent.agent_arn
}

output "agent_alias_id" {
  description = "Bedrock agent alias ID (live)"
  value       = aws_bedrockagent_agent_alias.live.agent_alias_id
}
