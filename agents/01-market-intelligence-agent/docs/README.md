# Market Intelligence Agent

**Category:** Executive Strategy  
**Use Case:** Competitive Intelligence Monitoring  
**Agent:** Market Intelligence Agent

---

## What It Does

The Market Intelligence Agent continuously monitors competitors by:

- Searching recent news articles (via NewsAPI)
- Querying SEC EDGAR for material filings (8-K, 10-K, 10-Q)
- Synthesizing findings into a structured executive briefing
- Storing the report to S3 for downstream consumption
- **Emailing the briefing to a configured list of recipients via AWS SES**

It runs on a schedule (default: daily) via EventBridge, or can be invoked on-demand.

---

## Architecture

```
EventBridge (Schedule)
        │
        ▼
   Lambda Function
   (market-intelligence-agent)
        │
        ├── Tool: search_news()                    → NewsAPI.org
        ├── Tool: search_sec_filings()             → SEC EDGAR (free, no key)
        ├── Tool: summarize_competitive_landscape()
        ├── Tool: store_intelligence_report()      → S3
        └── Tool: send_briefing_email()            → AWS SES → Recipients
        │
        ▼
  Bedrock (Claude Sonnet)
  ← reasons across tool results →
        │
        ▼
   S3 Bucket + 📧 Email Inboxes
```

### Components

| Resource | Type | Purpose |
|---|---|---|
| `market-intelligence-agent-{env}` | Lambda | Agent runtime |
| `market-intelligence-reports-{env}-{acct}` | S3 | Report storage |
| `market-intelligence-agent-{env}` | ECR | Container image |
| `market-intelligence-agent-daily-{env}` | EventBridge Rule | Scheduled trigger |
| `/market-intelligence-agent/NEWS_API_KEY` | SSM SecureString | API key storage |
| SES verified identity | SES | Email delivery |

---

## Prerequisites

1. **AWS Account** with Bedrock access enabled
2. **Bedrock model access** — request access to `anthropic.claude-sonnet-4-5` in the AWS Console → Bedrock → Model access
3. **Docker** installed locally (for building the container)
4. **Terraform** >= 1.5 installed
5. **AWS CLI** configured with sufficient permissions
6. **SES verified sender** — verify your sender email in AWS Console → SES → Verified identities *(required for email delivery)*
7. *(Optional)* **NewsAPI key** — free tier at https://newsapi.org (500 req/day). Without it, only SEC filings are searched.

> ⚠️ **SES Sandbox**: New AWS accounts are in SES sandbox mode, meaning you can only send to verified email addresses. To send to any address, request production access in the SES console.

---

## Deployment

### Step 1 — Clone and configure

```bash
cd agents/01-market-intelligence-agent
```

Edit `infra/terraform.tfvars`:

```hcl
aws_region          = "us-east-1"
environment         = "prod"
default_competitors = "[\"Tesla\", \"Rivian\", \"Lucid\"]"
briefing_recipients = "ceo@yourcompany.com,cto@yourcompany.com,strategy@yourcompany.com"
ses_sender_email    = "intelligence@yourcompany.com"   # Must be SES-verified
news_api_key        = "your_key_here"                  # Optional but recommended
```

### Step 2 — Deploy infrastructure

```bash
cd infra
terraform init
terraform plan
terraform apply
```

Note the outputs — you'll need `ecr_repository_url` for the next step.

### Step 3 — Build and push the container

```bash
# Get ECR URL from terraform output
ECR_URL=$(terraform output -raw ecr_repository_url)
AWS_REGION="us-east-1"
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

# Authenticate Docker to ECR
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_URL

# Build and push
cd ..
docker build -t market-intelligence-agent .
docker tag market-intelligence-agent:latest $ECR_URL:latest
docker push $ECR_URL:latest
```

### Step 4 — Update Lambda with the new image

```bash
aws lambda update-function-code \
  --function-name market-intelligence-agent-prod \
  --image-uri $ECR_URL:latest \
  --region us-east-1
```

### Step 5 — Test it

```bash
aws lambda invoke \
  --function-name market-intelligence-agent-prod \
  --payload '{"competitors":["Tesla","Rivian"],"topic":"product launches","days_back":7}' \
  --cli-binary-format raw-in-base64-out \
  response.json

cat response.json
```

---

## Invocation Payload

```json
{
  "competitors": ["Company A", "Company B"],
  "recipients": ["exec@company.com", "cto@company.com"],
  "topic": "product launches and partnerships",
  "days_back": 7
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `competitors` | string[] | ✅ | List of competitor names to monitor |
| `recipients` | string[] | ❌ | Override email recipients (falls back to `BRIEFING_RECIPIENTS` env var) |
| `topic` | string | ❌ | Focus area (default: general strategy) |
| `days_back` | integer | ❌ | News lookback window in days (default: 7) |

---

## Output

Reports are stored in S3 at:
```
s3://market-intelligence-reports-{env}-{account}/reports/{timestamp}-{name}.md
```

Example report structure:
```markdown
# Competitive Intelligence Briefing — 2025-03-09

## Key Moves
- **Tesla**: Announced price cuts on Model Y...
- **Rivian**: 🚨 Filed 8-K disclosing $1.2B equity raise...

## Market Shifts
...

## Threats
...

## Opportunities
...

## Recommended Actions
...
```

---

## Scheduling

The agent runs daily by default. To change the schedule, update `terraform.tfvars`:

```hcl
# Every weekday at 6 AM UTC
schedule_expression = "cron(0 6 ? * MON-FRI *)"

# Twice daily
schedule_expression = "rate(12 hours)"
```

Then run `terraform apply`.

---

## Costs (Estimated)

| Resource | Estimated Monthly Cost |
|---|---|
| Lambda (300s × 30 runs) | ~$0.05 |
| Bedrock (Claude Sonnet, ~5K tokens/run) | ~$4.50 |
| S3 (storage + requests) | ~$0.10 |
| ECR (image storage) | ~$0.10 |
| **Total** | **~$5/month** |

*Costs vary based on competitor count and token usage.*

---

## Extending the Agent

To add more data sources, create a new `@tool` function in `src/agent.py`:

```python
@tool
def search_linkedin_posts(company: str) -> str:
    """Search LinkedIn for company posts and announcements."""
    # Your implementation
    ...
```

Then add it to the `tools=[]` list in `create_agent()`.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `ResourceNotFoundException` on Bedrock | Request model access in AWS Console → Bedrock → Model access |
| Lambda timeout | Increase `timeout` in `main.tf` (max 900s) or reduce competitor list |
| S3 access denied | Ensure Lambda IAM role has `s3:PutObject` on the reports bucket |
| No news results | Set `NEWS_API_KEY` in SSM at `/market-intelligence-agent/NEWS_API_KEY` |
| Cold start slow | Set Lambda provisioned concurrency for scheduled runs |
| Email not delivered | Verify sender in SES console; if in sandbox, verify recipient addresses too |
| `MessageRejected` from SES | Sender address not verified — go to SES → Verified identities |
| Email goes to spam | Set up SPF/DKIM records for your sending domain in SES |
