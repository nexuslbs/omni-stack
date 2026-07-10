#!/bin/bash
# Restore backup: sync S3 data back + restore PG dumps + Grafana + .env
# Stops omniagent, mattermost, grafana before restore, restarts after.
set -euo pipefail

OMNI_DIR="${OMNI_DIR:-/opt/omni-stack}"
S3_BUCKET="${S3_BUCKET:-hermes-nexuslbs}"
S3_PREFIX="${S3_PATH:-omni}/data"
S3_ENDPOINT="${S3_ENDPOINT:-https://s3.us-east-005.backblazeb2.com}"
S3_REGION="${S3_REGION:-us-east-005}"

BACKUP_DIR="${OMNI_DIR}/data/backups"

# ── Source credentials ─────────────────────────────────────────────────────
if [ -f "${OMNI_DIR}/.env" ]; then
  set -a
  . "${OMNI_DIR}/.env"
  set +a
fi

if [ -z "${S3_ACCESS_KEY:-}" ] || [ -z "${S3_SECRET_KEY:-}" ]; then
  echo "[restore] ERROR: S3_ACCESS_KEY and S3_SECRET_KEY must be set"
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
SRC="omni-s3:${S3_BUCKET}/${S3_PREFIX}"

echo "[restore] Starting restore from ${SRC}/"

# ─── Step 1: Stop services ─────────────────────────────────────────────────
echo "[restore] Step 1/6: Stopping services..."
docker stop omni-omniagent-1 2>/dev/null || echo "[restore] omniagent not running"
if docker ps -q --filter name=omni-mattermost-1 | grep -q .; then
  docker stop omni-mattermost-1
  echo "[restore] mattermost stopped"
fi
if docker ps -q --filter name=omni-grafana | grep -q .; then
  docker stop omni-grafana
  echo "[restore] grafana stopped"
fi

# ─── Step 2: Restore file data from S3 ─────────────────────────────────────
echo "[restore] Step 2/6: Restoring file data from S3..."
$RC sync "${SRC}/" "${OMNI_DIR}/data/" \
  --create-empty-src-dirs \
  --s3-no-check-bucket \
  --fast-list \
  --verbose 2>&1 | tail -5

# ─── Step 3: Restore .env ──────────────────────────────────────────────────
echo "[restore] Step 3/6: Restoring .env from data/credentials/.env..."
if [ -f "${OMNI_DIR}/data/credentials/.env" ]; then
  cp "${OMNI_DIR}/data/credentials/.env" "${OMNI_DIR}/.env"
  echo "[restore] .env restored."
  # Re-source restored creds
  set -a
  . "${OMNI_DIR}/.env"
  set +a
fi

# ─── Step 4: Restore OmniAgent PG ──────────────────────────────────────────
echo "[restore] Step 4/6: Restoring OmniAgent PostgreSQL..."
if [ -f "${BACKUP_DIR}/omniagent/omniagent.dump" ]; then
  
  if [ -n "${POSTGRES_PASSWORD:-}" ]; then
    echo "[restore] Terminating connections to omniagent DB..."
    export PGPASSWORD="${POSTGRES_PASSWORD}"
    psql -h postgres -U "${POSTGRES_USER:-omniagent}" -d postgres \
      -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB:-omniagent}' AND pid <> pg_backend_pid();" 2>/dev/null || true
    psql -h postgres -U "${POSTGRES_USER:-omniagent}" -d postgres \
      -c "DROP DATABASE IF EXISTS ${POSTGRES_DB:-omniagent};" 2>/dev/null || true
    psql -h postgres -U "${POSTGRES_USER:-omniagent}" -d postgres \
      -c "CREATE DATABASE ${POSTGRES_DB:-omniagent};" 2>/dev/null
    
    pg_restore -h postgres -U "${POSTGRES_USER:-omniagent}" -d "${POSTGRES_DB:-omniagent}" \
      --clean --if-exists \
      "${BACKUP_DIR}/omniagent/omniagent.dump" 2>/dev/null || \
      echo "[restore] WARNING: OmniAgent restore had warnings"
    
    unset PGPASSWORD
    echo "[restore] OmniAgent PG restored."
  fi
