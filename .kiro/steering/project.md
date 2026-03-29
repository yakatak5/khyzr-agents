# Khyzr Agents — Project Steering

## Overview
46 production AI agents built on AWS Strands Agents SDK and Amazon Bedrock AgentCore.
Covers 5 domains: Executive Strategy, Sales & Marketing, Operations, Finance & Accounting, Healthcare.

## Technology Stack
- **Agent Framework:** AWS Strands Agents SDK (`strands-agents`)
- **LLM:** Amazon Bedrock — Claude Sonnet (`us.us.anthropic.claude-3-5-sonnet-20241022-v2:0`)
- **Deployment Runtime:** Amazon Bedrock AgentCore Runtime (`awscc_bedrockagentcore_runtime`)
- **Code Deployment:** Code Zip (Direct Code Deployment) — S3 code artifact, no Docker required
- **Infrastructure:** Terraform (`aws` + `awscc` + `archive` providers)
- **Invocation:** `bedrock-agentcore:InvokeAgentRuntime`
- **Region:** us-east-1 (default)

## Agent Domains
| Range | Domain | Count |
|-------|--------|-------|
| 01–11 | Executive Strategy | 11 |
| 12–23 | Sales & Marketing | 12 |
| 24–35 | Operations | 12 |
| 36–41 | Finance & Accounting | 6 |
| 42–46 | Healthcare | 5 |

## Agent Directory Map
| # | Agent | Directory |
|---|-------|-----------|
| 01 | Market Intelligence | agents/01-market-intelligence-agent |
| 02 | Executive Reporting | agents/02-executive-reporting-agent |
| 03 | Strategy Document | agents/03-strategy-document-agent |
| 04 | Deal Sourcing | agents/04-deal-sourcing-agent |
| 05 | Scenario Modeling | agents/05-scenario-modeling-agent |
| 06 | Briefing | agents/06-briefing-agent |
| 07 | OKR Tracking | agents/07-okr-tracking-agent |
| 08 | ESG Reporting | agents/08-esg-reporting-agent |
| 09 | Risk Monitoring | agents/09-risk-monitoring-agent |
| 10 | IR Communication | agents/10-ir-communication-agent |
| 11 | Org Intelligence | agents/11-org-intelligence-agent |
| 12 | Lead Scoring | agents/12-lead-scoring-agent |
| 13 | SEO Content | agents/13-seo-content-agent |
| 14 | Email Personalization | agents/14-email-personalization-agent |
| 15 | Social Media | agents/15-social-media-agent |
| 16 | CRM Enrichment | agents/16-crm-enrichment-agent |
| 17 | Battlecard | agents/17-battlecard-agent |
| 18 | Sales Enablement | agents/18-sales-enablement-agent |
| 19 | Ad Optimization | agents/19-ad-optimization-agent |
| 20 | Churn Intelligence | agents/20-churn-intelligence-agent |
| 21 | ABM Intelligence | agents/21-abm-intelligence-agent |
| 22 | Attribution | agents/22-attribution-agent |
| 23 | Sentiment Monitoring | agents/23-sentiment-monitoring-agent |
| 24 | Demand Forecasting | agents/24-demand-forecasting-agent |
| 25 | Inventory Optimization | agents/25-inventory-optimization-agent |
| 26 | Vendor Compliance | agents/26-vendor-compliance-agent |
| 27 | Project Management | agents/27-project-management-agent |
| 28 | SOP Drafting | agents/28-sop-drafting-agent |
| 29 | Procurement | agents/29-procurement-agent |
| 30 | Scheduling Optimization | agents/30-scheduling-optimization-agent |
| 31 | QC Monitoring | agents/31-qc-monitoring-agent |
| 32 | Logistics Coordination | agents/32-logistics-coordination-agent |
| 33 | Contract Management | agents/33-contract-management-agent |
| 34 | Support Automation | agents/34-support-automation-agent |
| 35 | Process Intelligence | agents/35-process-intelligence-agent |
| 36 | AP Automation ⭐⭐ | agents/36-ap-automation-agent |
| 37 | Financial Reporting | agents/37-financial-reporting-agent |
| 38 | Investment Analysis | agents/38-investment-analysis-agent |
| 39 | Expense Audit ⭐ | agents/39-expense-audit-agent |
| 40 | AR Collections ⭐⭐ | agents/40-ar-collections-agent |
| 41 | Cash Flow | agents/41-cash-flow-agent |
| 42 | Healthcare Scheduling | agents/42-scheduling-automation-agent |
| 43 | Medical Coding | agents/43-medical-coding-agent |
| 44 | Clinical Documentation | agents/44-clinical-documentation-agent |
| 45 | Patient Intake | agents/45-patient-intake-agent |
| 46 | Revenue Cycle | agents/46-revenue-cycle-agent |

⭐ = Full demo-ready with Lambda + DynamoDB + S3 + Action Groups
⭐⭐ = AgentCore-upgraded: containerized Strands agent on AgentCore Runtime (no Lambda)

## Development Conventions

### AgentCore Agents (36, 40) — NEW Pattern
- Entry point: `src/agent.py` with `BedrockAgentCoreApp` + `@app.entrypoint`
- Tools use `@tool` decorator from strands
- Deployment: Code Zip (Direct Code Deployment) — no Dockerfile, no ECR
- Terraform: `data "archive_file"` zips `agent.py` + `requirements.txt` → `aws_s3_object` uploads to S3 → `awscc_bedrockagentcore_runtime` references `code_artifact.s3_location`
- requirements.txt: includes `bedrock-agentcore>=0.1.0`
- Invocation: `bedrock-agentcore invoke-agent-runtime --agent-runtime-arn <arn> --payload '{"prompt": "..."}'`
- Redeployment: `terraform apply` — detects hash changes, rebuilds zip, re-uploads to S3 (~10s)

### Legacy Agents (all others) — Lambda Pattern
- Entry point: `src/agent.py` with `run(input_data: dict) -> dict` + `lambda_handler(event, context)`
- Tools use `@tool` decorator from strands
- Terraform: `aws_bedrockagent_agent` + Lambda + Action Groups + OpenAPI schema

## Shared Infrastructure

### Reusable Terraform Module
`infra/modules/agentcore-runtime/` — drop-in module for deploying any Strands agent to AgentCore Runtime.
Provides: S3 code bucket, archive_file zip, aws_s3_object upload, IAM role (with base AgentCore permissions), `awscc_bedrockagentcore_runtime` resource using `code_artifact.s3_location`.
Pass `agent_py_path`, `requirements_path`, and `extra_iam_statements` for agent-specific permissions (DynamoDB, S3, etc.).

### Build Script
`scripts/build-push.sh <agent-dir> [region]` — legacy script for container-based agents (not needed for agents 36/40).

## Security Standards (enforced on all agents)
- S3: public access blocked, AES256 encryption, HTTPS-only bucket policy, account-scoped deny
- DynamoDB: server-side encryption, point-in-time recovery enabled
- IAM: least-privilege; ECR permissions removed from agents 36/40 (Code Zip needs only `s3:GetObject` on the code bucket)
- AgentCore: `bedrock-agentcore.amazonaws.com` service principal with `aws:SourceAccount` condition
- Code Zip: agent.py + requirements.txt zipped and uploaded to private S3 bucket with versioning + AES256 encryption
- Bedrock IAM: SourceAccount condition to prevent confused-deputy attacks
