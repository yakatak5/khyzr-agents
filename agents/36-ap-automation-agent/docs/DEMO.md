# AP Automation Agent — Demo Guide

## What This Agent Does

End-to-end accounts payable automation:

1. **Extracts** invoice data from PDFs/Excel/text (vendor, amounts, line items)
2. **Matches** against the purchase order (3-way match: PO ↔ Invoice ↔ Receipt)
3. **Flags** discrepancies with severity (critical/high/warning)
4. **Routes** to correct approver based on severity
5. **Records** everything in the AP ledger (DynamoDB)

---

## Deploy

> **Prerequisites:**
> - AWS credentials with AgentCore, DynamoDB, S3 permissions
> - Terraform ≥ 1.5.0
> - **No Docker required** — uses Code Zip (Direct Code Deployment)

```bash
cd agents/36-ap-automation-agent/infra
terraform init -upgrade
terraform plan -out=tfplan
terraform apply tfplan
```

Takes ~1 minute. Terraform will:

- ✅ Zip `src/agent.py` + `requirements.txt` into `agent.zip`
- ✅ Upload `agent.zip` to a dedicated S3 code bucket
- ✅ Create AgentCore Runtime pointing at the S3 code artifact
- ✅ Create DynamoDB table (AP ledger)
- ✅ Create S3 bucket (invoice storage + demo invoice pre-loaded)
- ✅ Create IAM role with least-privilege permissions

> **Note:** No Docker, no ECR, no buildx needed. `terraform apply` handles everything automatically via `data "archive_file"` + `aws_s3_object`.

---

## Run the Demo

After `terraform apply` completes, copy the `demo_invoke_command` from the Terraform outputs and run it directly.

### Python SDK

```python
import boto3, json

client = boto3.client("bedrock-agentcore", region_name="us-east-1")
response = client.invoke_agent_runtime(
    agentRuntimeArn="<AGENT_RUNTIME_ARN>",   # from terraform output agent_runtime_arn
    payload=json.dumps({
        "prompt": "Process the demo invoice INV-2024-08821 — extract all data, match against the PO, flag any discrepancies, route for approval, and update the ledger."
    }).encode()
)
# Response is streaming
chunks = [c.get("chunk", b"") for c in response.get("body", [])]
print(b"".join(chunks).decode())
```

### AWS CLI

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <AGENT_RUNTIME_ARN> \
  --payload '{"prompt": "Process invoice INV-2024-08821 — extract data, match PO, flag discrepancies, route for approval, update ledger."}' \
  --region us-east-1
```

### Excel Invoice Demo

```bash
# Copy the excel_demo_command from terraform output and run it, or:
python3 -c "
import boto3, json
client = boto3.client('bedrock-agentcore', region_name='us-east-1')
response = client.invoke_agent_runtime(
    agentRuntimeArn='<AGENT_RUNTIME_ARN>',
    payload=json.dumps({
        'prompt': 'Process the Excel invoice at s3://<INVOICES_BUCKET>/invoices/INV-2024-08821.xlsx — extract data, match PO, flag discrepancies, route for approval, update ledger.'
    }).encode()
)
chunks = [c.get('chunk', b'') for c in response.get('body', [])]
print(b''.join(chunks).decode())
"
```

---

## Expected Output

The agent will call all 5 tools in sequence:

| Step | Tool | Expected Result |
|------|------|-----------------|
| 1 | `extract_invoice_data` | Vendor: Apex Supply Co., Total: $13,446.00, 2 line items |
| 2 | `match_purchase_order` | 3-way match against PO-2024-00312, 0% variance |
| 3 | `flag_discrepancies` | Status: `approved_for_payment`, 0 discrepancies |
| 4 | `route_for_approval` | Assigned to AP Clerk (clean invoice) |
| 5 | `update_ap_ledger` | Transaction recorded in DynamoDB, GL account 2000-AP |

Check DynamoDB to confirm the ledger entry:

```bash
aws dynamodb scan \
  --table-name $(terraform -chdir=infra output -raw dynamodb_table_name) \
  --region us-east-1 \
  --output json | python3 -m json.tool
