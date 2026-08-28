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
    nodejs \
    jq

# Copy backup/utility scripts
COPY scripts/backup.sh /usr/bin/backup
COPY scripts/checkpoint.sh /usr/bin/checkpoint
COPY scripts/restore_backup.sh /usr/bin/restore_backup
COPY scripts/restore_checkpoint.sh /usr/bin/restore_checkpoint
COPY scripts/checkout.sh /usr/bin/checkout
COPY scripts/restore_checkout.sh /usr/bin/restore_checkout
COPY scripts/entrypoint.sh /entrypoint.sh

# Code-exec runners (builtin `code_exec` MCP tool executes model-written
# programs in THIS container: the dsh codeRuntime seam: program via stdin,
# typed JSON completion value on a marker line). The core never runs the
# program in-process; it `docker exec`s into the toolbox instead.
COPY scripts/code_exec_runner.py /usr/bin/code_exec_runner
COPY scripts/code_exec_runner_js.js /usr/bin/code_exec_runner_js

RUN chmod +x /usr/bin/backup /usr/bin/checkout /usr/bin/checkpoint /usr/bin/restore_backup /usr/bin/restore_checkout /usr/bin/restore_checkpoint /entrypoint.sh /usr/bin/code_exec_runner /usr/bin/code_exec_runner_js

# Create cron log directory
RUN mkdir -p /var/log

# The crontab is generated dynamically by entrypoint.sh based on CRON_BACKUP and CRON_CHECKPOINT
ENTRYPOINT ["/sbin/tini", "--", "/entrypoint.sh"]
