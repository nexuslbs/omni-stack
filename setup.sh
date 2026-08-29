#!/usr/bin/env bash
#
# setup.sh - one-shot provisioning for a fresh Omni host
# (Vagrant VM or cloud/remote Linux box).
#
# Replaces the old Vagrantfile provisioning (install-docker, install-node-exporter,
# setup-omniagent) and scripts/bootstrap-remote.sh: the Vagrantfile now only copies
# host-side files into /opt/secrets/ and delegates everything else to this script
# (fetched from the omni-stack repo). Remote users can scp/place files in
# /opt/secrets/ and run `sudo bash setup.sh` directly.
#
# Inputs (all OPTIONAL, read from ${SECRETS_DIR:-/opt/secrets}):
#   config.yml   - repo URL, private-repo auth (repo_token / github_app_*),
#                  optional top-level `secrets:` dict (name -> value)
#   .env         - compose environment (may enable COMPOSE_PROFILES / services)
#   <key>.pem    - GitHub App private key; the FILE NAME is the value of the
#                  `github_app_private_key` key in config.yml (as today)
#
# Behavior:
#   1. Installs Docker Engine + compose plugin + node-exporter (apt/yum/dnf).
#   2. If config.yml is missing or has no `repo` key -> stop (only step 1 done).
#   3. Otherwise clones the repo into /opt/omni (private repos via repo_token or
#      a freshly minted GitHub App installation token - same flow the Vagrantfile
#      used to do on the host).
#   4. After the clone:
#        - .env present  -> copy to /opt/omni/.env, `docker compose pull` +
#                           `build` + `up -d` (profiles the user defined).
#        - no .env       -> pull + build the NON-profile-gated compose services
#                           only (as the Vagrantfile did today).
#      If S3_ACCESS_KEY and S3_SECRET_KEY are defined in .env, the toolbox is
#      started and a restore is run from S3 AFTER pull+build and BEFORE `up -d`
#      (see restore_from_s3()).
#   5. If config.yml has a top-level `secrets:` dict, register each secret via
#      the omniagent API (POST /secrets {name, value, fieldType}).
#
# Usage:
#   sudo bash setup.sh
#
# Env overrides: SECRETS_DIR, OMNI_DIR, API_BASE (omniagent API base URL).

set -euo pipefail

SECRETS_DIR="${SECRETS_DIR:-/opt/secrets}"
OMNI_DIR="${OMNI_DIR:-/opt/omni}"
API_BASE="${API_BASE:-http://localhost:8080}"
CONFIG_FILE="${SECRETS_DIR}/config.yml"
ENV_FILE="${SECRETS_DIR}/.env"

log() { echo "==> $*"; }
warn() { echo "WARN: $*" >&2; }
die()  { echo "ERROR: $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run as root (e.g. sudo bash setup.sh)"

# ---------------------------------------------------------------------------
# 1. Install Docker Engine + compose plugin + node-exporter
# ---------------------------------------------------------------------------
install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "Docker + compose plugin already installed: $(docker --version)"
    return
  fi
  log "Installing Docker Engine + compose plugin..."
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl git
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q dnf-plugins-core git
    dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    dnf install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  elif command -v yum >/dev/null 2>&1; then
    yum install -y -q yum-utils git
    yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    yum install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  else
    die "No supported package manager found (need apt-get, dnf, or yum)"
  fi
  systemctl enable docker
  systemctl start docker
  docker --version
  docker compose version
}

install_node_exporter() {
  if command -v node_exporter >/dev/null 2>&1; then
    log "node_exporter already installed: $(node_exporter --version | head -1)"
    return
  fi
  log "Installing Node Exporter (host metrics on :9100)..."
  local VERSION="1.8.2" ARCH="linux-amd64" FILENAME URL
  ARCH="$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')"
  FILENAME="node_exporter-${VERSION}.${ARCH}"
  URL="https://github.com/prometheus/node_exporter/releases/download/v${VERSION}/${FILENAME}.tar.gz"
  ( cd /tmp
    curl -fsSL "$URL" -o node_exporter.tar.gz
    tar xzf node_exporter.tar.gz
    cp "${FILENAME}/node_exporter" /usr/local/bin/node_exporter
    rm -rf "${FILENAME}" node_exporter.tar.gz )
  id -u node_exporter &>/dev/null || useradd -rs /bin/false node_exporter
  cat > /etc/systemd/system/node_exporter.service <<'UNIT'
[Unit]
Description=Prometheus Node Exporter
After=network.target

[Service]
Type=simple
User=node_exporter
Group=node_exporter
ExecStart=/usr/local/bin/node_exporter \
  --web.listen-address=:9100 \
  --path.rootfs=/ \
  --collector.systemd \
  --collector.processes
Restart=always

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now node_exporter
}

