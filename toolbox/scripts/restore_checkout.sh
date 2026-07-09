#!/bin/bash
# Restore checkout: restore from date-stamped S3 checkout
# Usage: restore_checkout YYYYMMDD
set -euo pipefail

OMNI_DIR="${OMNI_DIR:-/opt/omni-stack}"
S3_BUCKET="hermes-nexuslbs"
S3_ENDPOINT="https://s3.us-east-005.backblazeb2.com"
S3_REGION="us-east-005"

if [ $# -lt 1 ]; then
  echo "Usage: restore_checkout YYYYMMDD"
  echo "Example: restore_checkout 20260709"
  exit 1
fi

DATE_SUFFIX="$1"
if ! echo "$DATE_SUFFIX" | grep -qE '^[0-9]{8}$'; then
  echo "Error: Date must be in YYYYMMDD format (got: $DATE_SUFFIX)"
  exit 1
fi

TMPDIR="/tmp/omni-restore-$$"
mkdir -p "$TMPDIR"

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
RCLONE_CONF=$(mktemp /tmp/rclone-conf-XXXXXX.conf)
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
SRC="omni-s3:${S3_BUCKET}/omni/checkout/${DATE_SUFFIX}"

echo "[restore] Starting restore from checkout ${DATE_SUFFIX} (${SRC}/)"

# ─── Step 1: Stop services ─────────────────────────────────────────────────
echo "[restore] Step 1/6: Stopping omniagent and mattermost..."
docker stop omni-omniagent-1 2>/dev/null || true
if docker ps -q --filter name=omni-mattermost-1 | grep -q .; then
  docker stop omni-mattermost-1 || true
fi

# ─── Step 2: Restore file data ─────────────────────────────────────────────
echo "[restore] Step 2/6: Restoring file data..."
$RC sync "${SRC}/data/" "${OMNI_DIR}/data/" \
  --create-empty-src-dirs \
  --s3-no-check-bucket \
  --fast-list \
  --verbose 2>&1 | tail -5

# ─── Step 3: Restore .env ──────────────────────────────────────────────────
echo "[restore] Step 3/6: Restoring .env..."
if [ -f "${OMNI_DIR}/data/credentials/.env" ]; then
  cp "${OMNI_DIR}/data/credentials/.env" "${OMNI_DIR}/.env"
fi

# ─── Step 4: Restore OmniAgent PG ──────────────────────────────────────────
echo "[restore] Step 4/6: Restoring OmniAgent PostgreSQL..."
if $RC ls "${SRC}/db/omniagent-dump.sql.gz" &>/dev/null; then
  $RC copy "${SRC}/db/omniagent-dump.sql.gz" "${TMPDIR}/" --s3-no-check-bucket
  set -a; . "${OMNI_DIR}/.env"; set +a
  if [ -n "${POSTGRES_PASSWORD:-}" ]; then
    export PGPASSWORD=***    psql -h postgres -U "${POSTGRES_USER:-omniagent}" -d postgres -c \
      "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB:-omniagent}' AND pid <> pg_backend_pid();" 2>/dev/null || true
    psql -h postgres -U "${POSTGRES_USER:-omniagent}" -d postgres \
      -c "DROP DATABASE IF EXISTS ${POSTGRES_DB:-omniagent};" 2>/dev/null || true
    psql -h postgres -U "${POSTGRES_USER:-omniagent}" -d postgres \
      -c "CREATE DATABASE ${POSTGRES_DB:-omniagent};" 2>/dev/null
    gunzip -c "${TMPDIR}/omniagent-dump.sql.gz" | psql -h postgres -U "${POSTGRES_USER:-omniagent}" -d "${POSTGRES_DB:-omniagent}" 2>/dev/null
    unset PGPASSWORD
  fi
fi

# ─── Step 5: Restore Mattermost PG (if profile enabled) ────────────────────
MM_PROFILE="${COMPOSE_PROFILES:-}"
if echo "$MM_PROFILE" | grep -qE '(mattermost|all)'; then
  echo "[restore] Step 5/6: Restoring Mattermost PostgreSQL..."
  if $RC ls "${SRC}/db/mattermost-dump.sql.gz" &>/dev/null; then
    $RC copy "${SRC}/db/mattermost-dump.sql.gz" "${TMPDIR}/" --s3-no-check-bucket
    set -a; . "${OMNI_DIR}/.env"; set +a
    if [ -n "${MM_POSTGRES_PASSWORD:-}" ]; then
      export PGPASSWORD=***      psql -h mattermost-db -U "${MM_POSTGRES_USER:-mmuser}" -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'mattermost' AND pid <> pg_backend_pid();" 2>/dev/null || true
      psql -h mattermost-db -U "${MM_POSTGRES_USER:-mmuser}" -d postgres \
        -c "DROP DATABASE IF EXISTS mattermost;" 2>/dev/null || true
      psql -h mattermost-db -U "${MM_POSTGRES_USER:-mmuser}" -d postgres \
        -c "CREATE DATABASE mattermost;" 2>/dev/null
      gunzip -c "${TMPDIR}/mattermost-dump.sql.gz" | psql -h mattermost-db -U "${MM_POSTGRES_USER:-mmuser}" -d mattermost 2>/dev/null
      unset PGPASSWORD
    fi
  fi
fi

# ─── Step 6: Start services ────────────────────────────────────────────────
echo "[restore] Step 6/6: Starting services..."
docker start omni-omniagent-1 2>/dev/null || true
for i in $(seq 1 30); do
  if curl -sf http://localhost:8080/health 2>/dev/null | grep -q ok; then
    echo "[restore] omniagent is healthy."
    break
  fi
  sleep 2
done

if docker ps -q --filter name=omni-mattermost-1 | grep -q .; then
  docker start omni-mattermost-1 || true
fi

rm -rf "$TMPDIR" "$RCLONE_CONF"
echo ""
echo "[restore] Restore from checkout ${DATE_SUFFIX} complete."
