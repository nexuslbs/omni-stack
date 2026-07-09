#!/bin/bash
# Checkout: sync OMNI_DIR/data/ + PG dumps + .env to S3 with date-stamped prefix
set -euo pipefail

OMNI_DIR="${OMNI_DIR:-/opt/omni-stack}"
S3_BUCKET="hermes-nexuslbs"
S3_PREFIX="omni/checkout/$(date +%Y%m%d)"
S3_ENDPOINT="https://s3.us-east-005.backblazeb2.com"
S3_REGION="us-east-005"
TMPDIR="/tmp/omni-checkout-$$"
mkdir -p "$TMPDIR"

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
DEST="omni-s3:${S3_BUCKET}/${S3_PREFIX}"

echo "[checkout] Starting checkout to ${DEST}/"

# ─── Step 1: Copy .env to data/credentials/.env ────────────────────────────
echo "[checkout] Step 1/5: Copying .env to data/credentials/.env..."
mkdir -p "${OMNI_DIR}/data/credentials"
cp "${OMNI_DIR}/.env" "${OMNI_DIR}/data/credentials/.env"

# ─── Step 2: File data sync ───────────────────────────────────────────────
echo "[checkout] Step 2/5: Syncing file data..."
$RC sync "${OMNI_DIR}/data/" "${DEST}/data/" \
  --create-empty-src-dirs \
  --s3-no-check-bucket \
  --fast-list \
  --exclude "backup/**" \
  --verbose 2>&1 | tail -5

# ─── Step 3: OmniAgent PG dump ─────────────────────────────────────────────
echo "[checkout] Step 3/5: OmniAgent PostgreSQL dump..."
if [ -n "${POSTGRES_PASSWORD:-}" ]; then
  export PGPASSWORD="${POSTGRES_PASSWORD}"
  pg_dump -h postgres -U "${POSTGRES_USER:-omniagent}" -d "${POSTGRES_DB:-omniagent}" \
    --no-owner --no-acl --clean --if-exists 2>/dev/null | gzip > "${TMPDIR}/omniagent-dump.sql.gz"
  unset PGPASSWORD
  if [ -s "${TMPDIR}/omniagent-dump.sql.gz" ]; then
    $RC copy "${TMPDIR}/omniagent-dump.sql.gz" "${DEST}/db/" --s3-no-check-bucket
  fi
fi

# ─── Step 4: Mattermost PG dump (if profile enabled) ───────────────────────
MM_PROFILE="${COMPOSE_PROFILES:-}"
if echo "$MM_PROFILE" | grep -qE '(mattermost|all)'; then
  if [ -n "${MM_POSTGRES_PASSWORD:-}" ]; then
    export PGPASSWORD="${MM_POSTGRES_PASSWORD}"
    pg_dump -h mattermost-db -U "${MM_POSTGRES_USER:-mmuser}" -d mattermost \
      --no-owner --no-acl --clean --if-exists 2>/dev/null | gzip > "${TMPDIR}/mattermost-dump.sql.gz" || true
    unset PGPASSWORD
    if [ -s "${TMPDIR}/mattermost-dump.sql.gz" ]; then
      $RC copy "${TMPDIR}/mattermost-dump.sql.gz" "${DEST}/db/" --s3-no-check-bucket
    fi
  fi
fi

# ─── Step 5: Re-sync data/ ─────────────────────────────────────────────────
echo "[checkout] Step 5/5: Re-syncing data/..."
$RC sync "${OMNI_DIR}/data/" "${DEST}/data/" \
  --create-empty-src-dirs \
  --s3-no-check-bucket \
  --fast-list \
  --exclude "backup/**" \
  --verbose 2>&1 | tail -5

rm -rf "$TMPDIR" "$RCLONE_CONF"
echo ""
echo "[checkout] Checkout complete! (dest: ${DEST}/)"
