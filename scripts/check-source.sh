#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$PROJECT_DIR/config/local.env"
: "${RTSP_SOURCE_URL:?Set RTSP_SOURCE_URL in config/local.env}"

ffprobe \
  -v error \
  -rtsp_transport tcp \
  -show_entries stream=index,codec_type,codec_name,width,height,r_frame_rate \
  -of json \
  "$RTSP_SOURCE_URL"
