# AP Automation Agent — Demo Guide

## What This Agent Does

End-to-end accounts payable automation:

1. **Extracts** invoice data from PDFs/text (vendor, amounts, line items)
2. **Matches** against the purchase order (3-way match: PO ↔ Invoice ↔ Receipt)
3. **Flags** discrepancies with severity (critical/high/warning)
4. **Routes** to correct approver based on severity
5. **Records** everything in the AP ledger (DynamoDB)

---

## Deploy

```bash
cd agents/36-ap-automation-agent/infra
terraform init
terraform apply
```

Takes ~3 minutes. Deploys:

- ✅ Bedrock Agent with Claude Sonnet
- ✅ Lambda function (action group tools)
- ✅ DynamoDB table (AP ledger)
- ✅ S3 bucket (invoice storage + demo invoice pre-loaded)
- ✅ IAM roles and permissions
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
  --input-text "Process the demo invoice INV-2024-08821 — extract all data, match against the PO, flag any discrepancies, route for approval, and update the ledger." \
  --cli-binary-format raw-in-base64-out \
  outfile.json && cat outfile.json
```

### AWS Console

1. Go to **Amazon Bedrock → Agents**
2. Find `khyzr-ap-automation-demo`
3. Click **Test**
4. Type: *"Process invoice INV-2024-08821 — extract data, match the PO, flag discrepancies, route for approval, and update the ledger"*

---

## Expected Output

The agent will call all 5 tools in sequence:

| Step | Tool | Expected Result |
|------|------|-----------------|
| 1 | `extract-invoice-data` | Vendor: Apex Supply Co., Total: $13,446.00, 2 line items |
| 2 | `match-purchase-order` | 3-way match against PO-2024-00312, 0% variance |
| 3 | `flag-discrepancies` | Status: `approved_for_payment`, 0 discrepancies |
| 4 | `route-for-approval` | Assigned to AP Clerk (clean invoice) |
| 5 | `update-ap-ledger` | Transaction recorded in DynamoDB, GL account 2000-AP |

Check DynamoDB to confirm the ledger entry:

```bash
aws dynamodb scan \
  --table-name khyzr-ap-automation-demo-ledger \
  --region us-east-1 \
  --output json | python3 -m json.tool
```

---

## Test Scenarios

### Scenario 1 — Clean Invoice (Happy Path)

> **Prompt:** "Process invoice INV-2024-08821"

**Expected:**
- ✅ Matches PO-2024-00312 exactly (0% variance)
- ✅ Status: `approved_for_payment`
- ✅ Routed to AP Clerk
- ✅ Ledger entry written to DynamoDB

---

### Scenario 2 — Price Discrepancy

> **Prompt:** "Process invoice INV-2024-09999 with total $15,000 against PO-2024-00312 which was approved for $12,450"

**Expected:**
- ⚠️ Flags `PRICE_VARIANCE_HIGH` (20.5% over PO amount)
- 🛑 Status: `hold`
- 📧 Routed to AP Controller (urgent priority)
- 📋 Ledger entry with status `pending`

---

### Scenario 3 — Fraud Signal (Vendor Mismatch)

> **Prompt:** "Process invoice from vendor VND-9999 referencing PO-2024-00312 which belongs to vendor VND-4492"

**Expected:**
- 🚨 Flags `VENDOR_MISMATCH` as **critical**
- 🛑 Status: `hold` — payment blocked
- 📧 Routed to AP Controller immediately
- 📋 Ledger entry flagged for fraud review

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
    ├── /extract-invoice-data  → parses invoice (+ S3 fetch)
    ├── /match-purchase-order  → 3-way match logic
    ├── /flag-discrepancies    → severity classification
    ├── /route-for-approval    → role-based routing
    └── /update-ap-ledger      → DynamoDB write
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
│   ├── agent.py          # Lambda handler + all 5 tool functions
│   └── openapi.json      # OpenAPI schema for Bedrock Action Group
├── infra/
│   ├── main.tf           # Full Terraform — Bedrock + Lambda + DynamoDB + S3 + IAM
│   └── terraform.tfvars  # Default variable values
├── docs/
│   └── DEMO.md           # This file
├── requirements.txt      # Python dependencies
└── Dockerfile            # Container build (for local testing)
```

---

## Teardown

```bash
cd agents/36-ap-automation-agent/infra
terraform destroy
```

Removes all AWS resources. No ongoing costs after destroy.

> **Note:** `force_destroy = true` is set on S3 buckets, so Terraform will empty them automatically before deletion.

---

## Troubleshooting

**"ResourceNotFoundException" on DynamoDB write**
→ The Lambda env var `AP_LEDGER_TABLE` must match the actual table name. Verify with:
```bash
terraform output dynamodb_table_name
```

**Agent returns no tool calls**
→ The agent alias must point to a prepared version. Terraform creates the alias automatically; if you modify the agent in the console, click **Prepare** before testing.

**"AccessDeniedException" invoking Bedrock model**
→ Ensure the foundation model `anthropic.claude-sonnet-4-5-v1:0` is enabled in your AWS account under **Bedrock → Model access**.
