#!/bin/bash
# Backup: sync the compose project's data/ directory (including DB backups) to S3
# - PG dumps in custom format -> data/backups/omniagent/ and data/backups/mattermost/
# - Grafana SQLite dump -> data/backups/grafana/
# - File data sync to S3 (rclone)
# - Remote SELF-VERIFICATION after the sync (artifact sizes + object count), so a
#   broken chain (missing/corrupt dump, wrong bucket, no upload) FAILS LOUDLY with
#   a non-zero exit instead of reporting a silent success.
# - FINAL step: git sync via the omniagent API (same call as the dashboard
#   explorer sync button), fail-soft.
#
# DATA-DIR DETERMINISM (operator requirement, 2026-09-05):
#   The backup source is the data/ directory that sits next to the docker-compose
#   of THIS toolbox container: <compose-project-dir>/data. The project dir is
#   resolved DETERMINISTICALLY from the container's own compose labels
#   (com.docker.compose.project.working_dir, fallback config_files) - NEVER by
#   scanning candidate paths (/opt/omni-stack, /opt/omni) and picking whichever
#   .env happens to carry S3 credentials. OMNI_DIR remains an explicit override
#   for manual runs outside the toolbox container only.
set -euo pipefail

# ---- Deterministic project-dir resolution -----------------------------------
# Print the container-visible path of the compose project directory that defines
# this toolbox container; empty when it cannot be determined.
resolve_project_dir() {
    local host_dir="" dst="" mounts
    # 1) Directory docker compose was invoked from (= where the docker-compose
    #    of this container lives), recorded by Docker at container creation.
    host_dir="$(docker inspect "$HOSTNAME" \
        --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)"
    # 2) Fallback: first compose file of the project, take its directory.
    if [ -z "${host_dir}" ]; then
        host_dir="$(docker inspect "$HOSTNAME" \
            --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' 2>/dev/null || true)"
        host_dir="${host_dir%%,*}"
        host_dir="${host_dir%/*}"
    fi
    [ -n "${host_dir}" ] || return 1
    # 3) Translate host path -> container-visible path: if the project dir (or a
    #    parent of it, e.g. /opt) is bind-mounted into this container, the mount
    #    destination is where the project dir is visible here.
    mounts="$(docker inspect "$HOSTNAME" \
        --format '{{range .Mounts}}{{.Source}}|{{.Destination}}{{"\n"}}{{end}}' 2>/dev/null || true)"
    dst="$(printf '%s' "${mounts}" | awk -F'|' -v h="${host_dir}" '
        $1 == h { print $2; exit }
        $1 != "/" && substr(h, 1, length($1)) == $1 {
            cand = $2 substr(h, length($1) + 1)
            if (length($1) > best) { best = length($1); bestcand = cand }
        }
        END { if (best > 0) print bestcand }
    ')"
    # 4) No matching bind: assume the host path is visible unchanged.
    if [ -z "${dst}" ]; then
        dst="${host_dir}"
    fi
    printf '%s\n' "${dst}"
}

# ---- Compose project dir + data dir -----------------------------------------
PROJECT_DIR=""
if [ -n "${OMNI_DIR:-}" ]; then
    # Explicit override (manual run outside the toolbox container). It must
    # point at the real project dir; validated below like every other source.
    PROJECT_DIR="${OMNI_DIR}"
else
    PROJECT_DIR="$(resolve_project_dir || true)"
fi

if [ -z "${PROJECT_DIR}" ]; then
    echo "[backup] ERROR: cannot determine the compose project directory of this" >&2
    echo "[backup]        toolbox container (com.docker.compose.project.* labels" >&2
    echo "[backup]        missing). Manual runs outside the container must set" >&2
    echo "[backup]        OMNI_DIR=<project dir containing docker-compose.yml, .env and data/>." >&2
    exit 2
fi
if [ ! -f "${PROJECT_DIR}/.env" ] || [ ! -r "${PROJECT_DIR}/.env" ]; then
    echo "[backup] ERROR: ${PROJECT_DIR}/.env missing or unreadable - the compose" >&2
    echo "[backup]        project dir must contain its .env (S3 credentials)." >&2
    exit 2
