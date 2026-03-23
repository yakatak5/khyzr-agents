# AR Collections Agent — Demo Guide

## What This Agent Does

End-to-end AR collections automation in 5 steps:

1. **Fetch** aging AR report — from Excel (.xlsx), JSON, or demo data
2. **Score** each account by risk tier (Critical / High / Medium / Low)
3. **Draft** personalized collection emails matched to urgency
4. **Escalate** accounts to AR Manager and/or CFO based on tier
5. **Record** every action in DynamoDB with next follow-up date

## Deploy

```bash
cd agents/40-ar-collections-agent/infra
terraform init
terraform apply
```

Takes ~3 minutes. Deploys:
- ✅ Bedrock Agent with Claude Sonnet
- ✅ Lambda function (all 5 tools as Action Group)
- ✅ DynamoDB table (collection status log)
- ✅ S3 bucket with two demo aging reports pre-loaded:
  - `reports/aging-report-demo.json`
  - `reports/aging-report-demo.xlsx` (Excel, single sheet, 4 accounts)
- ✅ All IAM locked to account-private (no wildcard resources)

## Run the Demo

After `terraform apply`, copy the `demo_invoke_command` output and run it.

### Scenario 1 — Full Collections Run (JSON data)
```
"Work the full collections queue: fetch the aging report, score all accounts 
by risk, draft collection emails, escalate high-risk accounts, and update statuses."
```

Expected flow:
- `fetch-aging-report` → 4 accounts, $1.85M total AR
- `score-collection-risk` → Summit Healthcare (Critical, 102 days), Cascade Retail (High, 88 days), Meridian Logistics (High, 53 days), Nexus Tech (Medium, 32 days)
- `draft-collection-email` × 4 → tier-appropriate emails
- `escalate-account` × 4 → CFO notified for Critical, AR Manager for High/Medium
- `update-collection-status` × 4 → all written to DynamoDB

---

### Scenario 2 — Excel Report
```
"Fetch the Excel aging report from s3://<ar_reports_bucket>/reports/aging-report-demo.xlsx,
score all accounts, draft emails, and escalate Critical accounts."
```

Expected: Same 4 accounts parsed from Excel sheet "AR Aging Report"

---

### Scenario 3 — Single Account Deep Dive
```
"Draft a collection email for Cascade Retail Corp (ACC-10078) — 
they are 88 days overdue with $89,500 outstanding and have a poor payment history. 
Then escalate and update their status."
```

Expected: High-risk urgent email + AR Manager escalation + DynamoDB record

---

### Scenario 4 — High-Value Focus
```
"Show me all accounts over 60 days overdue, flag any over $100K, 
and escalate the Critical ones immediately."
```

Expected: Flags Meridian Logistics ($127K 🚨), escalates Summit Healthcare + Cascade Retail as Critical/High

---

## Verify DynamoDB Records

```bash
aws dynamodb scan \
  --table-name khyzr-ar-collections-demo \
  --region us-east-1
```

## Check Logs

```bash
aws logs tail /aws/lambda/khyzr-ar-collections-demo-tools --follow --region us-east-1
```

## Teardown

```bash
terraform destroy -auto-approve
```

Removes all AWS resources. No ongoing costs after destroy.

## Excel Aging Report Format

The agent auto-detects these column headers (flexible matching):

| Column | Aliases |
|--------|---------|
| Account ID | acct_id, id |
| Company Name | company, customer |
| Contact Name | contact |
| Contact Email | email |
| Invoice Number | invoice_no, invoice |
| Invoice Date | issued |
| Due Date | due |
| Days Overdue | days_past, overdue_days |
| Balance | amount, outstanding |
| Payment History | history, pay_history |
| Last Payment Date | last_paid |

Any `.xlsx` file with these columns (in any order, any sheet) will parse correctly.
