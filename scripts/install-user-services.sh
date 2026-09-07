#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"

sed "s|@PROJECT_DIR@|$PROJECT_DIR|g" \
  "$PROJECT_DIR/deploy/systemd/mediamtx-local.service.in" \
  > "$UNIT_DIR/mediamtx-local.service"
sed "s|@PROJECT_DIR@|$PROJECT_DIR|g" \
  "$PROJECT_DIR/deploy/systemd/video-gateway.service.in" \
  > "$UNIT_DIR/video-gateway.service"

systemctl --user daemon-reload
systemctl --user enable --now mediamtx-local.service video-gateway.service
systemctl --user --no-pager --full status mediamtx-local.service video-gateway.service
