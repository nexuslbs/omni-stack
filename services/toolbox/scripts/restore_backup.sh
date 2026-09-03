#!/bin/bash
# Restore backup: sync S3 data back + restore PG dumps + Grafana + .env
# Stops omniagent, mattermost, grafana before restore, restarts after.
# FIRST step: git sync via the omniagent API (same call as the dashboard
# explorer sync button), so the local config repo state is pulled/pushed
# before anything is restored.
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

# ─── Step 0: Git sync via omniagent API (FIRST step) ───────────────────────
# Pull/push the local config repo state - the SAME API call the dashboard
# explorer sync button performs (POST /git/sync on the omniagent HTTP API,
# which runs the configured sync tool, default `git_sync` from the builtin
# git plugin). Runs BEFORE services are stopped so the omniagent API is
# still available. Guard: only run when the omniagent container is running
# (the sync needs the omniagent HTTP API); never start omniagent just for
# this - skip and log why instead. Fail-soft: a sync error is logged and
# the restore continues; the sync must never abort the restore.
echo "[restore] Step 0/8: Git sync via omniagent API..."
OA_CT="$(docker ps -q --filter "label=com.docker.compose.project=${PROJECT}" --filter "name=omniagent" 2>/dev/null | head -1 || true)"
if [ -n "${OA_CT}" ]; then
  if curl -sf -m 90 -X POST -H 'Content-Type: application/json' -d '{}' \
      http://omniagent:8080/git/sync >/tmp/git-sync.out 2>/tmp/git-sync.err; then
    echo "[restore] Git sync OK: $(cat /tmp/git-sync.out)"
  else
    echo "[restore] WARNING: git sync failed - restore continues: $(tail -1 /tmp/git-sync.err 2>/dev/null)"
  fi
  rm -f /tmp/git-sync.out /tmp/git-sync.err
else
  echo "[restore] omniagent container not running - SKIPPING git sync (sync needs the omniagent HTTP API; not starting omniagent just for this)"
fi

# ─── Step 1: Stop services ─────────────────────────────────────────────────
echo "[restore] Step 1/8: Stopping services..."
docker stop "${PROJECT}-omniagent-1" 2>/dev/null || echo "[restore] omniagent not running"
if docker ps -q --filter name="${PROJECT}-mattermost-1" | grep -q .; then
  docker stop "${PROJECT}-mattermost-1"
  echo "[restore] mattermost stopped"
fi
if [ -n "${GRAFANA_CT}" ]; then
  docker stop "${GRAFANA_CT}"
  echo "[restore] grafana stopped"
fi

# ─── Step 2: Restore file data from S3 ─────────────────────────────────────
echo "[restore] Step 2/8: Restoring file data from S3..."
$RC sync "${SRC}/" "${OMNI_DIR}/data/" \
  --create-empty-src-dirs \
  --s3-no-check-bucket \
  --fast-list \
  --verbose 2>&1 | tail -5

# ─── Step 3: Restore .env ──────────────────────────────────────────────────
echo "[restore] Step 3/8: Restoring .env from data/credentials/.env..."
if [ -f "${OMNI_DIR}/data/credentials/.env" ]; then
  cp "${OMNI_DIR}/data/credentials/.env" "${OMNI_DIR}/.env"
  echo "[restore] .env restored."
  # Re-source restored creds
  set -a
  . "${OMNI_DIR}/.env"
  set +a
fi

# ─── Step 4: Restore OmniAgent PG ──────────────────────────────────────────
echo "[restore] Step 4/8: Restoring OmniAgent PostgreSQL..."
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
  echo "[restore] Step 5/8: Restoring Mattermost PostgreSQL..."
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
  echo "[restore] Step 5/8: Mattermost profile not active -- skipping."
fi

# ─── Step 6: Restore Grafana ──────────────────────────────────────────────
echo "[restore] Step 6/8: Restoring Grafana data..."
if [ -f "${BACKUP_DIR}/grafana/grafana.db" ]; then
  # Restore by mounting the backup into the grafana volume
  # Since the volume is separate, create a temp container to copy it
  if docker volume ls -q | grep -q "^${GRAFANA_VOL}$"; then
    docker run --rm \
      -v "${GRAFANA_VOL}:/target" \
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
echo "[restore] Step 7/8: Starting services..."
docker start "${PROJECT}-omniagent-1" 2>/dev/null || echo "[restore] Starting omniagent..."
# Wait for omniagent to be healthy
for i in $(seq 1 30); do
  if curl -sf http://localhost:8080/health 2>/dev/null | grep -q ok; then
    echo "[restore] omniagent is healthy."
    break
  fi
  sleep 2
done
if docker ps -a -q --filter name="${PROJECT}-mattermost-1" | grep -q .; then
  docker start "${PROJECT}-mattermost-1"
  echo "[restore] mattermost restarted."
fi

if [ -n "${GRAFANA_CT}" ]; then
  docker start "${GRAFANA_CT}"
  echo "[restore] grafana restarted."
fi

rm -f "$RCLONE_CONF"
echo ""
echo "[restore] Restore complete! (source: ${SRC}/)"
