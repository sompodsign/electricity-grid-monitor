#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_TEMPLATE="$PROJECT_DIR/deploy/grid-monitor.service.in"
SERVICE_FILE="/etc/systemd/system/grid-monitor.service"

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  printf 'Create .env from .env.example before installing the service.\n' >&2
  exit 1
fi

sed -e "s|__USER__|$USER|g" -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$SERVICE_TEMPLATE" \
  | sudo tee "$SERVICE_FILE" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now grid-monitor.service
printf 'Service installed. View logs with: sudo journalctl -u grid-monitor -f\n'
