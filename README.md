# Khyzr AI Agent Platform

> **46 production-ready AI agents** across 5 business domains, built on [AWS Strands Agents SDK](https://github.com/aws/strands-agents) + Amazon Bedrock (Claude Sonnet).

---

## 🏗️ Architecture

```
                        ┌─────────────────────────────────────┐
                        │        Khyzr Agent Platform         │
                        │                                     │
  Input Event           │  ┌──────────┐    ┌──────────────┐  │
  (API/Schedule) ──────▶│  │  Agent   │───▶│  Strands SDK │  │
                        │  │ (Lambda) │    │  + Tools     │  │
                        │  └──────────┘    └──────┬───────┘  │
                        │                         │           │
                        │                ┌────────▼────────┐  │
                        │                │ Amazon Bedrock  │  │
                        │                │ Claude Sonnet   │  │
                        │                └────────┬────────┘  │
                        │                         │           │
                        │         ┌───────────────┼──────┐    │
                        │         ▼               ▼      ▼    │
                        │        S3             DynamoDB SES   │
                        └─────────────────────────────────────┘

  Infrastructure: Terraform → ECR + Lambda + CloudWatch + EventBridge
```

---

## 📋 All 46 Agents

### Domain 1: Executive Strategy (01–11)

| # | Agent | Description |
|---|-------|-------------|
| 01 | Market Intelligence | Monitors competitor news, SEC filings, and analyst reports; delivers daily briefings via email |
| 02 | Executive Reporting | Synthesizes cross-functional KPIs into board-ready executive dashboards |
| 03 | Strategy Document | Drafts strategic plans, OKR frameworks, and board decks from briefing inputs |
| 04 | Deal Sourcing | Identifies M&A targets, partnership opportunities, and investment candidates |
| 05 | Scenario Modeling | Builds quantitative scenarios (base/bull/bear) for strategic planning decisions |
| 06 | Briefing | Prepares executive briefing packages for meetings, site visits, and investor calls |
| 07 | OKR Tracking | Tracks objectives and key results across teams; flags at-risk goals weekly |
| 08 | ESG Reporting | Compiles ESG metrics and generates sustainability reports aligned to GRI/SASB |
| 09 | Risk Monitoring | Continuously monitors operational, financial, and regulatory risk signals |
| 10 | IR Communication | Drafts investor relations communications, earnings call scripts, and press releases |
| 11 | Audit Trail | Maintains immutable audit logs for compliance and governance processes |

### Domain 2: Sales & Marketing (12–23)

| # | Agent | Description |
|---|-------|-------------|
| 12 | Lead Scoring | Scores inbound leads using firmographic, behavioral, and engagement signals |
| 13 | SEO Content | Generates SEO-optimized content briefs and long-form articles targeting priority keywords |
| 14 | Email Personalization | Personalizes email campaigns at scale using CRM data and behavioral triggers |
| 15 | Social Media | Creates and schedules social media content across LinkedIn, Twitter, and Instagram |
| 16 | CRM Enrichment | Enriches CRM records with firmographic, technographic, and contact data |
| 17 | Battlecard | Generates competitive battlecards comparing products, pricing, and positioning |
| 18 | Sales Enablement | Creates sales playbooks, objection handling guides, and deal-specific collateral |
| 19 | Ad Optimization | Optimizes paid ad campaigns by analyzing performance and adjusting bids/creatives |
| 20 | Churn Intelligence | Predicts churn risk scores and recommends retention interventions by account |
| 21 | ABM Intelligence | Drives account-based marketing plays with personalized insights for target accounts |
| 22 | Attribution | Models multi-touch marketing attribution across channels and campaigns |
| 23 | Sentiment Monitoring | Monitors brand sentiment across social, review sites, and news in real-time |

### Domain 3: Operations (24–35)

| # | Agent | Description |
|---|-------|-------------|
| 24 | Demand Forecasting | Forecasts product demand using historical patterns, seasonality, and external signals |
| 25 | Inventory Optimization | Optimizes inventory levels to minimize stockouts and excess carrying costs |
| 26 | Vendor Compliance | Monitors vendor compliance with contractual SLAs, certifications, and regulations |
| 27 | Project Management | Tracks project milestones, flags delays, and generates status reports |
| 28 | SOP Drafting | Generates and maintains standard operating procedures from process descriptions |
| 29 | Procurement | Automates RFQ/RFP workflows, vendor evaluation, and purchase requisitions |
| 30 | Scheduling Optimization | Optimizes staff and resource scheduling to minimize cost and maximize coverage |
| 31 | QC Monitoring | Monitors quality control metrics and triggers alerts on spec deviations |
| 32 | Logistics Coordination | Coordinates freight, shipping, and last-mile delivery workflows |
| 33 | Contract Management | Manages contract lifecycle: creation, negotiation tracking, renewal alerts |
| 34 | Support Automation | Automates Tier-1 customer support with AI-powered ticket routing and resolution |
| 35 | Process Intelligence | Analyzes workflow data to identify throughput bottlenecks and improve efficiency |

### Domain 4: Finance & Accounting (36–41)

| # | Agent | Description |
|---|-------|-------------|
| 36 | AP Automation | Extracts invoice data, matches POs, flags discrepancies, routes for approval |
| 37 | Financial Reporting | Pulls GL data and auto-generates income statements, balance sheets, cash flow statements |
| 38 | Investment Analysis | Models ROI, NPV, and IRR for potential investments with sensitivity analysis |
| 39 | Expense Audit | Scans expense submissions against policy rules, detects duplicates and anomalies |
| 40 | AR Collections | Monitors aging AR, generates collection emails, escalates by risk tier |
| 41 | Cash Flow | Synthesizes AR/AP schedules to produce rolling 13-week cash flow forecasts |

### Domain 5: Healthcare (42–46)

| # | Agent | Description |
|---|-------|-------------|
| 42 | Scheduling Automation | Manages appointment booking, reminders, and rescheduling to reduce no-shows |
| 43 | Medical Coding | Reviews clinical notes and assigns accurate ICD-10 and CPT codes |
| 44 | Clinical Documentation | Generates structured SOAP notes and discharge summaries from visit transcripts |
| 45 | Patient Intake | Collects demographics, verifies insurance eligibility, pre-populates EHR fields |
| 46 | Revenue Cycle | Identifies denied claims, determines root cause, generates corrected resubmissions |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- AWS CLI configured (`aws configure`)
- Terraform >= 1.5.0
- Docker
- Bedrock model access enabled (Claude Sonnet)

### Test an Agent Locally
```bash
# Clone the repo
git clone <repo-url>
cd khyzr-agents

# Install dependencies for an agent
pip install -r agents/36-ap-automation-agent/requirements.txt

# Run with test input
echo '{"message": "Process invoice INV-2024-001"}' | \
  python agents/36-ap-automation-agent/src/agent.py

# Or use the test script
./scripts/test-agent.sh agents/36-ap-automation-agent \
  '{"message": "Process invoice INV-2024-001"}'
```

### Deploy All Agents to AWS
```bash
# Deploy all 46 agents via Terraform
./scripts/deploy-all.sh

# Or manually
cd infra
terraform init
terraform plan
terraform apply
```

### Deploy a Single Agent
```bash
./scripts/deploy-agent.sh agents/01-market-intelligence-agent
```

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Agent Framework | [AWS Strands Agents SDK](https://github.com/aws/strands-agents) |
| LLM | Amazon Bedrock — Claude Sonnet 4.5 |
| Runtime | Python 3.11, Docker |
| Infrastructure | Terraform + AWS Lambda + ECR |
| Scheduling | Amazon EventBridge |
| Storage | Amazon S3, DynamoDB |
| Messaging | Amazon SES, SNS |
| Monitoring | Amazon CloudWatch |

---

## 📁 Repository Structure

```
khyzr-agents/
├── agents/                          # 46 agent implementations
│   ├── 01-market-intelligence-agent/
│   │   ├── src/agent.py            # Strands agent implementation
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── infra/main.tf           # Per-agent Terraform
│   │   └── docs/README.md
│   └── ... (46 total)
├── infra/                           # Root Terraform (all 46 agents)
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── modules/bedrock-agent/      # Reusable Bedrock module
├── scripts/
│   ├── deploy-all.sh
│   ├── deploy-agent.sh
│   └── test-agent.sh
├── .kiro/steering/                  # Kiro IDE steering files
├── README.md
└── DEPLOYMENT.md
```

---

## 🔧 Agent Development Pattern

Every agent follows this standard structure:

```python
# src/agent.py
from strands import Agent, tool
from strands.models import BedrockModel

@tool
def my_tool(param: str) -> str:
    """Tool description for the LLM."""
    # Implementation
    return json.dumps(result)

SYSTEM_PROMPT = """You are the [Agent Name] for Khyzr..."""

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(model=model, tools=[my_tool], system_prompt=SYSTEM_PROMPT)

def run(input_data: dict) -> dict:
    """Main entry point."""
    response = agent(input_data.get("message", "Run default task"))
    return {"result": str(response)}
```

---

## 🌍 Environment Variables

All agents support these core environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-sonnet-4-5` | Bedrock model to use |
| `AWS_REGION` | `us-east-1` | AWS region |
| `ENVIRONMENT` | `prod` | Deployment environment |

See each agent's `docs/README.md` for agent-specific environment variables.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-new-agent`
3. Follow the agent pattern in `src/agent.py`
4. Add Terraform in `infra/main.tf`
5. Document in `docs/README.md`
6. Submit a pull request

### Agent Checklist
- [ ] `src/agent.py` with `run(input_data)` entry point
- [ ] 3-5 `@tool` decorated functions with realistic implementations
- [ ] System prompt: 200-400 words, role-specific
- [ ] `Dockerfile` using `python:3.11-slim`
- [ ] `requirements.txt` with all dependencies
- [ ] `infra/main.tf` with Lambda + ECR + IAM
- [ ] `docs/README.md` with inputs/outputs/examples

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built with ❤️ using AWS Strands Agents SDK + Amazon Bedrock*