```

---

## Test Scenarios

### Scenario 1 — Clean Invoice (Happy Path)

> **Prompt:** `"Process invoice INV-2024-08821"`

**Expected:**
- ✅ Matches PO-2024-00312 exactly (0% variance)
- ✅ Status: `approved_for_payment`
- ✅ Routed to AP Clerk
- ✅ Ledger entry written to DynamoDB

---

### Scenario 2 — Price Discrepancy

> **Prompt:** `"Process invoice INV-2024-09999 with total $15,000 against PO-2024-00312 which was approved for $12,450"`

**Expected:**
- ⚠️ Flags `PRICE_VARIANCE_HIGH` (20.5% over PO amount)
- 🛑 Status: `hold`
- 📧 Routed to AP Controller (urgent priority)
- 📋 Ledger entry with status `pending`

---

### Scenario 3 — Fraud Signal (Vendor Mismatch)

> **Prompt:** `"Process invoice from vendor VND-9999 referencing PO-2024-00312 which belongs to vendor VND-4492"`

**Expected:**
- 🚨 Flags `VENDOR_MISMATCH` as **critical**
- 🛑 Status: `hold` — payment blocked
- 📧 Routed to AP Controller immediately
- 📋 Ledger entry flagged for fraud review

---

## Architecture

```
User / CLI / SDK
       │
       │  invoke_agent_runtime (payload: {"prompt": "..."})
       ▼
AgentCore Runtime (Code Zip on bedrock-agentcore.amazonaws.com)
       │
       │  Strands Agent orchestrates tool calls (Claude Sonnet)
       ▼
   agent.py (BedrockAgentCoreApp)
       ├── extract_invoice_data  → parses invoice (S3 fetch + Excel/text)
       ├── match_purchase_order  → 3-way match logic
       ├── flag_discrepancies    → severity classification
       ├── route_for_approval    → role-based routing
       └── update_ap_ledger      → DynamoDB write
               │
               ▼
           DynamoDB (AP Ledger)
           S3 (Invoice Storage)
```

---

## File Structure

```
agents/36-ap-automation-agent/
├── src/
│   ├── agent.py              # BedrockAgentCoreApp + all 5 tool functions
│   └── demo_invoice.xlsx     # Demo Excel invoice (pre-loaded to S3 by Terraform)
├── infra/
│   └── main.tf               # Terraform — AgentCore + S3 code bucket + DynamoDB + S3 + IAM
├── docs/
│   └── DEMO.md               # This file
└── requirements.txt          # Python dependencies (includes bedrock-agentcore)
```

---

## Redeploy After Code Changes

When `agent.py` or `requirements.txt` changes, just re-run:

```bash
cd agents/36-ap-automation-agent/infra
terraform apply
```

Terraform detects the file hash change, rebuilds the zip, uploads it to S3, and updates the AgentCore Runtime automatically. No Docker required. Takes ~10 seconds.

---

## Teardown

```bash
cd agents/36-ap-automation-agent/infra
terraform destroy
```

Removes all AWS resources. No ongoing costs after destroy.

> **Note:** `force_destroy = true` is set on all S3 buckets, so Terraform will clean them up automatically.

---

## Troubleshooting

**"ResourceNotFoundException" on DynamoDB write**
→ The env var `AP_LEDGER_TABLE` must match the actual table name. Verify:
```bash
terraform -chdir=infra output dynamodb_table_name
```

**"AccessDeniedException" invoking Bedrock model**
→ Ensure `us.anthropic.claude-3-5-sonnet-20241022-v2:0` is enabled in your account under **Bedrock → Model access**.

**"Invalid payload" error**
→ Make sure the payload is JSON-encoded bytes with a `"prompt"` key:
```python
payload=json.dumps({"prompt": "your message here"}).encode()
```

**Check AgentCore logs**
```bash
aws logs tail /aws/bedrock-agentcore/$(terraform -chdir=infra output -raw agent_runtime_id) --follow
```
