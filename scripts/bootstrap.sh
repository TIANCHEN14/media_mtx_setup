#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$PROJECT_DIR/scripts/install-mediamtx.sh"
python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

if [[ ! -f "$PROJECT_DIR/config/local.env" ]]; then
  cp "$PROJECT_DIR/config/local.env.example" "$PROJECT_DIR/config/local.env"
  echo "Created config/local.env. Set RTSP_SOURCE_URL before starting MediaMTX."
fi

echo "Bootstrap complete. Install the services with:"
echo "  $PROJECT_DIR/scripts/install-user-services.sh"