fi
if [ ! -d "${PROJECT_DIR}/data" ]; then
    echo "[backup] ERROR: ${PROJECT_DIR}/data not found - the compose project dir" >&2
    echo "[backup]        must contain the data/ directory to back up." >&2
    exit 2
fi
DATA_DIR="${PROJECT_DIR}/data"
echo "[backup] Compose project dir (deterministic): ${PROJECT_DIR}"
echo "[backup] Backup source data dir: ${DATA_DIR}/"

S3_BUCKET="${S3_BUCKET:-hermes-nexuslbs}"
S3_PREFIX="${S3_PATH:-omni}/data"
S3_ENDPOINT="${S3_ENDPOINT:-https://s3.us-east-005.backblazeb2.com}"
S3_REGION="${S3_REGION:-us-east-005}"

# ---- Compose project NAME (container filtering) -----------------------------
# Containers/volumes are auto-named per project ({project}-{service}-{index},
# {project}_{volume}) - there are no fixed omni-* names. Derive the project
# name from this container's compose label; fall back to the default name.
COMPOSE_PROJECT="$(docker inspect "$HOSTNAME" --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || true)"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-omni}"
GRAFANA_CT="$(docker ps -q --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" --filter "name=grafana" 2>/dev/null | head -1 || true)"

BACKUP_DIR="${DATA_DIR}/backups"
mkdir -p "${BACKUP_DIR}/omniagent" "${BACKUP_DIR}/mattermost" "${BACKUP_DIR}/grafana"

# ---- Source credentials ------------------------------------------------------
set -a
. "${PROJECT_DIR}/.env"
set +a

if [ -z "${S3_ACCESS_KEY:-}" ] || [ -z "${S3_SECRET_KEY:-}" ]; then
    echo "[backup] ERROR: S3_ACCESS_KEY and S3_SECRET_KEY must be present in ${PROJECT_DIR}/.env" >&2
    exit 2
fi

# ---- Build rclone config ----------------------------------------------------
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

# Accumulated failures: a broken chain must exit non-zero at the end.
FAILURES=""
fail() {
    echo "[backup] ERROR: $1" >&2
    FAILURES="${FAILURES}
- $1"
}

echo "[backup] Starting backup to ${DEST}/"

# ---- Step 1: Copy .env to data/credentials/.env -----------------------------
echo "[backup] Step 1/7: Copying .env to data/credentials/.env..."
mkdir -p "${DATA_DIR}/credentials"
if ! cp "${PROJECT_DIR}/.env" "${DATA_DIR}/credentials/.env"; then
    echo "[backup] ERROR: failed to copy ${PROJECT_DIR}/.env to data/credentials/.env" >&2
    exit 2
fi
if [ ! -s "${DATA_DIR}/credentials/.env" ]; then
    echo "[backup] ERROR: data/credentials/.env is empty after copy" >&2
    exit 2
fi
echo "[backup] .env copied (${DATA_DIR}/credentials/.env)."

# ---- Step 2: OmniAgent PG dump (custom format) ------------------------------
echo "[backup] Step 2/7: OmniAgent PostgreSQL dump..."
OA_USER="${POSTGRES_USER:-omniagent}"
OA_DB="${POSTGRES_DB:-omniagent}"

