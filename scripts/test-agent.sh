#!/bin/bash
set -e

AGENT_DIR="${1:-}"
INPUT="${2:-'{\"message\": \"Run default analysis\"}'}"

if [ -z "$AGENT_DIR" ]; then
  echo "Usage: $0 <agent-directory> [json-input]"
  echo "Example: $0 agents/01-market-intelligence-agent '{\"message\": \"Analyze OpenAI\"}'"
  exit 1
fi

echo "🧪 Testing $AGENT_DIR..."
cd "$AGENT_DIR"
echo "$INPUT" | python src/agent.py