else
  echo "[restore] No OmniAgent backup found -- skipping."
fi

# ─── Step 5: Restore Mattermost PG (if profile enabled) ────────────────────
MM_PROFILE="${COMPOSE_PROFILES:-}"
if echo "$MM_PROFILE" | grep -qE '(mattermost|all)'; then
  echo "[restore] Step 5/6: Restoring Mattermost PostgreSQL..."
  if [ -f "${BACKUP_DIR}/mattermost/mattermost.dump" ]; then
    if [ -n "${MM_POSTGRES_PASSWORD:-}" ]; then
      echo "[restore] Terminating connections to mattermost DB..."
      export PGPASSWORD="${MM_POSTGRES_PASSWORD}"
      psql -h mattermost-db -U "${MM_POSTGRES_USER:-mmuser}" -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'mattermost' AND pid <> pg_backend_pid();" 2>/dev/null || true
      psql -h mattermost-db -U "${MM_POSTGRES_USER:-mmuser}" -d postgres \
        -c "DROP DATABASE IF EXISTS mattermost;" 2>/dev/null || true
      psql -h mattermost-db -U "${MM_POSTGRES_USER:-mmuser}" -d postgres \
        -c "CREATE DATABASE mattermost;" 2>/dev/null
      
      pg_restore -h mattermost-db -U "${MM_POSTGRES_USER:-mmuser}" -d mattermost \
        --clean --if-exists \
        "${BACKUP_DIR}/mattermost/mattermost.dump" 2>/dev/null || \
        echo "[restore] WARNING: Mattermost restore had warnings"
      
      unset PGPASSWORD
      echo "[restore] Mattermost PG restored."
    fi
  else
    echo "[restore] No Mattermost backup found -- skipping."
  fi
else
  echo "[restore] Step 5/6: Mattermost profile not active -- skipping."
fi

# ─── Step 6: Restore Grafana ──────────────────────────────────────────────
echo "[restore] Step 6/7: Restoring Grafana data..."
if [ -f "${BACKUP_DIR}/grafana/grafana.db" ]; then
  # Restore by mounting the backup into the grafana volume
  # Since the volume is separate, create a temp container to copy it
  if docker volume ls -q | grep -q omni-grafana-vol; then
    docker run --rm \
      -v omni-grafana-vol:/target \
      -v "${BACKUP_DIR}/grafana:/source:ro" \
      alpine sh -c 'cp /source/grafana.db /target/ && chown 472:472 /target/grafana.db' \
      2>/dev/null && echo "[restore] Grafana data restored." || \
      echo "[restore] Grafana restore had issues -- continuing."
  else
    echo "[restore] Grafana volume not found -- skipping."
  fi
else
  echo "[restore] No Grafana backup found -- skipping."
fi

# ─── Step 7: Start services ────────────────────────────────────────────────
echo "[restore] Step 7/7: Starting services..."
docker start omni-omniagent-1 2>/dev/null || echo "[restore] Starting omniagent..."
# Wait for omniagent to be healthy
for i in $(seq 1 30); do
  if curl -sf http://localhost:8080/health 2>/dev/null | grep -q ok; then
    echo "[restore] omniagent is healthy."
    break
  fi
  sleep 2
done

if docker ps -a -q --filter name=omni-mattermost-1 | grep -q .; then
  docker start omni-mattermost-1
  echo "[restore] mattermost restarted."
fi

if docker ps -a -q --filter name=omni-grafana | grep -q .; then
  docker start omni-grafana
  echo "[restore] grafana restarted."
fi

rm -f "$RCLONE_CONF"
echo ""
echo "[restore] Restore complete! (source: ${SRC}/)"
