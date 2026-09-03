#!/bin/bash
# Backup: sync OMNI_DIR/data/ (including DB backups) to S3
# - PG dumps in custom format → data/backups/omniagent/ and data/backups/mattermost/
# - Grafana SQLite dump → data/backups/grafana/
# - File data sync to S3
# - FINAL step: git sync via the omniagent API (same call as the dashboard
#   explorer sync button), so the local config repo state is pushed to the
#   remote right after the backup lands in S3.
set -euo pipefail

OMNI_DIR="${OMNI_DIR:-/opt/omni-stack}"
S3_BUCKET="${S3_BUCKET:-hermes-nexuslbs}"
S3_PREFIX="${S3_PATH:-omni}/data"
S3_ENDPOINT="${S3_ENDPOINT:-https://s3.us-east-005.backblazeb2.com}"
S3_REGION="${S3_REGION:-us-east-005}"

# ── Compose project resolution ─────────────────────────────────────────────
# Containers/volumes are auto-named per project ({project}-{service}-{index},
# {project}_{volume}) - there are no fixed omni-* names. Derive the project
# from this container's compose label; fall back to the default directory name.
PROJECT="$(docker inspect "$HOSTNAME" --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || true)"
PROJECT="${PROJECT:-omni-stack}"
GRAFANA_CT="$(docker ps -q --filter "label=com.docker.compose.project=${PROJECT}" --filter "name=grafana" 2>/dev/null | head -1)"
GRAFANA_VOL="${PROJECT}_grafana-vol"

BACKUP_DIR="${OMNI_DIR}/data/backups"
mkdir -p "${BACKUP_DIR}/omniagent" "${BACKUP_DIR}/mattermost" "${BACKUP_DIR}/grafana"

# ── Source credentials ─────────────────────────────────────────────────────
if [ -f "${OMNI_DIR}/.env" ]; then
  set -a
  . "${OMNI_DIR}/.env"
  set +a
fi

if [ -z "${S3_ACCESS_KEY:-}" ] || [ -z "${S3_SECRET_KEY:-}" ]; then
  echo "[backup] ERROR: S3_ACCESS_KEY and S3_SECRET_KEY must be set"
  exit 1
fi

# ── Build rclone config ────────────────────────────────────────────────────
RCLONE_CONF=$(mktemp /tmp/rclone-conf-XXXXXX)
cat > "$RCLONE_CONF" <<EOF
[omni-s3]
type = s3
provider = Other
access_key_id = ${S3_ACCESS_KEY}
secret_access_key = ${S3_SECRET_KEY}
endpoint = ${S3_ENDPOINT}
region = ${S3_REGION}
EOF
chmod 600 "$RCLONE_CONF"

RC="rclone --config ${RCLONE_CONF}"
DEST="omni-s3:${S3_BUCKET}/${S3_PREFIX}"

echo "[backup] Starting backup to ${DEST}/"

# ─── Step 1: Copy .env to data/credentials/.env ────────────────────────────
echo "[backup] Step 1/6: Copying .env to data/credentials/.env..."
mkdir -p "${OMNI_DIR}/data/credentials"
cp "${OMNI_DIR}/.env" "${OMNI_DIR}/data/credentials/.env"
echo "[backup] .env copied."

# ─── Step 2: OmniAgent PG dump (custom format) ────────────────────────────
echo "[backup] Step 2/6: OmniAgent PostgreSQL dump..."
OA_USER="${POSTGRES_USER:-omniagent}"
OA_DB="${POSTGRES_DB:-omniagent}"

if [ -n "${POSTGRES_PASSWORD:-}" ]; then
  export PGPASSWORD="${POSTGRES_PASSWORD}"
  DUMP_FILE="${BACKUP_DIR}/omniagent/omniagent.dump"
  LOG_FILE="${BACKUP_DIR}/omniagent/dump.log"
  
  pg_dump -h postgres -U "$OA_USER" -d "$OA_DB" \
    --format=custom --compress=9 \
    --no-owner --no-acl --clean --if-exists \
    -f "$DUMP_FILE" 2>"$LOG_FILE"
  
  unset PGPASSWORD
  
  # Verify integrity
  if [ -f "$DUMP_FILE" ] && [ "$(stat -c%s "$DUMP_FILE")" -gt 100 ]; then
    if pg_restore -l "$DUMP_FILE" >/dev/null 2>>"$LOG_FILE"; then
      echo "[backup] OmniAgent PG dump OK ($(stat -c%s "$DUMP_FILE") bytes)"
    else
      echo "[backup] ERROR: OmniAgent PG dump corrupt! Check ${LOG_FILE}"
      rm -f "$DUMP_FILE"
    fi
  else
    echo "[backup] ERROR: OmniAgent PG dump too small or missing!"
    echo "  log: $(cat "$LOG_FILE" | tail -3)"
    rm -f "$DUMP_FILE"
  fi
else
  echo "[backup] POSTGRES_PASSWORD not set -- skipping OmniAgent PG dump."
fi

# ─── Step 3: Mattermost PG dump (custom format) ────────────────────────────
MM_PROFILE="${COMPOSE_PROFILES:-}"
echo "[backup] Step 3/6: Mattermost PostgreSQL (profiles: ${MM_PROFILE})..."

