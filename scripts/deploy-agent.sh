#!/bin/bash
set -e

AGENT_DIR="${1:-}"

if [ -z "$AGENT_DIR" ]; then
  echo "Usage: $0 <agent-directory>"
  echo "Example: $0 agents/01-market-intelligence-agent"
  exit 1
fi

echo "🚀 Deploying $AGENT_DIR..."
cd "$AGENT_DIR/infra"

terraform init -upgrade
terraform apply -auto-approve

echo "✅ Done"
