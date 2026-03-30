#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Khyzr Agents Deployment Script
# =============================================================================
#
# Usage:
#   ./deploy.sh [all|agent01|agent36|agent40|agent47|api]
#
# Examples:
#   ./deploy.sh all        # Deploy all agents + API Gateway
#   ./deploy.sh agent01    # Deploy only Agent 01 (Market Intelligence)
#   ./deploy.sh agent36    # Deploy only Agent 36 (AP Automation)
#   ./deploy.sh agent40    # Deploy only Agent 40 (AR Collections)
#   ./deploy.sh agent47    # Deploy only Agent 47 (SEO Content)
#   ./deploy.sh api        # Deploy API Gateway + Lambda proxy only
#
# AWS credentials are read from environment variables:
#   AWS_ACCESS_KEY_ID      — required
#   AWS_SECRET_ACCESS_KEY  — required
#   AWS_SESSION_TOKEN      — optional (for temporary credentials)
#
# Prerequisites:
#   - Python 3.12+ with pip
#   - AWS CLI configured (or credentials in env)
#   - Terraform at /workspace/bin/terraform or on PATH
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_DIR="$SCRIPT_DIR/agents"

# ── Terraform binary ─────────────────────────────────────────────────────────
if [ -f "/workspace/bin/terraform" ]; then
  TERRAFORM="/workspace/bin/terraform"
elif command -v terraform &>/dev/null; then
  TERRAFORM="terraform"
else
  echo "❌ ERROR: terraform not found at /workspace/bin/terraform and not on PATH"
  exit 1
fi

echo "✅ Using terraform: $TERRAFORM ($($TERRAFORM version -json | python3 -c 'import sys,json; print(json.load(sys.stdin)["terraform_version"])' 2>/dev/null || $TERRAFORM version | head -1))"

# ── Credentials check ────────────────────────────────────────────────────────
if [ -z "${AWS_ACCESS_KEY_ID:-}" ] || [ -z "${AWS_SECRET_ACCESS_KEY:-}" ]; then
  echo "⚠️  WARNING: AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY not set."
  echo "   Terraform will rely on ~/.aws/credentials or instance profile."
fi

# =============================================================================
# build_agent_zip <src_dir> <output_zip>
#
# Installs Python deps for manylinux aarch64 + Python 3.12, copies agent.py,
# and packages everything into a zip suitable for AgentCore Code Zip runtime.
# =============================================================================
build_agent_zip() {
  local src_dir="$1"
  local output_zip="$2"
  local build_dir
  build_dir="$(mktemp -d)"

  echo "  📦 Building zip from: $src_dir"
  echo "  📂 Build dir: $build_dir"
  echo "  🎯 Output zip: $output_zip"

  # Install dependencies (manylinux aarch64, Python 3.12 binaries)
  if [ -f "$src_dir/../requirements.txt" ]; then
    echo "  ⬇️  Installing dependencies..."
    pip install \
      --target "$build_dir" \
      --platform manylinux2014_aarch64 \
      --python-version 3.12 \
      --only-binary=:all: \
      strands-agents bedrock-agentcore boto3 openpyxl \
      2>&1 | tail -5
    echo "  ✅ Dependencies installed"
  else
    echo "  ⚠️  No requirements.txt found, skipping pip install"
  fi

  # Copy agent.py
  if [ -f "$src_dir/agent.py" ]; then
    cp "$src_dir/agent.py" "$build_dir/agent.py"
    echo "  ✅ Copied agent.py"
  else
    echo "  ❌ ERROR: agent.py not found in $src_dir"
    rm -rf "$build_dir"
    return 1
  fi

  # Create the zip
  local zip_dir
  zip_dir="$(dirname "$output_zip")"
  mkdir -p "$zip_dir"

  (cd "$build_dir" && zip -r "$output_zip" . -x "*.pyc" -x "__pycache__/*" -x "*.dist-info/*" 2>&1 | tail -3)
  echo "  ✅ Zip created: $output_zip ($(du -sh "$output_zip" | cut -f1))"

  # Cleanup
  rm -rf "$build_dir"
}

