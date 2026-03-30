# Khyzr Agents — API Gateway + Lambda Proxy

A serverless HTTP API that lets any website (including Replit) talk to Khyzr's
three deployed AgentCore runtimes **without needing AWS credentials**.

---

## How it works

```
Browser / Replit
     │
     │  POST /chat  (JSON, no auth required)
     ▼
API Gateway v2 (HTTP API)
     │
     │  AWS_PROXY integration
     ▼
Lambda: khyzr-agents-api
     │
     │  boto3  (IAM role handles auth)
     ▼
AgentCore runtime (market-intelligence | ap-automation | ar-collections)
```

The Lambda's IAM role (`khyzr-agents-api-role`) holds the credentials.
Your frontend sends a plain HTTPS POST — no AWS SDK or credentials required.

---

## Deploy

### Prerequisites

- AWS credentials in environment (`AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`)
- Terraform at `/workspace/bin/terraform` or on `$PATH`
- Python 3.x (used by deploy script for version check only)

### One-command deploy

```bash
./deploy.sh api
```

This will:
1. Zip `api/lambda/handler.py` → `api/lambda/handler.zip`
2. Run `terraform init` in `api/infra/`
3. Run `terraform apply` — creates IAM role, Lambda, API Gateway
4. Print the live endpoint URL

To deploy all agents **and** the API in one shot:

```bash
./deploy.sh all
```

---

## Endpoint

After deploying, Terraform outputs the URL:

```
https://{api-id}.execute-api.us-east-1.amazonaws.com/chat
```

Send all requests as `POST /chat` with a JSON body.

---

## Request / Response format

### Request body

```json
{
  "agent_id":   "market-intelligence",
  "message":    "Your question here",
  "session_id": "optional-string-for-continuity"
}
```

| Field        | Required | Description                                               |
|--------------|----------|-----------------------------------------------------------|
| `agent_id`   | ✅       | One of `market-intelligence`, `ap-automation`, `ar-collections` |
| `message`    | ✅       | The user's question or instruction                        |
| `session_id` | ❌       | Reuse to maintain conversation context; auto-generated if omitted |

### Response body

```json
{
  "response":   "Agent reply text here",
  "agent_id":   "market-intelligence",
  "session_id": "abc123"
}
```

### Error response

```json
{
  "error": "Human-readable error message"
}
```

---

## Examples for all 3 agents

### 1. Market Intelligence (`market-intelligence`)

```json
POST /chat
{
  "agent_id": "market-intelligence",
  "message":  "Analyze Tesla's competitive position in the EV market",
  "session_id": "demo-session-01"
}
```

```json
{
  "response":   "Tesla holds approximately 18% of global EV market share...",
  "agent_id":   "market-intelligence",
  "session_id": "demo-session-01"
}
```

### 2. AP Automation (`ap-automation`)

```json
POST /chat
{
  "agent_id": "ap-automation",
  "message":  "Review this invoice: Vendor ACME Corp, $4,200, due 2026-04-15",
  "session_id": "ap-session-42"
}
```

```json
{
  "response":   "Invoice reviewed. ACME Corp is an approved vendor. Amount $4,200 is within auto-approval threshold...",
  "agent_id":   "ap-automation",
  "session_id": "ap-session-42"
}
```

### 3. AR Collections (`ar-collections`)

```json
POST /chat
{
  "agent_id": "ar-collections",
  "message":  "Which customers have invoices overdue by more than 30 days?",
  "session_id": "ar-session-07"
}
```

```json
{
  "response":   "3 customers have invoices overdue 30+ days: Globex Corp ($12,400), Initech ($8,750)...",
  "agent_id":   "ar-collections",
  "session_id": "ar-session-07"
}
```

---

## Using from Replit (JavaScript)

Copy this snippet into your Replit project. Replace `YOUR_API_ENDPOINT` with
the URL from `./deploy.sh api` output.

```javascript
const API_ENDPOINT = 'https://YOUR_API_ENDPOINT/chat';

async function askAgent(agentId, message, sessionId = null) {
  const response = await fetch(API_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      agent_id:   agentId,   // 'market-intelligence' | 'ap-automation' | 'ar-collections'
      message:    message,
      session_id: sessionId  // optional — reuse to keep conversation context
    })
  });

  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.error || `HTTP ${response.status}`);
  }

  const data = await response.json();
  console.log(data.response); // the agent's reply
  return data;
}

// Examples
await askAgent('market-intelligence', 'Summarize recent EV market trends');
await askAgent('ap-automation',       'List pending invoices over $10,000');
await askAgent('ar-collections',      'Show overdue accounts', 'my-session-id');
```

---

## CORS

The API Gateway and Lambda both set `Access-Control-Allow-Origin: *`, so the
endpoint works from **any domain** — including Replit, localhost, CodeSandbox,
or any hosted website — without any proxy or workaround.

---

## Infrastructure overview

| Resource                    | Name / ID                        |
|-----------------------------|----------------------------------|
| IAM Role                    | `khyzr-agents-api-role`          |
| Lambda Function             | `khyzr-agents-api`               |
| API Gateway (HTTP)          | `khyzr-agents-api-gw`            |
| Route                       | `POST /chat`                     |
| Lambda runtime              | Python 3.12                      |
| Timeout / Memory            | 60 s / 256 MB                    |
| CloudWatch Log Group        | `/aws/lambda/khyzr-agents-api`   |

---

## Re-deploy after code changes

```bash
./deploy.sh api
```

Terraform's `archive_file` data source detects changes to `handler.py` via
SHA-256 and automatically updates the Lambda function.
