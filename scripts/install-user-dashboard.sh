#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_FILE="$PROJECT_DIR/deploy/grid-monitor-dashboard-user.service"

systemctl --user link "$UNIT_FILE" >/dev/null 2>&1 || true
systemctl --user daemon-reload
systemctl --user enable --now grid-monitor-dashboard-user.service
printf 'Dashboard service started at http://0.0.0.0:8090\n'
