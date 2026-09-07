#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_ENV="$PROJECT_DIR/config/local.env"

if [[ ! -f "$LOCAL_ENV" ]]; then
  echo "Missing $LOCAL_ENV; run scripts/bootstrap.sh and configure RTSP_SOURCE_URL." >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$LOCAL_ENV"
: "${RTSP_SOURCE_URL:?Set RTSP_SOURCE_URL in config/local.env}"
export MTX_PATHS_CAMERA01_SOURCE="$RTSP_SOURCE_URL"

if [[ -n "${PUBLIC_HOST:-}" ]]; then
  WEBRTC_HOSTS="$PUBLIC_HOST"
else
  WEBRTC_HOSTS="$(hostname -I | tr ' ' '\n' | sed '/^$/d' | paste -sd, -)"
fi

if [[ -n "$WEBRTC_HOSTS" ]]; then
  export MTX_WEBRTCADDITIONALHOSTS="$WEBRTC_HOSTS"
fi

exec "$PROJECT_DIR/bin/mediamtx" "$PROJECT_DIR/config/mediamtx.yml"
