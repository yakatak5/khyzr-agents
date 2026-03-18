#!/bin/bash
set -e

echo "🚀 Deploying all Khyzr agents..."
cd "$(dirname "$0")/../infra"

terraform init -upgrade
terraform plan -out=tfplan
terraform apply tfplan

echo "✅ All agents deployed successfully"