if echo "$MM_PROFILE" | grep -qE '(mattermost|all)'; then
  if [ -n "${MM_POSTGRES_PASSWORD:-}" ]; then
    export PGPASSWORD="${MM_POSTGRES_PASSWORD}"
    DUMP_FILE="${BACKUP_DIR}/mattermost/mattermost.dump"
    LOG_FILE="${BACKUP_DIR}/mattermost/dump.log"
    
    pg_dump -h mattermost-db -U "${MM_POSTGRES_USER:-mmuser}" -d mattermost \
      --format=custom --compress=9 \
      --no-owner --no-acl --clean --if-exists \
      -f "$DUMP_FILE" 2>"$LOG_FILE" || {
      echo "[backup] Mattermost PG dump failed -- continuing."
      rm -f "$DUMP_FILE"
    }
    unset PGPASSWORD
    
    if [ -f "$DUMP_FILE" ] && [ "$(stat -c%s "$DUMP_FILE")" -gt 100 ]; then
      if pg_restore -l "$DUMP_FILE" >/dev/null 2>>"$LOG_FILE"; then
        echo "[backup] Mattermost PG dump OK ($(stat -c%s "$DUMP_FILE") bytes)"
      else
        echo "[backup] ERROR: Mattermost PG dump corrupt! Check ${LOG_FILE}"
        rm -f "$DUMP_FILE"
      fi
    else
      echo "[backup] Mattermost PG dump not available -- continuing."
    fi
  else
    echo "[backup] MM_POSTGRES_PASSWORD not set -- skipping Mattermost PG dump."
  fi
else
  echo "[backup] Step 3/6: Mattermost profile not active -- skipping."
fi

# ─── Step 4: Grafana SQLite backup ────────────────────────────────────────
echo "[backup] Step 4/6: Grafana data..."
if [ -n "${GRAFANA_CT}" ]; then
  GRAFANA_BACKUP="${BACKUP_DIR}/grafana/grafana.db"
  # The grafana image ships NO sqlite3 CLI (exec exits 127), so pull the db
  # (+ wal/shm, best-effort) out of the container and take a consistent
  # snapshot with python3's sqlite3 backup API (toolbox alpine ships python3
  # with the sqlite3 module built in). Verified: backup API output passes
  # PRAGMA integrity_check.
  if docker cp "${GRAFANA_CT}:/var/lib/grafana/grafana.db" /tmp/grafana-src.db 2>/dev/null \
     && (docker cp "${GRAFANA_CT}:/var/lib/grafana/grafana.db-wal" /tmp/grafana-src.db-wal 2>/dev/null || true) \
     && (docker cp "${GRAFANA_CT}:/var/lib/grafana/grafana.db-shm" /tmp/grafana-src.db-shm 2>/dev/null || true) \
     && python3 -c 'import sqlite3; src=sqlite3.connect("/tmp/grafana-src.db"); dst=sqlite3.connect("/tmp/grafana-backup.db"); src.backup(dst); dst.close(); src.close()' \
     && mv /tmp/grafana-backup.db "$GRAFANA_BACKUP"; then
    rm -f /tmp/grafana-src.db /tmp/grafana-src.db-wal /tmp/grafana-src.db-shm
    if [ -f "$GRAFANA_BACKUP" ] && [ "$(stat -c%s "$GRAFANA_BACKUP")" -gt 1000 ]; then
      echo "[backup] Grafana backup OK ($(stat -c%s "$GRAFANA_BACKUP") bytes)"
    else
      echo "[backup] Grafana backup too small or missing."
      rm -f "$GRAFANA_BACKUP"
    fi
  else
    rm -f /tmp/grafana-src.db /tmp/grafana-src.db-wal /tmp/grafana-src.db-shm /tmp/grafana-backup.db
    echo "[backup] Grafana SQLite backup failed -- continuing."
  fi
else
  echo "[backup] Grafana not running -- skipping."
fi

# ─── Step 5: Sync data/ to S3 (includes backups/) ──────────────────────────
echo "[backup] Step 5/6: Syncing file data to S3..."
$RC sync "${OMNI_DIR}/data/" "${DEST}/" \
  --create-empty-src-dirs \
  --s3-no-check-bucket \
  --fast-list \
  --verbose 2>&1 | tail -5

# ─── Step 6: Git sync via omniagent API (FINAL step) ───────────────────────
# Push the local config repo state - the SAME API call the dashboard
# explorer sync button performs (POST /git/sync on the omniagent HTTP API,
# which runs the configured sync tool, default `git_sync` from the builtin
# git plugin). Guard: only run when the omniagent container is running (the
# sync needs the omniagent HTTP API); never start omniagent just for this -
# skip and log why instead. Fail-soft: a sync error is logged and the backup
# still completes; the sync must never abort or roll back the backup.
echo "[backup] Step 6/6: Git sync via omniagent API..."
OA_CT="$(docker ps -q --filter "label=com.docker.compose.project=${PROJECT}" --filter "name=omniagent" 2>/dev/null | head -1 || true)"
if [ -n "${OA_CT}" ]; then
  if curl -sf -m 90 -X POST -H 'Content-Type: application/json' -d '{}' \
      http://omniagent:8080/git/sync >/tmp/git-sync.out 2>/tmp/git-sync.err; then
    echo "[backup] Git sync OK: $(cat /tmp/git-sync.out)"
  else
    echo "[backup] WARNING: git sync failed - backup continues: $(tail -1 /tmp/git-sync.err 2>/dev/null)"
  fi
  rm -f /tmp/git-sync.out /tmp/git-sync.err
else
  echo "[backup] omniagent container not running - SKIPPING git sync (sync needs the omniagent HTTP API; not starting omniagent just for this)"
fi

# Clean up rclone config
rm -f "$RCLONE_CONF"

echo ""
echo "[backup] Backup complete! (dest: ${DEST}/)"
