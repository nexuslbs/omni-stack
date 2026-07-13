#!/bin/bash
set -euo pipefail

# Entrypoint for the toolbox container.
# Sets up rclone config if S3 vars are available, installs cron jobs, then sleeps.

# ── Optional: S3/rclone setup (only if S3_ACCESS_KEY is set) ──────────────
if [ -n "${S3_ACCESS_KEY:-}" ]; then
    : "${S3_SECRET_KEY:?S3_SECRET_KEY not set}"
    : "${S3_ENDPOINT:?S3_ENDPOINT not set}"
    : "${S3_REGION:?S3_REGION not set}"
    : "${S3_BUCKET:?S3_BUCKET not set}"
    : "${S3_PATH:?S3_PATH not set}"

    mkdir -p /etc/rclone
    cat > /etc/rclone/rclone.conf <<EOF
[s3-backup]
type = s3
provider = Other
access_key_id = ${S3_ACCESS_KEY}
secret_access_key = ${S3_SECRET_KEY}
endpoint = ${S3_ENDPOINT}
region = ${S3_REGION}
EOF
    chmod 600 /etc/rclone/rclone.conf
    echo "[entrypoint] rclone config written for remote 's3-backup'"
else
    echo "[entrypoint] S3_ACCESS_KEY not set - skipping rclone setup"
fi

# ── Cron jobs (only if S3 is configured) ─────────────────────────────────
CRONTAB_FILE=/tmp/crontab
rm -f "$CRONTAB_FILE"

if [ -n "${CRON_BACKUP:-}" ] && [ -n "${S3_ACCESS_KEY:-}" ]; then
    echo "${CRON_BACKUP} RCLONE_CONFIG=/etc/rclone/rclone.conf /usr/bin/backup >> /var/log/backup.log 2>&1" >> "$CRONTAB_FILE"
    echo "[entrypoint] Scheduled backup: ${CRON_BACKUP}"
fi

if [ -n "${CRON_CHECKPOINT:-}" ] && [ -n "${S3_ACCESS_KEY:-}" ]; then
    echo "${CRON_CHECKPOINT} RCLONE_CONFIG=/etc/rclone/rclone.conf /usr/bin/checkpoint >> /var/log/checkpoint.log 2>&1" >> "$CRONTAB_FILE"
    echo "[entrypoint] Scheduled checkpoint: ${CRON_CHECKPOINT}"
fi

if [ -f "$CRONTAB_FILE" ]; then
    crontab "$CRONTAB_FILE"
    echo "[entrypoint] Crontab installed."
else
    echo "[entrypoint] No cron jobs configured."
fi

echo "[entrypoint] Toolbox container ready."

# Run crond in foreground, or just sleep if no cron
if [ -f "$CRONTAB_FILE" ]; then
    exec crond -f -l 2 -L /dev/stdout
else
    # No cron jobs - just keep the container alive
    exec tail -f /dev/null
fi
