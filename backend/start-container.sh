#!/bin/sh
set -eu

volume_path="${RAILWAY_VOLUME_MOUNT_PATH:-/data}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///${volume_path}/videos.db}"
export VIDEOHUB_STORAGE_DIR="${VIDEOHUB_STORAGE_DIR:-${volume_path}/storage}"
export VIDEOHUB_ALLOW_PUBLIC_UPLOADS="${VIDEOHUB_ALLOW_PUBLIC_UPLOADS:-false}"

mkdir -p \
  "$VIDEOHUB_STORAGE_DIR/videos" \
  "$VIDEOHUB_STORAGE_DIR/thumbnails"

exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8001}" \
  --http h11 \
  --proxy-headers \
  --forwarded-allow-ips="*"