# ---------------------------------------------------------------------------
# 2. Read config.yml values (python3+yaml preferred, sed fallback for scalars)
# ---------------------------------------------------------------------------
read_yaml() { # $1 = key -> prints value (or empty)
  local key="$1"
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml' 2>/dev/null; then
    python3 - "$CONFIG_FILE" "$key" <<'PY' 2>/dev/null || true
import sys, yaml
try:
    with open(sys.argv[1]) as f:
        data = yaml.safe_load(f) or {}
    val = data.get(sys.argv[2])
    if isinstance(val, bool):
        print('true' if val else 'false')
    elif isinstance(val, (str, int, float)):
        print(str(val))
    else:
        print('')
except Exception:
    pass
PY
  else
    sed -n "s/^${key}:[[:space:]]*//p" "$CONFIG_FILE" | head -1 | tr -d '"'
  fi
}

# Emit "name<TAB>value" lines for the top-level `secrets:` dict in config.yml.
secrets_to_lines() {
  command -v python3 >/dev/null 2>&1 || return 0
  python3 -c 'import yaml' 2>/dev/null || return 0
  python3 - "$CONFIG_FILE" <<'PY' 2>/dev/null || true
import sys, yaml
try:
    with open(sys.argv[1]) as f:
        data = yaml.safe_load(f) or {}
    secrets = data.get('secrets') or {}
    if isinstance(secrets, dict):
        for name, value in secrets.items():
            print(f"{name}\t{value}")
except Exception:
    pass
PY
}

# ---------------------------------------------------------------------------
# 3. GitHub App installation-token minting (bash port of the Vagrantfile's
#    generate_installation_token - JWT RS256 signed with the app private key,
#    exchanged for a 1-hour installation token via the GitHub API).
# ---------------------------------------------------------------------------
b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

mint_installation_token() { # $1=app_id $2=installation_id $3=key_path
  local app_id="$1" installation_id="$2" key_path="$3"
  local now header payload signing_input sig jwt resp
  command -v openssl >/dev/null 2>&1 || die "openssl required for GitHub App token minting"
  command -v curl  >/dev/null 2>&1 || die "curl required for GitHub App token minting"
  now="$(date +%s)"
  header="$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)"
  payload="$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' "$((now-60))" "$((now+600))" "$app_id" | b64url)"
  signing_input="${header}.${payload}"
  sig="$(printf '%s' "$signing_input" | openssl dgst -sha256 -sign "$key_path" | b64url)"
  jwt="${signing_input}.${sig}"
  resp="$(curl -fsS -X POST \
    -H "Authorization: Bearer ${jwt}" \
    -H 'Accept: application/vnd.github+json' \
    -H 'User-Agent: omni-setup' \
    -H 'Content-Type: application/json' \
    -d '{}' \
    "https://api.github.com/app/installations/${installation_id}/access_tokens" 2>/dev/null)" \
    || die "GitHub App token request failed (check github_app_id / github_installation_id / key)"
  printf '%s' "$resp" | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])' \
    || die "could not parse GitHub App token response"
}

