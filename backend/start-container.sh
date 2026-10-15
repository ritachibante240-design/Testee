#!/bin/sh
set -eu

volume_path="${RAILWAY_VOLUME_MOUNT_PATH:-/data}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///${volume_path}/videos.db}"
export VIDEOHUB_STORAGE_DIR="${VIDEOHUB_STORAGE_DIR:-${volume_path}/storage}"
export VIDEOHUB_ALLOW_PUBLIC_UPLOADS="${VIDEOHUB_ALLOW_PUBLIC_UPLOADS:-false}"

mkdir -p \
  "$VIDEOHUB_STORAGE_DIR/videos" \
  "$VIDEOHUB_STORAGE_DIR/thumbnails"

if [ ! -s "$volume_path/videos.db" ]; then
  cp /app/seed/videos.db "$volume_path/videos.db"
fi

if [ -z "$(find "$VIDEOHUB_STORAGE_DIR/videos" -maxdepth 1 -type f -name '*.mp4' -print -quit)" ]; then
  cp /app/seed/storage/videos/*.mp4 "$VIDEOHUB_STORAGE_DIR/videos/"
fi

if [ -z "$(find "$VIDEOHUB_STORAGE_DIR/thumbnails" -maxdepth 1 -type f -name '*.jpg' -print -quit)" ]; then
  cp /app/seed/storage/thumbnails/*.jpg "$VIDEOHUB_STORAGE_DIR/thumbnails/"
fi

exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8001}" \
  --http h11 \
  --proxy-headers \
  --forwarded-allow-ips="*"