# =============================================================================
# deploy_api
#
# Zips api/lambda/handler.py and runs Terraform in api/infra/.
# =============================================================================
deploy_api() {
  local api_dir="$SCRIPT_DIR/api"
  local lambda_dir="$api_dir/lambda"
  local infra_dir="$api_dir/infra"
  local zip_path="$lambda_dir/handler.zip"

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🚀 Deploying API Gateway + Lambda Proxy"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  if [ ! -f "$lambda_dir/handler.py" ]; then
    echo "❌ ERROR: $lambda_dir/handler.py not found"
    return 1
  fi

  # Step 1: zip the Lambda handler
  echo ""
  echo "📦 Step 1/3: Zipping Lambda handler..."
  (cd "$lambda_dir" && zip -j "$zip_path" handler.py 2>&1)
  echo "  ✅ Zip created: $zip_path ($(du -sh "$zip_path" | cut -f1))"

  # Step 2: Terraform init
  echo ""
  echo "🔧 Step 2/3: Terraform init..."
  cd "$infra_dir"
  if $TERRAFORM init -upgrade 2>&1 | tail -5; then
    echo "  ✅ Terraform init complete"
  else
    echo "  ❌ Terraform init failed"
    return 1
  fi

  # Step 3: Terraform apply
  echo ""
  echo "⚙️  Step 3/3: Terraform apply..."
  if $TERRAFORM apply -auto-approve -var-file="terraform.tfvars" 2>&1; then
    echo ""
    echo "  ✅ Terraform apply complete"
    echo ""
    echo "🌐 API Endpoint:"
    $TERRAFORM output -raw api_endpoint 2>/dev/null && echo ""
  else
    echo ""
    echo "  ❌ Terraform apply failed"
    return 1
  fi

  echo ""
  echo "🎉 API Gateway + Lambda deployed successfully!"
  echo "   POST to: $($TERRAFORM output -raw api_endpoint 2>/dev/null)/chat"
}

# =============================================================================
# deploy_agent <agent_label> <agent_dir_name>
# =============================================================================
deploy_agent() {
  local label="$1"
  local agent_dir_name="$2"
  local agent_dir="$AGENTS_DIR/$agent_dir_name"
  local infra_dir="$agent_dir/infra"
  local src_dir="$agent_dir/src"

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🚀 Deploying $label ($agent_dir_name)"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  if [ ! -d "$agent_dir" ]; then
    echo "❌ ERROR: Agent directory not found: $agent_dir"
    return 1
  fi

  if [ ! -d "$infra_dir" ]; then
    echo "❌ ERROR: Infra directory not found: $infra_dir"
    return 1
  fi

  # Build the agent zip
  local zip_path="$infra_dir/agent.zip"
  echo ""
  echo "📦 Step 1/3: Building agent zip..."
  if build_agent_zip "$src_dir" "$zip_path"; then
    echo "  ✅ Build complete"
  else
    echo "  ❌ Build failed for $label"
    return 1
  fi

  # Terraform init
  echo ""
  echo "🔧 Step 2/3: Terraform init..."
  cd "$infra_dir"
  if $TERRAFORM init -upgrade 2>&1 | tail -5; then
    echo "  ✅ Terraform init complete"
  else
    echo "  ❌ Terraform init failed for $label"
    return 1
  fi

  # Terraform apply
  echo ""
  echo "⚙️  Step 3/3: Terraform apply..."
  if $TERRAFORM apply \
    -auto-approve \
    -var="agent_zip_path=$zip_path" \
    2>&1; then
    echo ""
    echo "  ✅ Terraform apply complete for $label"
  else
    echo ""
    echo "  ❌ Terraform apply failed for $label"
    return 1
  fi

  echo ""
  echo "🎉 $label deployed successfully!"
}

# =============================================================================
# Main
# =============================================================================
TARGET="${1:-all}"
ERRORS=0

echo "============================================================"
echo "  Khyzr Agents Deploy Script"
echo "  Target: $TARGET"
echo "  Region: ${AWS_DEFAULT_REGION:-us-east-1}"
echo "============================================================"

case "$TARGET" in
  agent01)
    deploy_agent "Agent 01 - Market Intelligence" "01-market-intelligence-agent" || ERRORS=$((ERRORS + 1))
    ;;

  agent36)
    deploy_agent "Agent 36 - AP Automation" "36-ap-automation-agent" || ERRORS=$((ERRORS + 1))
    ;;

  agent40)
    deploy_agent "Agent 40 - AR Collections" "40-ar-collections-agent" || ERRORS=$((ERRORS + 1))
    ;;

  agent47)
    deploy_agent "Agent 47 - SEO Content" "47-seo-content-agent" || ERRORS=$((ERRORS + 1))
    ;;

  api)
    deploy_api || ERRORS=$((ERRORS + 1))
    ;;

  all)
    deploy_agent "Agent 01 - Market Intelligence" "01-market-intelligence-agent" || ERRORS=$((ERRORS + 1))
    deploy_agent "Agent 36 - AP Automation"       "36-ap-automation-agent"       || ERRORS=$((ERRORS + 1))
    deploy_agent "Agent 40 - AR Collections"      "40-ar-collections-agent"      || ERRORS=$((ERRORS + 1))
    deploy_agent "Agent 47 - SEO Content"         "47-seo-content-agent"         || ERRORS=$((ERRORS + 1))
    deploy_api                                                                    || ERRORS=$((ERRORS + 1))
    ;;

  *)
    echo ""
    echo "❌ Unknown target: $TARGET"
    echo ""
    echo "Usage: $0 [all|agent01|agent36|agent40|agent47|api]"
    exit 1
    ;;
esac

echo ""
echo "============================================================"
if [ "$ERRORS" -eq 0 ]; then
  echo "✅ All deployments completed successfully!"
else
  echo "❌ Completed with $ERRORS error(s). Check output above."
  exit 1
fi
echo "============================================================"
