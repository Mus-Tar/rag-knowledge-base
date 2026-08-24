#!/usr/bin/env sh
set -eu
backup_dir=${1:-./backups}
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$backup_dir"
docker compose -f compose.yaml -f compose.production.yaml exec -T api \
  sh -c 'mkdir -p /tmp/rag-backup && sqlite3 /app/data/rag.db ".backup /tmp/rag-backup/rag.db" && tar -C /app/data -czf /tmp/rag-backup/rag-data.tar.gz uploads chroma'
docker compose -f compose.yaml -f compose.production.yaml cp api:/tmp/rag-backup/rag.db "$backup_dir/rag-$timestamp.db"
docker compose -f compose.yaml -f compose.production.yaml cp api:/tmp/rag-backup/rag-data.tar.gz "$backup_dir/rag-$timestamp-data.tar.gz"
