#!/bin/bash
# Checkout: create a date-stamped checkout (YYYYMMDD) to S3
# Same as backup but destinations are dated.
set -euo pipefail

OMNI_DIR="${OMNI_DIR:-/opt/omni-stack}"
S3_BUCKET="${S3_BUCKET:-hermes-nexuslbs}"
S3_PREFIX="${S3_PATH:-omni}/checkout/$(date +%Y%m%d)"
S3_ENDPOINT="${S3_ENDPOINT:-https://s3.us-east-005.backblazeb2.com}"
S3_REGION="${S3_REGION:-us-east-005}"

DATE_TAG=$(date +%Y%m%d)
BACKUP_DIR="${OMNI_DIR}/data/backups"
mkdir -p "${BACKUP_DIR}/omniagent" "${BACKUP_DIR}/mattermost" "${BACKUP_DIR}/grafana"

echo "[checkout] Creating checkout ${DATE_TAG}..."

# ── Source credentials ─────────────────────────────────────────────────────
if [ -f "${OMNI_DIR}/.env" ]; then
  set -a
  . "${OMNI_DIR}/.env"
  set +a
fi

if [ -z "${S3_ACCESS_KEY:-}" ] || [ -z "${S3_SECRET_KEY:-}" ]; then
  echo "[checkout] ERROR: S3_ACCESS_KEY and S3_SECRET_KEY must be set"
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

echo "[checkout] Destination: ${DEST}/"

# ─── Step 1: Copy .env ─────────────────────────────────────────────────────
echo "[checkout] Step 1/5: Copying .env..."
mkdir -p "${OMNI_DIR}/data/credentials"
cp "${OMNI_DIR}/.env" "${OMNI_DIR}/data/credentials/.env"

# ─── Step 2: OmniAgent PG dump ─────────────────────────────────────────────
echo "[checkout] Step 2/5: OmniAgent PostgreSQL dump..."
if [ -n "${POSTGRES_PASSWORD:-}" ]; then
  export PGPASSWORD="${POSTGRES_PASSWORD}"
  DUMP="${BACKUP_DIR}/omniagent/omniagent.dump"
  LOG="${BACKUP_DIR}/omniagent/dump.log"
  
  pg_dump -h postgres -U "${POSTGRES_USER:-omniagent}" -d "${POSTGRES_DB:-omniagent}" \
    --format=custom --compress=9 \
    --no-owner --no-acl --clean --if-exists \
    -f "$DUMP" 2>"$LOG"
  unset PGPASSWORD
  
  if [ -f "$DUMP" ] && [ "$(stat -c%s "$DUMP")" -gt 100 ]; then
    if pg_restore -l "$DUMP" >/dev/null 2>>"$LOG"; then
      echo "[checkout] OmniAgent PG dump OK ($(stat -c%s "$DUMP") bytes)"
    else
      echo "[checkout] ERROR: OmniAgent PG dump corrupt!"
      rm -f "$DUMP"
    fi
  else
    echo "[checkout] ERROR: OmniAgent PG dump too small!"
    rm -f "$DUMP"
  fi
fi

# ─── Step 3: Mattermost PG dump ────────────────────────────────────────────
if echo "${COMPOSE_PROFILES:-}" | grep -qE '(mattermost|all)'; then
  echo "[checkout] Step 3/5: Mattermost PostgreSQL..."
  if [ -n "${MM_POSTGRES_PASSWORD:-}" ]; then
    export PGPASSWORD="${MM_POSTGRES_PASSWORD}"
    DUMP="${BACKUP_DIR}/mattermost/mattermost.dump"
    LOG="${BACKUP_DIR}/mattermost/dump.log"
    
    pg_dump -h mattermost-db -U "${MM_POSTGRES_USER:-mmuser}" -d mattermost \
      --format=custom --compress=9 \
      --no-owner --no-acl --clean --if-exists \
      -f "$DUMP" 2>"$LOG" || {
      echo "[checkout] Mattermost PG dump failed -- continuing."
      rm -f "$DUMP"
    }
    unset PGPASSWORD
    
    if [ -f "$DUMP" ] && [ "$(stat -c%s "$DUMP")" -gt 100 ]; then
      if pg_restore -l "$DUMP" >/dev/null 2>>"$LOG"; then
        echo "[checkout] Mattermost PG dump OK ($(stat -c%s "$DUMP") bytes)"
      else
        echo "[checkout] ERROR: Mattermost PG dump corrupt!"
        rm -f "$DUMP"
      fi
    fi
  fi
fi

# ─── Step 4: Grafana ───────────────────────────────────────────────────────
echo "[checkout] Step 4/5: Grafana..."
if docker ps -q --filter name=omni-grafana 2>/dev/null | grep -q .; then
  GFB="${BACKUP_DIR}/grafana/grafana.db"
  if docker exec omni-grafana sh -c 'sqlite3 /var/lib/grafana/grafana.db ".backup /tmp/grafana-ck.db"' 2>/dev/null; then
    docker cp omni-grafana:/tmp/grafana-ck.db "$GFB" 2>/dev/null
    docker exec omni-grafana rm -f /tmp/grafana-ck.db 2>/dev/null
    if [ -f "$GFB" ] && [ "$(stat -c%s "$GFB")" -gt 1000 ]; then
      echo "[checkout] Grafana OK ($(stat -c%s "$GFB") bytes)"
    else
      rm -f "$GFB"
    fi
  fi
fi

# ─── Step 5: Sync to S3 ────────────────────────────────────────────────────
echo "[checkout] Step 5/5: Syncing to S3..."
$RC sync "${OMNI_DIR}/data/" "${DEST}/" \
  --create-empty-src-dirs \
  --s3-no-check-bucket \
  --fast-list \
  --verbose 2>&1 | tail -5

rm -f "$RCLONE_CONF"
echo ""
echo "[checkout] Checkout ${DATE_TAG} complete! (dest: ${DEST}/)"
