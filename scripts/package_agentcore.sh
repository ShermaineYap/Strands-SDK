#!/usr/bin/env bash
# Assemble an AgentCore "bring your own code" agent folder from this repo.
#   usage: bash scripts/package_agentcore.sh <path-to-agent-folder, e.g. app/JagaSungai>
set -euo pipefail
DEST="${1:?agent folder, e.g. app/JagaSungai}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$DEST"
cp "$REPO/agentcore/app.py" "$DEST/main.py"
rm -rf "$DEST/jagasungai" "$DEST/profiles"
cp -r "$REPO/jagasungai" "$REPO/profiles" "$DEST/"
find "$DEST" -name __pycache__ -type d -prune -exec rm -rf {} +
cd "$DEST"
[ -f pyproject.toml ] || uv init --bare --python 3.13
uv add "strands-agents==1.62.0" "bedrock-agentcore" "aws-opentelemetry-distro" boto3 pydantic requests beautifulsoup4 lxml PyYAML
echo "Packaged JagaSungai into $DEST"