# ---------------------------------------------------------------------------
# 4. Clone / update the configured repo into /opt/omni (private-repo auth via
#    repo_token or a freshly minted GitHub App installation token).
# ---------------------------------------------------------------------------
clone_or_update() { # $1=url $2=token
  local url="${1:-}" token="${2:-}"
  [ -n "$url" ] || die "repo URL is empty (set the 'repo' key in config.yml)"
  if [ -d "$OMNI_DIR/.git" ]; then
    log "/opt/omni already exists - pulling latest"
    git -C "$OMNI_DIR" pull --ff-only || true
    return
  fi
  case "$url" in
    git@*|ssh://*)
      log "Cloning via SSH: ${url}"
      git clone "${url}" "$OMNI_DIR"
      ;;
    https://*)
      if [ -n "$token" ]; then
        log "Cloning private repo over HTTPS with token auth (GIT_ASKPASS; token never touches disk)..."
        # GIT_ASKPASS: git calls this script with the prompt and reads the
        # reply. The script holds no secrets - REPO_TOKEN is read from the
        # environment at call time.
        cat > /tmp/git-askpass.sh <<'ASKPASS'
#!/bin/sh
case "$1" in
  Username*) echo "x-access-token" ;;
  Password*) echo "$REPO_TOKEN" ;;
  *) exit 1 ;;
esac
ASKPASS
        chmod 700 /tmp/git-askpass.sh
        trap 'rm -f /tmp/git-askpass.sh' EXIT
        export REPO_TOKEN="$token"
        export GIT_ASKPASS=/tmp/git-askpass.sh
        export GIT_TERMINAL_PROMPT=0
        if command -v curl >/dev/null 2>&1 && [[ "$url" == https://github.com/* ]]; then
          repo_slug="${url#https://github.com/}"
          repo_slug="${repo_slug%.git}"
          api_code="$(curl -s -o /dev/null -w '%{http_code}' --oauth2-bearer "$token" \
            -H 'Accept: application/vnd.github+json' -H 'User-Agent: omni-setup' \
            "https://api.github.com/repos/${repo_slug}" || echo 000)"
          case "$api_code" in
            200) log "Token check OK: can read ${repo_slug}" ;;
            401|404)
              die "GitHub token rejected (API ${api_code}) - invalid, expired, or no access to ${repo_slug}. Check the repo_token / GitHub App config."
              ;;
            *) warn "token check returned HTTP ${api_code} - continuing anyway" ;;
          esac
        fi
        git clone "$url" "$OMNI_DIR"
        rm -f /tmp/git-askpass.sh
        trap - EXIT
        unset GIT_ASKPASS GIT_TERMINAL_PROMPT REPO_TOKEN
      else
        log "Cloning: ${url}"
        git clone "$url" "$OMNI_DIR"
      fi
      ;;
    *)
      log "Cloning: ${url}"
      git clone "$url" "$OMNI_DIR"
      ;;
  esac
}

# ---------------------------------------------------------------------------
# 5. Compose: .env present -> copy + pull + build + up -d; absent -> pull +
#    build the non-profile-gated services only.
# ---------------------------------------------------------------------------
run_compose() {
  [ -d "$OMNI_DIR" ] || die "$OMNI_DIR does not exist after clone"
  cd "$OMNI_DIR"
  if [ -f "$ENV_FILE" ]; then
    log "Copying ${ENV_FILE} -> ${OMNI_DIR}/.env"
    cp "$ENV_FILE" "${OMNI_DIR}/.env"
    log "Starting services (pull + build + up -d; profiles from .env)..."
    docker compose pull
    docker compose build || warn "source build incomplete - the stack will run from the pulled images"
    restore_from_s3
    docker compose up -d
  else
    log "No .env found - pulling + building core (non-profiled) services only"
    CORE_SERVICES="$(docker compose config --services)"
    docker compose pull $CORE_SERVICES
    docker compose build $CORE_SERVICES || warn "source build incomplete - the stack will run from the pulled images"
    cat <<'MSG'

==> Core images ready. Next steps (operator):
  1. Create /opt/omni/.env (cp .env.example .env) and set POSTGRES_PASSWORD
     before starting the stack (required by postgres).
  2. Start the core services:  docker compose up -d  (in /opt/omni)
  3. Start opt-in profiles:    docker compose --profile mattermost up -d
MSG
  fi
}