if [ -n "${POSTGRES_PASSWORD:-}" ]; then
    export PGPASSWORD="${POSTGRES_PASSWORD}"
    DUMP_FILE="${BACKUP_DIR}/omniagent/omniagent.dump"
    LOG_FILE="${BACKUP_DIR}/omniagent/dump.log"

    if ! pg_dump -h "${PGHOST:-postgres}" -U "$OA_USER" -d "$OA_DB" \
        --format=custom --compress=9 \
        --no-owner --no-acl --clean --if-exists \
        -f "$DUMP_FILE" 2>"$LOG_FILE"; then
        echo "[backup] ERROR: pg_dump failed for ${OA_DB}; log tail:" >&2
        tail -5 "$LOG_FILE" >&2 || true
        fail "OmniAgent pg_dump failed (see ${LOG_FILE})"
    fi
    unset PGPASSWORD

    if [ -f "$DUMP_FILE" ] && [ "$(stat -c%s "$DUMP_FILE")" -gt 100 ]; then
        if pg_restore -l "$DUMP_FILE" >/dev/null 2>>"$LOG_FILE"; then
            echo "[backup] OmniAgent PG dump OK ($(stat -c%s "$DUMP_FILE") bytes)"
        else
            echo "[backup] ERROR: OmniAgent PG dump corrupt! Check ${LOG_FILE}" >&2
            rm -f "$DUMP_FILE"
            fail "OmniAgent PG dump failed integrity check (pg_restore -l)"
        fi
    else
        echo "[backup] ERROR: OmniAgent PG dump too small or missing!" >&2
        tail -5 "$LOG_FILE" 2>/dev/null >&2 || true
        rm -f "$DUMP_FILE"
        fail "OmniAgent PG dump missing or too small"
    fi
else
    fail "POSTGRES_PASSWORD not set in ${PROJECT_DIR}/.env - cannot dump omniagent DB"
fi

# ---- Step 3: Mattermost PG dump (custom format) ------------------------------
MM_PROFILE="${COMPOSE_PROFILES:-}"
echo "[backup] Step 3/7: Mattermost PostgreSQL (profiles: ${MM_PROFILE})..."

if echo "$MM_PROFILE" | grep -qE '(mattermost|all)'; then
    if [ -n "${MM_POSTGRES_PASSWORD:-}" ]; then
        export PGPASSWORD="${MM_POSTGRES_PASSWORD}"
        DUMP_FILE="${BACKUP_DIR}/mattermost/mattermost.dump"
        LOG_FILE="${BACKUP_DIR}/mattermost/dump.log"
        if ! pg_dump -h "${MM_DB_HOST:-mattermost-db}" -U "${MM_POSTGRES_USER:-mmuser}" -d mattermost \
            --format=custom --compress=9 \
            --no-owner --no-acl --clean --if-exists \
            -f "$DUMP_FILE" 2>"$LOG_FILE"; then
            echo "[backup] WARNING: Mattermost PG dump failed - continuing." >&2
            rm -f "$DUMP_FILE"
        fi
        unset PGPASSWORD
        if [ -f "$DUMP_FILE" ] && [ "$(stat -c%s "$DUMP_FILE")" -gt 100 ]; then
            echo "[backup] Mattermost PG dump OK ($(stat -c%s "$DUMP_FILE") bytes)"
        else
            echo "[backup] Mattermost PG dump not available - continuing (warning only)." >&2
            rm -f "$DUMP_FILE"
        fi
    else
        echo "[backup] MM_POSTGRES_PASSWORD not set - skipping Mattermost PG dump." >&2
    fi
else
    echo "[backup] Step 3/7: Mattermost profile not active - skipping."
fi

# ---- Step 4: Grafana SQLite backup -------------------------------------------
echo "[backup] Step 4/7: Grafana data..."
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
            echo "[backup] ERROR: Grafana backup too small or missing." >&2
            rm -f "$GRAFANA_BACKUP"
            fail "Grafana SQLite backup missing or too small"
        fi
    else
        rm -f /tmp/grafana-src.db /tmp/grafana-src.db-wal /tmp/grafana-src.db-shm /tmp/grafana-backup.db
        echo "[backup] ERROR: Grafana SQLite backup failed (container ${GRAFANA_CT})." >&2
        fail "Grafana SQLite backup failed (docker cp / sqlite3 snapshot)"
    fi
else
    echo "[backup] Grafana not running - skipping (not an error)."
fi

