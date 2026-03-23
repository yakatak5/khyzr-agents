#!/bin/bash
# deploy-agent.sh — Deploy a single Khyzr agent and print all test endpoints
# Usage: ./scripts/deploy-agent.sh <agent-directory> [environment]
# Example: ./scripts/deploy-agent.sh agents/36-ap-automation-agent
# Example: ./scripts/deploy-agent.sh agents/36-ap-automation-agent prod

set -e

AGENT_DIR="${1:-}"
ENVIRONMENT="${2:-demo}"

# ── Resolve agent directory ──────────────────────────────────────────────────
if [ -z "$AGENT_DIR" ]; then
  echo "❌ Usage: $0 <agent-directory> [environment]"
  echo ""
  echo "Examples:"
  echo "  $0 agents/36-ap-automation-agent"
  echo "  $0 agents/39-expense-audit-agent prod"
  echo ""
  echo "Available agents:"
  ls agents/ | sed 's/^/  /'
  exit 1
fi

# Strip trailing slash
AGENT_DIR="${AGENT_DIR%/}"

if [ ! -d "$AGENT_DIR/infra" ]; then
  echo "❌ No infra/ directory found in $AGENT_DIR"
  exit 1
fi

AGENT_NAME=$(basename "$AGENT_DIR")

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Deploying: $AGENT_NAME"
echo "║  Environment: $ENVIRONMENT"
echo "║  Directory: $AGENT_DIR/infra"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Pre-flight checks ────────────────────────────────────────────────────────
echo "🔍 Running pre-flight checks..."

# Check AWS credentials
if ! aws sts get-caller-identity > /tmp/aws_identity.json 2>&1; then
  echo "❌ AWS credentials not configured. Run: aws configure"
  exit 1
fi
ACCOUNT_ID=$(cat /tmp/aws_identity.json | python3 -c "import json,sys; print(json.load(sys.stdin)['Account'])")
echo "✅ AWS Account: $ACCOUNT_ID"

# Check Terraform
if ! terraform --version > /dev/null 2>&1; then
  echo "❌ Terraform not installed. See: https://developer.hashicorp.com/terraform/install"
  exit 1
fi
echo "✅ Terraform: $(terraform --version | head -1)"

echo ""

# ── Deploy ───────────────────────────────────────────────────────────────────
cd "$AGENT_DIR/infra"

echo "📦 Initializing Terraform..."
terraform init -upgrade -input=false 2>&1 | tail -3

echo ""
echo "📋 Planning..."
terraform plan \
  -var="environment=$ENVIRONMENT" \
  -out=tfplan \
  -input=false \
  -compact-warnings 2>&1 | tail -10

echo ""
echo "🚀 Applying..."
terraform apply \
  -input=false \
  -compact-warnings \
  tfplan

# ── Capture outputs ──────────────────────────────────────────────────────────
echo ""
echo "📤 Capturing outputs..."
OUTPUTS=$(terraform output -json 2>/dev/null || echo "{}")

# Parse key outputs
AGENT_ID=$(echo "$OUTPUTS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('agent_id',{}).get('value','N/A'))" 2>/dev/null || echo "N/A")
ALIAS_ID=$(echo "$OUTPUTS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('agent_alias_id',{}).get('value','N/A'))" 2>/dev/null || echo "N/A")
LAMBDA_NAME=$(echo "$OUTPUTS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('lambda_function_name',{}).get('value','N/A'))" 2>/dev/null || echo "N/A")
DYNAMO_TABLE=$(echo "$OUTPUTS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('dynamodb_table_name',{}).get('value','N/A'))" 2>/dev/null || echo "N/A")
S3_BUCKET=$(echo "$OUTPUTS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('invoices_bucket',{}).get('value','N/A'))" 2>/dev/null || echo "N/A")
DEMO_CMD=$(echo "$OUTPUTS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('demo_invoke_command',{}).get('value','N/A'))" 2>/dev/null || echo "N/A")
REGION=$(terraform output -raw aws_region 2>/dev/null || echo "us-east-1")

