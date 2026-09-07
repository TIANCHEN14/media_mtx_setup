#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="1.21.0"
ARCH="$(uname -m)"

case "$ARCH" in
  aarch64|arm64) ASSET_ARCH="arm64" ;;
  x86_64|amd64) ASSET_ARCH="amd64" ;;
  armv7l) ASSET_ARCH="armv7" ;;
  *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
esac

mkdir -p "$PROJECT_DIR/bin"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

ARCHIVE="mediamtx_v${VERSION}_linux_${ASSET_ARCH}.tar.gz"
BASE_URL="https://github.com/bluenviron/mediamtx/releases/download/v${VERSION}"

curl -fL "$BASE_URL/$ARCHIVE" -o "$TEMP_DIR/$ARCHIVE"
curl -fL "$BASE_URL/checksums.sha256" -o "$TEMP_DIR/checksums.sha256"
(
  cd "$TEMP_DIR"
  grep " \*$ARCHIVE\$" checksums.sha256 | sha256sum --check
  tar -xzf "$ARCHIVE" mediamtx
)
install -m 0755 "$TEMP_DIR/mediamtx" "$PROJECT_DIR/bin/mediamtx"
"$PROJECT_DIR/bin/mediamtx" --version
