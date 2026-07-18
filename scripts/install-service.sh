#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAMES=("grid-monitor" "grid-monitor-dashboard")

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  printf 'Create .env from .env.example before installing the service.\n' >&2
  exit 1
fi

for service_name in "${SERVICE_NAMES[@]}"; do
  service_template="$PROJECT_DIR/deploy/$service_name.service.in"
  service_file="/etc/systemd/system/$service_name.service"
  sed -e "s|__USER__|$USER|g" -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$service_template" \
    | sudo tee "$service_file" >/dev/null
done

sudo systemctl daemon-reload
sudo systemctl enable --now grid-monitor.service grid-monitor-dashboard.service
printf 'Services installed. Dashboard: http://127.0.0.1:8090\n'
printf 'View logs with: sudo journalctl -u grid-monitor -u grid-monitor-dashboard -f\n'
