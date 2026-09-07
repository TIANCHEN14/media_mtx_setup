#!/usr/bin/env bash
set -euo pipefail

echo "Gateway health"
curl -fsS http://127.0.0.1:8000/healthz
echo
echo "Registered streams"
curl -fsS http://127.0.0.1:8000/streams
echo
echo "camera01 health"
curl -fsS http://127.0.0.1:8000/streams/camera01/health
echo
echo "HLS master playlist"
COOKIE_FILE="$(mktemp)"
trap 'rm -f "$COOKIE_FILE"' EXIT
curl -fsSL --max-time 15 \
  -c "$COOKIE_FILE" -b "$COOKIE_FILE" \
  http://127.0.0.1:8888/camera01/index.m3u8 \
  | sed -n '1,12p'
