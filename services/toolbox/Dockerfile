# syntax=docker/dockerfile:1
# Toolbox: always-running utility container with backup, cron, and dev tools
# Merges the previous backup and toolbox containers into one.

FROM alpine:latest

# Install all tools needed for backup + general utility
RUN apk add --no-cache \
    bash tini dcron curl wget \
    rclone \
    postgresql-client postgresql \
    docker-cli docker-compose \
    python3 py3-pip \
    py3-psycopg2 \
    jq \
    # External-interaction tooling (email + TOTP, ships in the next version).
    # himalaya email CLI: Alpine package (v1.2.0, apk-managed).
    # oathtool CLI (TOTP/HOTP): Alpine package oath-toolkit-oathtool (the
    # oath-toolkit meta package alone ships only pskctool, not oathtool).
    himalaya \
    oath-toolkit-oathtool

# pyotp: TOTP library for python3. Not packaged in Alpine repos as py3-pyotp
# (Alpine's py3-otp is the unrelated 'otp' library), so install the pinned
# pure-python PyPI release (no build deps needed).
RUN python3 -m pip install --no-cache-dir --break-system-packages pyotp==2.10.0

# Copy backup/utility scripts
COPY scripts/backup.sh /usr/bin/backup
COPY scripts/checkpoint.sh /usr/bin/checkpoint
COPY scripts/restore_backup.sh /usr/bin/restore_backup
COPY scripts/restore_checkpoint.sh /usr/bin/restore_checkpoint
COPY scripts/checkout.sh /usr/bin/checkout
COPY scripts/restore_checkout.sh /usr/bin/restore_checkout
COPY scripts/entrypoint.sh /entrypoint.sh

RUN chmod +x /usr/bin/backup /usr/bin/checkout /usr/bin/checkpoint /usr/bin/restore_backup /usr/bin/restore_checkout /usr/bin/restore_checkpoint /entrypoint.sh

# Create cron log directory
RUN mkdir -p /var/log

# The crontab is generated dynamically by entrypoint.sh based on CRON_BACKUP and CRON_CHECKPOINT
ENTRYPOINT ["/sbin/tini", "--", "/entrypoint.sh"]
