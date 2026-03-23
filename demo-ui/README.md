# Khyzr Agents — Demo UI

A lightweight local web interface for chatting with all deployed AgentCore agents.

## Deployed Agents

| # | Agent | Domain | ARN |
|---|-------|--------|-----|
| 01 | Market Intelligence | Executive Strategy | `khyzr_market_intelligence_demo-IXK91q23u1` |
| 36 | AP Automation | Finance & Accounting | `khyzr_ap_automation_demo-yXLiHZ39Ob` |
| 40 | AR Collections | Finance & Accounting | `khyzr_ar_collections_demo-HZchkDGBs5` |

## Running

**Prerequisites:** AWS credentials with `bedrock-agentcore:InvokeAgentRuntime` permission.

```bash
cd demo-ui

# Set AWS credentials
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...

# Run (no dependencies needed — pure Python stdlib + boto3)
python3 server.py
```

Open http://localhost:8080

## Demo Prompts

**Market Intelligence (Agent 01)**
```
Run a competitive briefing on OpenAI and Anthropic — search recent news and summarize key moves.
```

**AP Automation (Agent 36)**
```
Process invoice INV-2024-08821 from Apex Supply Co — extract data, match PO-2024-00312, flag discrepancies, route for approval.
```

**AR Collections (Agent 40)**
```
Fetch the aging AR report from s3://khyzr-ar-collections-demo-reports-110276528370/reports/aging-report-demo.json and give me a risk-tiered summary with recommended actions.
```

## Architecture

- Pure Python stdlib HTTP server — no Flask/FastAPI needed
- Proxies prompts directly to AgentCore `InvokeAgentRuntime` API
- Single-file SPA (HTML/CSS/JS inlined in server.py)
- Per-agent conversation history (client-side)
