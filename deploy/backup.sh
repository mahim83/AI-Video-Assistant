#!/bin/sh
# Back up ./data (meetings, search indexes, users, audit log) to backups/,
# then optionally upload it with rclone. Run from cron as root, e.g.:
#   15 3 * * * /opt/ai-video-assistant/deploy/backup.sh >> /var/log/ai-video-backup.log 2>&1
# Set RCLONE_REMOTE (e.g. "b2:my-bucket/ai-video") to copy each backup off the server.
set -eu
# Backups hold every user's transcripts: readable by the owner only.
umask 077
cd "$(dirname "$0")/.."

STAMP=$(date -u +%Y%m%d-%H%M%S)
ARCHIVE="backups/data-$STAMP.tar.gz"
mkdir -p backups

# A consistent snapshot of the app database, even if a user is writing to it.
docker compose exec -T app python -c "import sqlite3; s = sqlite3.connect('/app/data/app.db'); d = sqlite3.connect('/app/data/app.db.backup'); s.backup(d); d.close(); s.close()"

# Temporary audio (work/) and the live database files are left out.
tar -czf "$ARCHIVE" \
    --exclude='data/users/*/work' \
    --exclude='data/app.db' --exclude='data/app.db-wal' --exclude='data/app.db-shm' \
    data
rm -f data/app.db.backup

if [ -n "${RCLONE_REMOTE:-}" ]; then
    rclone copy "$ARCHIVE" "$RCLONE_REMOTE"
fi

# Keep two weeks of local backups.
find backups -name 'data-*.tar.gz' -mtime +14 -delete
echo "$(date -u) backup written: $ARCHIVE"
