#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_FILE="$PROJECT_DIR/deploy/cloudflare-grid-tunnel.service"

if [[ ! -x "$PROJECT_DIR/bin/cloudflared" ]]; then
  printf 'cloudflared is missing at %s/bin/cloudflared\n' "$PROJECT_DIR" >&2
  exit 1
fi

systemctl --user link "$UNIT_FILE" >/dev/null 2>&1 || true
systemctl --user daemon-reload
systemctl --user enable --now cloudflare-grid-tunnel.service
printf 'Cloudflare Tunnel service started.\n'
