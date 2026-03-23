#!/bin/bash
# build-push.sh — Build and push an agent Docker image to ECR for AgentCore Runtime
#
# Usage:   ./scripts/build-push.sh <agent-directory> [aws-region]
# Example: ./scripts/build-push.sh agents/36-ap-automation-agent us-east-1
#
# Prerequisites:
#   - Docker with buildx (https://docs.docker.com/buildx/working-with-buildx/)
#   - AWS CLI configured with credentials that have ECR push permissions
#   - The ECR repository must already exist (created by `terraform apply`)
#
# AgentCore Runtime requires ARM64 container images.
# This script uses `docker buildx build --platform linux/arm64` to produce
# the correct architecture even when running on an x86_64 host.

set -euo pipefail

# ── Arguments ──────────────────────────────────────────────────────────────
AGENT_DIR="${1:-}"
REGION="${2:-us-east-1}"

if [ -z "$AGENT_DIR" ]; then
  echo "❌ Usage: $0 <agent-directory> [region]"
  echo "   Example: $0 agents/36-ap-automation-agent us-east-1"
  exit 1
fi

if [ ! -d "$AGENT_DIR" ]; then
  echo "❌ Directory not found: $AGENT_DIR"
  exit 1
fi

if [ ! -f "$AGENT_DIR/Dockerfile" ]; then
  echo "❌ No Dockerfile found in $AGENT_DIR"
  exit 1
fi

# ── Resolve names ───────────────────────────────────────────────────────────
AGENT_NAME=$(basename "$AGENT_DIR")
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
ECR_REPO="$ECR_REGISTRY/khyzr/$AGENT_NAME"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  AgentCore ARM64 Docker Build + Push                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "🤖 Agent:    $AGENT_NAME"
echo "📦 ECR:      $ECR_REPO:latest"
echo "🌍 Region:   $REGION"
echo "🏗️  Platform: linux/arm64 (required by AgentCore Runtime)"
echo ""

# ── Ensure buildx builder exists ────────────────────────────────────────────
if ! docker buildx inspect agentcore-builder &>/dev/null; then
  echo "⚙️  Creating buildx builder for ARM64 cross-compilation..."
  docker buildx create --name agentcore-builder --use
else
  docker buildx use agentcore-builder
fi

# ── Authenticate with ECR ───────────────────────────────────────────────────
echo "🔐 Authenticating with ECR..."
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

# ── Build for ARM64 and push ────────────────────────────────────────────────
echo "🐳 Building ARM64 image and pushing to ECR..."
echo ""

cd "$AGENT_DIR"
docker buildx build \
  --platform linux/arm64 \
  -t "$ECR_REPO:latest" \
  --push \
  .

echo ""
echo "✅ Successfully pushed: $ECR_REPO:latest"
echo ""
echo "📋 Next steps:"
echo "   1. Run terraform apply to deploy/update the AgentCore Runtime"
echo "   2. Or if the runtime is already deployed, it will pick up the new image on next invocation"
echo ""
echo "🧪 Test invocation:"
echo "   RUNTIME_ARN=\$(cd infra && terraform output -raw agent_runtime_arn)"
echo "   aws bedrock-agentcore invoke-agent-runtime \\"
echo "     --agent-runtime-arn \"\$RUNTIME_ARN\" \\"
echo "     --payload '{\"prompt\": \"Run a quick self-test\"}' \\"
echo "     --region $REGION"
