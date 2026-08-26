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

read_repo_key() { # $1 = yaml file -> prints repo URL (or empty)
  local file="$1"
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml' 2>/dev/null; then
    python3 - "$file" <<'PY'
import sys, yaml
try:
    data = yaml.safe_load(open(sys.argv[1])) or {}
    print(data.get("repo") or "")
except Exception:
    pass
PY
  else
    sed -n 's/^repo:[[:space:]]*//p' "$file" | head -1
  fi
}

REPO_URL="$(read_repo_key "$REPO_DIR/config.yml")"
if [ -z "$REPO_URL" ]; then
  log "No config.yml repo key - falling back to config.example.yml default"
  REPO_URL="$(read_repo_key "$REPO_DIR/config.example.yml")"
fi
[ -n "$REPO_URL" ] || die "could not determine repo URL (set the 'repo' key in config.yml)"
log "Repo URL: $REPO_URL"

# ---------------------------------------------------------------------------
# 3. git clone <repo> /opt/omni
# ---------------------------------------------------------------------------
if [ -d /opt/omni/.git ]; then
  log "/opt/omni already exists - pulling latest"
  git -C /opt/omni pull --ff-only || true
elif [ -e /opt/omni ]; then
  die "/opt/omni exists but is not a git checkout - move it away and re-run"
else
  log "Cloning $REPO_URL -> /opt/omni"
  git clone "$REPO_URL" /opt/omni
fi

# ---------------------------------------------------------------------------
# 4. docker compose pull + build (services WITHOUT a profile only)
# ---------------------------------------------------------------------------
cd /opt/omni
log "Pulling + building core services (non-profiled only; profiled services like mattermost/paperclip/noop are opt-in via COMPOSE_PROFILES)"
CORE_SERVICES="$(docker compose config --services)"
log "Core services: ${CORE_SERVICES//$'\n'/ }"
docker compose pull $CORE_SERVICES
docker compose build $CORE_SERVICES

# ---------------------------------------------------------------------------
# 5. Next steps
# ---------------------------------------------------------------------------
cat <<'MSG'

==> Bootstrap complete.

Next steps (operator):
  1. cd /opt/omni && cp .env.example .env
  2. Edit .env: set POSTGRES_PASSWORD (mandatory) and, for opt-in services,
     COMPOSE_PROFILES (e.g. "mattermost,paperclip,memory") plus their secrets.
  3. Start the core services:  docker compose up -d
  4. Start opt-in profiles:    docker compose --profile mattermost up -d
MSG
