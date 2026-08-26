#!/usr/bin/env bash
#
# bootstrap-remote.sh - Cloud-VM bootstrap for Omni Stack
#
# The cloud equivalent of the Vagrantfile provisioning: run this on a fresh
# Linux box (Cloud provider VM) to install Docker, clone the configured repo
# into /opt/omni, and pull/build the core (non-profiled) services.
#
# Requirements: root (or sudo), curl + git available or installable via
# apt-get / yum / dnf.
#
# Usage:
#   sudo bash scripts/bootstrap-remote.sh
#
# It reads the repo URL from config.yml (`repo` key - the same structure as
# the Vagrantfile), falling back to the default in config.example.yml.

set -euo pipefail

log() { echo "==> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Install Docker Engine + compose plugin (apt/yum/dnf detection)
# ---------------------------------------------------------------------------
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  log "Docker + compose plugin already installed: $(docker --version)"
else
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
fi
docker --version
docker compose version

# ---------------------------------------------------------------------------
# 2. Resolve the repo URL from config.yml (`repo` key), fall back to
#    config.example.yml default
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Walk up from the script dir to find the repo root (contains config.example.yml)
REPO_DIR="$SCRIPT_DIR"
while [ ! -f "$REPO_DIR/config.example.yml" ] && [ "$REPO_DIR" != "/" ]; do
  REPO_DIR="$(dirname "$REPO_DIR")"
done
[ -f "$REPO_DIR/config.example.yml" ] || die "config.example.yml not found under $SCRIPT_DIR"

read_config_value() { # $1 = yaml file, $2 = key -> prints value (or empty)
  local file="$1" key="$2"
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml' 2>/dev/null; then
    python3 - "$file" "$key" <<'PY'
import sys, yaml
try:
    data = yaml.safe_load(open(sys.argv[1])) or {}
    print(data.get(sys.argv[2]) or "")
except Exception:
    pass
PY
  else
    sed -n "s/^${key}:[[:space:]]*//p" "$file" | head -1
  fi
}

REPO_URL="$(read_config_value "$REPO_DIR/config.yml" repo)"
if [ -z "$REPO_URL" ]; then
  log "No config.yml repo key - falling back to config.example.yml default"
  REPO_URL="$(read_config_value "$REPO_DIR/config.example.yml" repo)"
fi
[ -n "$REPO_URL" ] || die "could not determine repo URL (set the 'repo' key in config.yml)"
REPO_TOKEN="$(read_config_value "$REPO_DIR/config.yml" repo_token)"
log "Repo URL: $REPO_URL"

# ---------------------------------------------------------------------------
# 3. git clone <repo> /opt/omni (private-repo auth: SSH URL or repo_token)
# ---------------------------------------------------------------------------
clone_or_update() {
  local url="${1:-}" token="${2:-}"
  [ -n "$url" ] || die "could not determine repo URL (set the 'repo' key in config.yml)"
  if [ -d /opt/omni/.git ]; then
    log "/opt/omni already exists - pulling latest"
    git -C /opt/omni pull --ff-only || true
  elif [ -e /opt/omni ]; then
    die "/opt/omni exists but is not a git checkout - move it away and re-run"
  else
    case "$url" in
      git@*|ssh://*)
        log "Cloning via SSH: $url"
        git clone "$url" /opt/omni
        ;;
      https://*)
        if [ -n "$token" ]; then
          log "Cloning private repo over HTTPS with token auth (GIT_ASKPASS; token never touches disk)..."
          # GIT_ASKPASS: git calls this script with the prompt ("Username for ..." /
          # "Password for ...") and reads the reply. The script holds no secrets -
          # REPO_TOKEN is read from the environment at call time.
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
          # Validate the token against the GitHub API before cloning.
          # Prints only the HTTP status code - the token is never echoed.
          if command -v curl >/dev/null 2>&1 && [[ "$url" == https://github.com/* ]]; then
            repo_slug="${url#https://github.com/}"
            repo_slug="${repo_slug%.git}"
            api_code="$(curl -s -o /dev/null -w '%{http_code}' --oauth2-bearer "$token" -H 'Accept: application/vnd.github+json' -H 'User-Agent: omni-bootstrap' "https://api.github.com/repos/${repo_slug}" || echo 000)"
            case "$api_code" in
              200) log "Token check OK: can read ${repo_slug}" ;;
              401|404)
                die "GitHub token rejected (API ${api_code}) - invalid, expired, or no access to ${repo_slug}. Check the 'repo_token' value in config.yml."
                ;;
              *)   log "WARN: token check returned HTTP ${api_code} - continuing anyway" ;;
            esac
          fi
          git clone "$url" /opt/omni
          rm -f /tmp/git-askpass.sh
          trap - EXIT
        else
          log "Cloning: $url"
          git clone "$url" /opt/omni
        fi
        ;;
      *)
        log "Cloning: $url"
        git clone "$url" /opt/omni
        ;;
    esac
  fi
}

clone_or_update "$REPO_URL" "$REPO_TOKEN"

# ---------------------------------------------------------------------------
# 4. Fresh-machine .env + docker compose pull + build (non-profiled services)
# ---------------------------------------------------------------------------
cd /opt/omni

# Create .env from the tracked template when missing (generates a random
# POSTGRES_PASSWORD; the template pins the PUBLIC omni-deployer GHCR images
# so `docker compose pull` needs no registry login).
if [ ! -f .env ]; then
  log "Creating /opt/omni/.env from .env.example..."
  cp .env.example .env
  if ! grep -q '^POSTGRES_PASSWORD=.\+' .env; then
    GEN_PW="$(openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    printf 'POSTGRES_PASSWORD=%s\n' "$GEN_PW" >> .env
    log "  (generated random POSTGRES_PASSWORD)"
  fi
fi

log "Pulling + building core services (non-profiled only; profiled services like mattermost/paperclip/noop are opt-in via COMPOSE_PROFILES)"
CORE_SERVICES="$(docker compose config --services)"
log "Core services: ${CORE_SERVICES//$'\n'/ }"
docker compose pull $CORE_SERVICES
# Best-effort source build for services with a build context (e.g. the
# toolbox Dockerfile in the repo); the stack runs from the pulled images
# either way.
docker compose build $CORE_SERVICES || log "WARN: source build incomplete - the stack will run from the pulled images"

# ---------------------------------------------------------------------------
# 5. Next steps
# ---------------------------------------------------------------------------
cat <<'MSG'

==> Bootstrap complete.

Next steps (operator):
  1. /opt/omni/.env was auto-created (generated POSTGRES_PASSWORD + public
     GHCR image pins). Edit it if you want COMPOSE_PROFILES or other secrets.
  2. Start the core services:  docker compose up -d
  3. Start opt-in profiles:    docker compose --profile mattermost up -d
MSG
