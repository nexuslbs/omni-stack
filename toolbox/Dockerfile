# syntax=docker/dockerfile:1
# Toolbox — always-running utility container with backup, cron, and dev tools
# Merges the previous backup and toolbox containers into one.

FROM alpine:latest

# Install all tools needed for backup + general utility
RUN apk add --no-cache \
    bash tini dcron curl wget \
    rclone \
    postgresql-client postgresql \
    docker-cli docker-compose \
    python3 py3-pip \
    jq

# Copy backup/utility scripts
COPY scripts/backup.sh /usr/bin/backup
COPY scripts/checkpoint.sh /usr/bin/checkpoint
COPY scripts/restore_backup.sh /usr/bin/restore_backup
COPY scripts/restore_checkpoint.sh /usr/bin/restore_checkpoint
COPY scripts/entrypoint.sh /entrypoint.sh

RUN chmod +x /usr/bin/backup /usr/bin/checkpoint /usr/bin/restore_backup /usr/bin/restore_checkpoint /entrypoint.sh

# Create cron log directory
RUN mkdir -p /var/log

# The crontab is generated dynamically by entrypoint.sh based on CRON_BACKUP and CRON_CHECKPOINT
ENTRYPOINT ["/sbin/tini", "--", "/entrypoint.sh"]
