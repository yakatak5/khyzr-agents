# infra/modules/agentcore-runtime/outputs.tf

output "agent_runtime_arn" {
  description = "AgentCore Runtime ARN — use this value with invoke_agent_runtime"
  value       = awscc_bedrockagentcore_runtime.agent.agent_runtime_arn
}

output "agent_runtime_id" {
  description = "AgentCore Runtime ID"
  value       = awscc_bedrockagentcore_runtime.agent.agent_runtime_id
}

output "agent_code_bucket" {
  description = "S3 bucket storing the agent code zip artifact"
  value       = aws_s3_bucket.agent_code.bucket
}

output "iam_role_arn" {
  description = "ARN of the IAM role attached to the AgentCore Runtime"
  value       = aws_iam_role.agentcore_role.arn
}
