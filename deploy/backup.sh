#!/bin/sh
# Runs inside the postgres image: one backup at start, then every night at
# BACKUP_HOUR (server time). Old files are removed after BACKUP_KEEP_DAYS.
set -eu
KEEP="${BACKUP_KEEP_DAYS:-14}"
HOUR="${BACKUP_HOUR:-2}"
export PGPASSWORD="$POSTGRES_PASSWORD"

backup() {
  stamp=$(date +%Y-%m-%d_%H%M)
  pg_dump -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom -f "/backups/db_$stamp.dump"
  tar -czf "/backups/media_$stamp.tar.gz" -C /data media 2>/dev/null || true
  # Only this script's own files, only in /backups.
  find /backups -maxdepth 1 -type f \( -name 'db_*.dump' -o -name 'media_*.tar.gz' \) -mtime +"$KEEP" -exec rm -f {} +
  echo "$(date) backup $stamp done"
}

backup
while true; do
  now=$(date +%s)
  next=$(date -d "$(date +%Y-%m-%d) $HOUR:00" +%s)
  if [ "$next" -le "$now" ]; then next=$((next + 86400)); fi
  sleep $((next - now))
  backup
done
