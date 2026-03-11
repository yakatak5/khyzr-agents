# Audit Trail Documentation Agent

**Category:** Finance & Accounting (#11)
**Use Case:** Audit Trail Documentation
**Agent:** Audit Readiness Agent

---

## What It Does

The Audit Trail Documentation Agent compiles complete, audit-ready packages by:

- Querying the general ledger / transaction database for a specified period
- Retrieving supporting documents (invoices, receipts, approvals) from S3
- Assessing internal controls: approvals, PO matching, segregation of duties, anomaly detection
- Compiling everything into a structured markdown audit package stored in S3
- Emailing the package to auditors and finance leadership via AWS SES

Runs automatically on the 1st of each month, or on-demand for any period.

---

## Architecture

```
EventBridge (Monthly — 1st of month, 6 AM UTC)
        │
        ▼
   Lambda Function
   (audit-trail-agent)
        │
        ├── Tool: query_transactions()         → GL / RDS / Athena / ERP
        ├── Tool: list_supporting_documents()  → S3 (supporting-docs/)
        ├── Tool: assess_control_evidence()    → Internal logic + rules engine
        ├── Tool: compile_audit_package()      → S3 (packages/)
        └── Tool: send_audit_package_email()   → AWS SES → Auditors
        │
        ▼
  Bedrock (Claude Sonnet)
  ← reasons, flags exceptions, writes narrative →
        │
        ▼
   S3: audit-trail-packages-{env}-{account}
   📧 Email: auditors + finance leadership
```

### Components

| Resource | Type | Purpose |
|---|---|---|
| `audit-trail-agent-{env}` | Lambda | Agent runtime |
| `audit-trail-packages-{env}-{acct}` | S3 | Package + doc storage |
| `audit-trail-agent-{env}` | ECR | Container image |
| `audit-trail-agent-monthly-{env}` | EventBridge Rule | Monthly trigger |
| `/audit-trail-agent/*` | SSM SecureString | DB credentials / API keys |

---

## Prerequisites

1. **AWS Account** with Bedrock model access (`anthropic.claude-sonnet-4-5`)
2. **Docker**, **Terraform >= 1.5**, **AWS CLI** configured
3. **SES verified sender email** (AWS Console → SES → Verified identities)
4. *(Production)* Connect `query_transactions()` to your real data source — see **Connecting Your GL Data** below

---

## Deployment

### Step 1 — Configure

Edit `infra/terraform.tfvars`:

```hcl
aws_region       = "us-east-1"
environment      = "prod"
audit_recipients = "auditor@firm.com,cfo@yourcompany.com"
ses_sender_email = "audit-agent@yourcompany.com"
```

### Step 2 — Deploy infrastructure

```bash
cd infra
terraform init
terraform plan
terraform apply
```

### Step 3 — Build and push container

```bash
ECR_URL=$(terraform output -raw ecr_repository_url)
AWS_REGION="us-east-1"

aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_URL

cd ..
docker build -t audit-trail-agent .
docker tag audit-trail-agent:latest $ECR_URL:latest
docker push $ECR_URL:latest

aws lambda update-function-code \
  --function-name audit-trail-agent-prod \
  --image-uri $ECR_URL:latest
```

### Step 4 — Test

```bash
aws lambda invoke \
  --function-name audit-trail-agent-prod \
  --payload '{
    "audit_period": "Q4 2024",
    "start_date": "2024-10-01",
    "end_date": "2024-12-31",
    "transaction_types": ["INVOICE", "PAYMENT", "JOURNAL"]
  }' \
  --cli-binary-format raw-in-base64-out \
  response.json

cat response.json
```

---

## Invocation Payload

```json
{
  "audit_period": "Q4 2024",
  "start_date": "2024-10-01",
  "end_date": "2024-12-31",
  "account_codes": ["1000", "2000", "4000", "5100"],
  "min_amount": 1000,
  "transaction_types": ["INVOICE", "PAYMENT", "JOURNAL"],
  "recipients": ["auditor@firm.com", "cfo@company.com"]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `audit_period` | string | ✅ | Human-readable label (e.g. "Q4 2024") |
| `start_date` | string | ✅ | Period start in YYYY-MM-DD |
| `end_date` | string | ✅ | Period end in YYYY-MM-DD |
| `account_codes` | string[] | ❌ | Filter to specific GL accounts |
| `min_amount` | number | ❌ | Only include transactions ≥ this amount |
| `transaction_types` | string[] | ❌ | Filter by type: INVOICE, PAYMENT, JOURNAL |
| `recipients` | string[] | ❌ | Override email list (falls back to env var) |

---

## Control Checks

The agent automatically performs these control assessments on every transaction:

| Check | Risk if Failed |
|---|---|
| Approval signature present | 🔴 HIGH |
| Invoice has PO reference | 🟡 MEDIUM |
| Large journal entry (>$100K) has adequate description | 🔴 HIGH |
| Round-number amounts flagged for doc review | 🟡 MEDIUM |

Add custom rules in `assess_control_evidence()` in `src/agent.py`.

---

## Connecting Your GL Data

The `query_transactions()` tool ships with mock data. Replace it with your real source:

### Option A — Aurora Serverless (RDS Data API)

```python
rds = boto3.client("rds-data")
response = rds.execute_statement(
    resourceArn="arn:aws:rds:...",
    secretArn="arn:aws:secretsmanager:...",
    database="general_ledger",
    sql="SELECT * FROM transactions WHERE date BETWEEN :start AND :end",
    parameters=[
        {"name": "start", "value": {"stringValue": start_date}},
        {"name": "end",   "value": {"stringValue": end_date}},
    ]
)
```

### Option B — Athena (S3-backed data lake)

```python
athena = boto3.client("athena")
athena.start_query_execution(
    QueryString=f"SELECT * FROM gl.transactions WHERE txn_date BETWEEN '{start_date}' AND '{end_date}'",
    ResultConfiguration={"OutputLocation": "s3://your-athena-results/"}
)
```

### Option C — ERP API (QuickBooks, NetSuite, SAP)

Replace the function body with an `httpx.get()` call to your ERP's REST API, authenticating via SSM-stored credentials.

---

## Output

Audit packages are stored at:
```
s3://audit-trail-packages-{env}-{account}/packages/{timestamp}-{name}.md
```

Supporting docs are expected at:
```
s3://audit-trail-packages-{env}-{account}/supporting-docs/{TXN-ID}/
```

---

## Costs (Estimated)

| Resource | Estimated Monthly Cost |
|---|---|
| Lambda (600s × 1 scheduled run) | ~$0.01 |
| Bedrock (Claude Sonnet, ~8K tokens/run) | ~$0.72 |
| S3 (storage + Glacier archive) | ~$0.05 |
| SES (email sends) | ~$0.01 |
| **Total** | **~$1/month** |

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `ResourceNotFoundException` on Bedrock | Enable model access in AWS Console → Bedrock |
| S3 access denied | Check Lambda IAM has `s3:PutObject` and `s3:ListBucket` on audit bucket |
| Empty transaction results | Replace mock data in `query_transactions()` with real GL integration |
| Email not sent | Verify SES sender; check SES sandbox status |
| Lambda timeout | Increase `timeout` in Terraform (max 900s) for large audit periods |
