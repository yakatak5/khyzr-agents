# AR Collections Agent — Demo Guide

## What This Agent Does

End-to-end accounts receivable collections automation:

1. **Fetches** the AR aging report — mock data, JSON from S3, or Excel (.xlsx) from S3
2. **Scores** each account by collection risk tier (Critical / High / Medium / Low)
3. **Drafts** tier-appropriate collection emails (friendly → formal → urgent → final-demand)
4. **Escalates** overdue accounts to AR manager or CFO based on risk tier
5. **Records** collection status in DynamoDB with next scheduled action

---

## Deploy

```bash
cd agents/40-ar-collections-agent/infra
terraform init
terraform apply
```

Takes ~3 minutes. Deploys:

- ✅ Bedrock Agent with Claude Sonnet
- ✅ Lambda function (action group tools)
- ✅ DynamoDB table (collection status store)
- ✅ S3 bucket (aging reports — JSON + Excel demo reports pre-loaded)
- ✅ IAM roles and permissions (least-privilege, no wildcard resources)
- ✅ OpenAPI schema wired up

---

## Run the Demo

After `terraform apply` completes, copy the `demo_invoke_command` from the Terraform outputs and run it directly.

### CLI (copy from `terraform output demo_invoke_command`)

```bash
aws bedrock-agent-runtime invoke-agent \
  --agent-id <AGENT_ID> \
  --agent-alias-id <ALIAS_ID> \
  --session-id demo-session-001 \
  --region us-east-1 \
  --input-text "Work the full collections queue — fetch the aging report from s3://<BUCKET>/reports/aging-report-demo.json, score all accounts, draft collection emails, escalate as needed, and update statuses." \
  --cli-binary-format raw-in-base64-out \
  outfile.json && cat outfile.json
```

### AWS Console

1. Go to **Amazon Bedrock → Agents**
2. Find `khyzr-ar-collections-demo`
3. Click **Test**
4. Type any of the prompts from the Test Scenarios below

---

## Expected Output

The agent will call all 5 tools in sequence:

| Step | Tool | Expected Result |
|------|------|-----------------|
| 1 | `fetch-aging-report` | 4 accounts returned; total AR $307K overdue |
| 2 | `score-collection-risk` | Summit Healthcare → Critical (102 days, score 62), Cascade Retail → High (88 days, score 65), Meridian → High (53 days), Nexus → Medium (32 days) |
| 3 | `draft-collection-email` | 4 emails drafted — tones match risk tiers |
| 4 | `escalate-account` | Critical accounts flagged for CFO + service review; High for AR manager |
| 5 | `update-collection-status` | All 4 accounts written to DynamoDB with next actions |

---

## Test Scenarios

### Scenario 1 — Full Collections Run (Happy Path)

> **Prompt:** "Work the full collections queue for today"

**Expected:**
- ✅ Fetches aging report (mock data — 4 accounts)
- ✅ Scores all 4 accounts: 2 Critical, 1 High, 1 Medium
- ✅ Drafts 4 emails with appropriate tones
- ✅ Escalates Critical accounts (Summit + Cascade) to AR manager + CFO
- ✅ All 4 status updates written to DynamoDB
- 🚨 Flags Meridian Logistics ($127K balance) as over $100K threshold

---

### Scenario 2 — High-Risk Focus

> **Prompt:** "Show me all accounts over 60 days overdue and escalate Critical ones"

**Expected:**
- ✅ Fetches aging report with `min_days_overdue=60`
- ✅ Returns 2 accounts: Cascade Retail (88 days) + Summit Healthcare (102 days)
- ✅ Both scored Critical
- ✅ Final-demand emails drafted for both
- ✅ Escalated: CFO + AR manager notified, service suspension flagged
- ✅ Statuses updated to `escalated` in DynamoDB

---

### Scenario 3 — Single Account

> **Prompt:** "Draft a collection email for Cascade Retail Corp (ACC-10078) — they're 88 days overdue with $89,500 outstanding"

**Expected:**
- ✅ Scores ACC-10078 as Critical (88 days + poor payment history)
- ✅ Drafts FINAL NOTICE email with $89,500 balance and 88-day urgency
- ✅ Escalates to AR manager
- ✅ Status updated to `escalated`

---

### Bonus — Excel Aging Report

> **Prompt:** "Process the Excel aging report at s3://<BUCKET>/reports/aging-report-demo.xlsx"

**Expected:**
- ✅ Fetches and parses the `.xlsx` from S3 using openpyxl
- ✅ Auto-detects header row + 11 columns
- ✅ Same 4 accounts loaded from the spreadsheet
- ✅ Rest of collections workflow runs identically

---

## DynamoDB Verification

After the demo, confirm collection status entries were written:

```bash
aws dynamodb scan \
  --table-name khyzr-ar-collections-demo \
  --region us-east-1 \
  --output json | python3 -m json.tool
```

You should see 4 items with `account_id`, `new_status`, `next_action`, and `updated_at` fields.

---

## Architecture

```
User / CLI
    │
    ▼
Amazon Bedrock Agent (Claude Sonnet)
    │  orchestrates tool calls
    ▼
Lambda Function (agent.lambda_handler)
    ├── /fetch-aging-report   → mock data OR parses JSON/Excel from S3
    ├── /score-collection-risk → risk scoring (days × balance × history)
    ├── /draft-collection-email → tier-toned email generation
    ├── /escalate-account      → internal routing (AR manager / CFO)
    └── /update-collection-status → DynamoDB write + next action
            │
            ├── DynamoDB (collection status store)
            └── S3 (aging reports: JSON + Excel)
```

---

## File Structure

```
agents/40-ar-collections-agent/
├── src/
│   ├── agent.py               # Lambda handler + all 5 tools + Excel parser
│   ├── openapi.json           # OpenAPI 3.0 schema for Bedrock Action Group
│   └── demo_aging_report.xlsx # Demo Excel aging report (4 accounts, pure stdlib)
├── infra/
│   ├── main.tf                # Full Terraform — Bedrock + Lambda + DynamoDB + S3 + IAM
│   └── terraform.tfvars       # Default variable values
├── docs/
│   ├── README.md              # Architecture overview
│   └── DEMO.md                # This file
├── requirements.txt           # Python deps (strands-agents, boto3, openpyxl)
└── Dockerfile                 # Container build (for local testing)
```

---

## Teardown

```bash
cd agents/40-ar-collections-agent/infra
terraform destroy
```

Removes all AWS resources. No ongoing costs after destroy.

> **Note:** `force_destroy = true` is set on S3 buckets, so Terraform will empty them automatically before deletion.

---

## Troubleshooting

**"ResourceNotFoundException" on DynamoDB write**
→ The Lambda env var `AR_COLLECTIONS_TABLE` must match the actual table name. Verify with:
```bash
terraform output dynamodb_table_name
```

**Excel parsing returns mock data**
→ Ensure openpyxl is included in the Lambda deployment package (it's in `requirements.txt`).
→ Verify the S3 URI is correct: `s3://<bucket>/reports/aging-report-demo.xlsx`

**Agent returns no tool calls**
→ The agent alias must point to a prepared version. Terraform creates the alias automatically; if you modify the agent in the console, click **Prepare** before testing.

**"AccessDeniedException" invoking Bedrock model**
→ Ensure the foundation model `anthropic.claude-sonnet-4-5-v1:0` is enabled in your AWS account under **Bedrock → Model access**.
