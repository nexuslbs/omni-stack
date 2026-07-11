#!/bin/bash
# Backup: sync OMNI_DIR/data/ (including DB backups) to S3
# - PG dumps in custom format → data/backups/omniagent/ and data/backups/mattermost/
# - Grafana SQLite dump → data/backups/grafana/
# - File data sync to S3
set -euo pipefail

OMNI_DIR="${OMNI_DIR:-/opt/omni-stack}"
S3_BUCKET="${S3_BUCKET:-hermes-nexuslbs}"
S3_PREFIX="${S3_PATH:-omni}/data"
S3_ENDPOINT="${S3_ENDPOINT:-https://s3.us-east-005.backblazeb2.com}"
S3_REGION="${S3_REGION:-us-east-005}"

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
echo "[backup] Step 1/5: Copying .env to data/credentials/.env..."
mkdir -p "${OMNI_DIR}/data/credentials"
cp "${OMNI_DIR}/.env" "${OMNI_DIR}/data/credentials/.env"
echo "[backup] .env copied."

# ─── Step 2: OmniAgent PG dump (custom format) ────────────────────────────
echo "[backup] Step 2/5: OmniAgent PostgreSQL dump..."
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
echo "[backup] Step 3/5: Mattermost PostgreSQL (profiles: ${MM_PROFILE})..."

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
  echo "[backup] Step 3/5: Mattermost profile not active -- skipping."
fi

# ─── Step 4: Grafana SQLite backup ────────────────────────────────────────
echo "[backup] Step 4/5: Grafana data..."
if docker ps -q --filter name=omni-grafana 2>/dev/null | grep -q .; then
  GRAFANA_BACKUP="${BACKUP_DIR}/grafana/grafana.db"
  # Use SQLite backup to get a consistent snapshot
  if docker exec omni-grafana sh -c 'sqlite3 /var/lib/grafana/grafana.db ".backup /tmp/grafana-backup.db"' 2>/dev/null; then
    docker cp omni-grafana:/tmp/grafana-backup.db "$GRAFANA_BACKUP" 2>/dev/null
    docker exec omni-grafana rm -f /tmp/grafana-backup.db 2>/dev/null
    if [ -f "$GRAFANA_BACKUP" ] && [ "$(stat -c%s "$GRAFANA_BACKUP")" -gt 1000 ]; then
      echo "[backup] Grafana backup OK ($(stat -c%s "$GRAFANA_BACKUP") bytes)"
    else
      echo "[backup] Grafana backup too small or missing."
      rm -f "$GRAFANA_BACKUP"
    fi
  else
    echo "[backup] Grafana SQLite backup failed -- continuing."
  fi
else
  echo "[backup] Grafana not running -- skipping."
fi

# ─── Step 5: Sync data/ to S3 (includes backups/) ──────────────────────────
echo "[backup] Step 5/5: Syncing file data to S3..."
$RC sync "${OMNI_DIR}/data/" "${DEST}/" \
  --create-empty-src-dirs \
  --s3-no-check-bucket \
  --fast-list \
  --verbose 2>&1 | tail -5

# Clean up rclone config
rm -f "$RCLONE_CONF"

echo ""
echo "[backup] Backup complete! (dest: ${DEST}/)"
