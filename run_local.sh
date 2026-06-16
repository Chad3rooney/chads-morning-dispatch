#!/usr/bin/env bash
# Build the dispatch locally and open it in your browser.
#
#   ./run_local.sh
#
# To enable the Claude synthesis layer, export your key first:
#   export ANTHROPIC_API_KEY="sk-ant-..."
set -euo pipefail
cd "$(dirname "$0")"

# macOS framework Python sometimes ships without a usable CA bundle, which
# makes HTTPS fail. Fall back to the system bundle if one isn't already set.
if [[ -z "${SSL_CERT_FILE:-}" && -f /etc/ssl/cert.pem ]]; then
  export SSL_CERT_FILE=/etc/ssl/cert.pem
fi

python3 generate.py --out public

PAGE="public/index.html"
echo "Built $PAGE"
if command -v open >/dev/null 2>&1; then
  open "$PAGE"          # macOS
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$PAGE"      # Linux
fi