# ---------------------------------------------------------------------------
# 5b. S3 restore: after pull + build but BEFORE the full stack starts, if S3
#     credentials (access key + secret) are defined in .env, start the toolbox
#     container and run a restore from S3. Best-effort: a failed restore warns
#     and continues with the stack start (retry manually with
#     `docker compose exec -T toolbox restore_backup`).
# ---------------------------------------------------------------------------
restore_from_s3() {
  [ -f "${OMNI_DIR}/.env" ] || return 0
  set -a
  . "${OMNI_DIR}/.env"
  set +a
  if [ -z "${S3_ACCESS_KEY:-}" ] || [ -z "${S3_SECRET_KEY:-}" ]; then
    log "No S3 credentials (S3_ACCESS_KEY/S3_SECRET_KEY) defined - skipping restore"
    return 0
  fi
  log "S3 credentials found - starting toolbox and running restore from S3 before stack start..."
  cd "$OMNI_DIR"
  # restore_backup restores into postgres (psql -h postgres), so postgres must
  # be up first; the toolbox container carries the restore scripts + rclone.
  docker compose up -d postgres toolbox
  local i
  for i in $(seq 1 30); do
    docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-omniagent}" -d "${POSTGRES_DB:-omniagent}" >/dev/null 2>&1 && break
    sleep 2
  done
  docker compose exec -T toolbox restore_backup \
    || warn "S3 restore failed - continuing with stack start (retry: cd ${OMNI_DIR} && docker compose exec -T toolbox restore_backup)"
}

# ---------------------------------------------------------------------------
# 6. Register config.yml `secrets:` dict entries via the omniagent API
#    (best-effort: POST /secrets {name, value, fieldType}; 409 = exists).
# ---------------------------------------------------------------------------
register_secrets() {
  [ -f "$CONFIG_FILE" ] || return 0
  command -v python3 >/dev/null 2>&1 || { warn "python3 not found - skipping secrets registration"; return 0; }
  python3 -c 'import yaml' 2>/dev/null || { warn "python3-yaml not available - skipping secrets registration"; return 0; }
  command -v curl >/dev/null 2>&1 || { warn "curl not found - skipping secrets registration"; return 0; }
  local line name value payload code
  while IFS=$'\t' read -r name value; do
    [ -n "$name" ] || continue
    payload="$(python3 -c 'import json,sys; print(json.dumps({"name": sys.argv[1], "value": sys.argv[2], "fieldType": "password"}))' "$name" "$value")"
    code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${API_BASE}/secrets" \
      -H 'Content-Type: application/json' -d "$payload" || true)"
    case "$code" in
      200|201) log "Registered secret '${name}'" ;;
      409)     log "Secret '${name}' already exists - skipping" ;;
      *)       warn "could not register secret '${name}' (HTTP ${code:-unreachable}) - register it later via the dashboard/API" ;;
    esac
  done < <(secrets_to_lines)
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
  log "Omni host setup (secrets dir: ${SECRETS_DIR})"
  install_docker
  install_node_exporter

  # 3.1: no config.yml -> only docker+compose+node-exporter (remote bare case)
  if [ ! -f "$CONFIG_FILE" ]; then
    log "No ${CONFIG_FILE} - installed Docker + compose + node-exporter only."
    log "Place config.yml / .env / <key>.pem into ${SECRETS_DIR} and re-run to set up the stack."
    exit 0
  fi
  # 3.1: config.yml present but no repo -> stop
  local repo_url repo_token app_id installation_id key_name key_path token
  repo_url="$(read_yaml repo)"
  if [ -z "$repo_url" ]; then
    log "config.yml present but no 'repo' key - stopping setup (nothing to clone)."
    exit 0
  fi

  # 3.2: resolve auth token (repo_token wins; else GitHub App auto-mint)
  token=""
  repo_token="$(read_yaml repo_token)"
  if [ -n "$repo_token" ]; then
    token="$repo_token"
    log "Using repo_token from config.yml"
  else
    app_id="$(read_yaml github_app_id)"
    installation_id="$(read_yaml github_installation_id)"
    key_name="$(read_yaml github_app_private_key)"
    if [ -n "$app_id" ] && [ -n "$installation_id" ] && [ -n "$key_name" ]; then
      key_path="${SECRETS_DIR}/$(basename "$key_name")"
      if [ -f "$key_path" ]; then
        log "Minting GitHub App installation token from ${key_path}..."
        token="$(mint_installation_token "$app_id" "$installation_id" "$key_path")"
      else
        warn "github_app_private_key file not found at ${key_path} - falling back to unauthenticated clone"
      fi
    fi
  fi

  clone_or_update "$repo_url" "$token"
  run_compose
  register_secrets
  log "Setup complete."
}

main "$@"