# ── Print summary ─────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  ✅  $AGENT_NAME DEPLOYED"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "📌 Resources:"
[ "$AGENT_ID" != "N/A" ]    && echo "   🤖 Bedrock Agent ID : $AGENT_ID"
[ "$ALIAS_ID" != "N/A" ]    && echo "   🔗 Agent Alias ID   : $ALIAS_ID"
[ "$LAMBDA_NAME" != "N/A" ] && echo "   ⚡ Lambda Function  : $LAMBDA_NAME"
[ "$DYNAMO_TABLE" != "N/A" ] && echo "   🗄️  DynamoDB Table   : $DYNAMO_TABLE"
[ "$S3_BUCKET" != "N/A" ]   && echo "   🪣 S3 Bucket        : $S3_BUCKET"
echo ""

# ── Test commands ─────────────────────────────────────────────────────────────
if [ "$AGENT_ID" != "N/A" ] && [ "$ALIAS_ID" != "N/A" ]; then
  echo "🧪 Test via AWS CLI:"
  echo ""
  echo "   aws bedrock-agent-runtime invoke-agent \\"
  echo "     --agent-id $AGENT_ID \\"
  echo "     --agent-alias-id $ALIAS_ID \\"
  echo "     --session-id test-session-\$(date +%s) \\"
  echo "     --region ${REGION:-us-east-1} \\"
  echo "     --input-text \"Run a quick self-test and confirm you are operational.\" \\"
  echo "     --cli-binary-format raw-in-base64-out \\"
  echo "     /tmp/agent_response.json && cat /tmp/agent_response.json"
  echo ""
fi

if [ "$DEMO_CMD" != "N/A" ]; then
  echo "🎬 Full demo command:"
  echo ""
  echo "$DEMO_CMD" | sed 's/^/   /'
  echo ""
fi

echo "🖥️  Test via AWS Console:"
echo "   1. Go to: https://console.aws.amazon.com/bedrock/home?region=${REGION:-us-east-1}#/agents"
echo "   2. Click on: $AGENT_NAME"
echo "   3. Click 'Test' (top right)"
echo ""

if [ "$LAMBDA_NAME" != "N/A" ]; then
  echo "📋 View logs:"
  echo "   aws logs tail /aws/lambda/$LAMBDA_NAME --follow --region ${REGION:-us-east-1}"
  echo ""
fi

if [ "$DYNAMO_TABLE" != "N/A" ]; then
  echo "🗄️  Check DynamoDB records:"
  echo "   aws dynamodb scan --table-name $DYNAMO_TABLE --region ${REGION:-us-east-1}"
  echo ""
fi

echo "🗑️  Teardown when done:"
echo "   cd $AGENT_DIR/infra && terraform destroy -auto-approve"
echo ""

# ── Run smoke test ─────────────────────────────────────────────────────────────
if [ "$AGENT_ID" != "N/A" ] && [ "$ALIAS_ID" != "N/A" ]; then
  echo "⏳ Running smoke test..."
  sleep 3  # brief pause for alias propagation

  if aws bedrock-agent-runtime invoke-agent \
    --agent-id "$AGENT_ID" \
    --agent-alias-id "$ALIAS_ID" \
    --session-id "smoke-$(date +%s)" \
    --region "${REGION:-us-east-1}" \
    --input-text "Confirm you are operational with a one-sentence status." \
    --cli-binary-format raw-in-base64-out \
    /tmp/smoke_output.json 2>/tmp/smoke_err.json; then
    echo "✅ Smoke test passed"
    echo "   Response: $(cat /tmp/smoke_output.json | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    chunks=d.get('completion',{}).get('chunks',[])
    text=''.join(c.get('bytes','') for c in chunks if isinstance(c.get('bytes'),str))
    print(text[:200] if text else 'Agent responded (no text extracted)')
except:
    print('Agent responded successfully')
" 2>/dev/null || echo "Agent responded")"
  else
    echo "⚠️  Smoke test had issues (agent may still work — aliases can take 30s to propagate)"
    echo "   Retry: aws bedrock-agent-runtime invoke-agent --agent-id $AGENT_ID --agent-alias-id $ALIAS_ID ..."
  fi
fi

echo ""
echo "Done! 🎉"