# ---- Step 5: Sync data/ to S3 (includes backups/) ----------------------------
echo "[backup] Step 5/7: Syncing file data to S3..."
if ! $RC sync "${DATA_DIR}/" "${DEST}/" \
    --create-empty-src-dirs \
    --s3-no-check-bucket \
    --fast-list \
    --verbose 2>&1 | tail -5; then
    fail "rclone sync to ${DEST} failed"
fi

# ---- Step 6: Remote self-verification (DR sanity) ----------------------------
echo "[backup] Step 6/7: Verifying remote backup (self-check)..."
LOCAL_OA=0
LOCAL_GF=0
[ -f "${BACKUP_DIR}/omniagent/omniagent.dump" ] && LOCAL_OA=$(stat -c%s "${BACKUP_DIR}/omniagent/omniagent.dump")
[ -f "${BACKUP_DIR}/grafana/grafana.db" ] && LOCAL_GF=$(stat -c%s "${BACKUP_DIR}/grafana/grafana.db")

if [ "$LOCAL_OA" -gt 0 ]; then
    REMOTE_OA=$($RC lsl "${DEST}/backups/omniagent/omniagent.dump" 2>/dev/null | awk '{print $1}' | head -1 || true)
    if [ -z "${REMOTE_OA:-}" ]; then
        fail "remote omniagent.dump MISSING at ${DEST}/backups/omniagent/ (sync did not upload)"
    elif [ "$REMOTE_OA" != "$LOCAL_OA" ]; then
        fail "remote omniagent.dump size mismatch: remote=${REMOTE_OA} local=${LOCAL_OA}"
    else
        echo "[backup] Remote omniagent.dump OK (${REMOTE_OA} bytes, matches local)"
    fi
else
    fail "local omniagent.dump missing - nothing to verify remotely"
fi

if [ "$LOCAL_GF" -gt 0 ]; then
    REMOTE_GF=$($RC lsl "${DEST}/backups/grafana/grafana.db" 2>/dev/null | awk '{print $1}' | head -1 || true)
    if [ -z "${REMOTE_GF:-}" ]; then
        fail "remote grafana.db MISSING at ${DEST}/backups/grafana/ (sync did not upload)"
    elif [ "$REMOTE_GF" != "$LOCAL_GF" ]; then
        fail "remote grafana.db size mismatch: remote=${REMOTE_GF} local=${LOCAL_GF}"
    else
        echo "[backup] Remote grafana.db OK (${REMOTE_GF} bytes, matches local)"
    fi
fi

# Object count + total size of the whole destination prefix (sanity baseline).
REMOTE_STATS=$($RC size "${DEST}" 2>/dev/null | tail -3 || true)
echo "[backup] Remote destination size:"
echo "${REMOTE_STATS:-unavailable}"

# ---- Step 7: Git sync via omniagent API (FINAL, fail-soft) -------------------
echo "[backup] Step 7/7: Git sync via omniagent API..."
OA_CT="$(docker ps -q --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" --filter "name=omniagent" 2>/dev/null | head -1 || true)"
if [ -n "${OA_CT}" ]; then
    if curl -sf -m 90 -X POST -H 'Content-Type: application/json' -d '{}' \
        http://omniagent:8080/git/sync >/tmp/git-sync.out 2>/tmp/git-sync.err; then
        echo "[backup] Git sync OK: $(cat /tmp/git-sync.out)"
    else
        echo "[backup] WARNING: git sync failed - backup continues: $(tail -1 /tmp/git-sync.err 2>/dev/null || true)"
    fi
    rm -f /tmp/git-sync.out /tmp/git-sync.err
else
    echo "[backup] omniagent container not running - SKIPPING git sync (sync needs the omniagent HTTP API; not starting omniagent just for this)"
fi

# Clean up rclone config
rm -f "$RCLONE_CONF"

if [ -n "${FAILURES}" ]; then
    echo "" >&2
    echo "[backup] BACKUP COMPLETED WITH ERRORS (exit 1):${FAILURES}" >&2
    exit 1
fi

echo ""
echo "[backup] Backup complete and verified! (dest: ${DEST}/)"
