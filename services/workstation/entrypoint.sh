#!/bin/sh
# workstation container entrypoint.
#
# Mirrors the workbench service contract:
#   * the PLUGIN SOURCES live on the `workstation-cache` named volume
#     (WORKSTATION_CACHE_DIR, default /var/lib/workstation/sources) and are
#     cloned ONCE - an image or container rebuild never re-clones them;
#   * the cordis SOURCES+PLUGINS config is a RUN-TIME input read from
#     WORKSTATION_CONFIG_FILE (bind-mount + env var), never an image layer;
#   * the harness boots with the MINIMAL/headless profile - every capability
#     comes from the config file + the plugin sources.
set -eu

HARNESS_DIR="${WORKSTATION_DIR:-/harness}"
CONFIG_FILE="${WORKSTATION_CONFIG_FILE:-/opt/omni/config/workstation.yml}"
CACHE_DIR="${WORKSTATION_CACHE_DIR:-/var/lib/workstation/sources}"
PROFILE="${WORKSTATION_PROFILE:-workstation}"
PORT="${WORKSTATION_PORT:-8080}"
PLUGINS_REPO_URL="${WORKSTATION_PLUGINS_REPO_URL:-https://github.com/nexuslbs/workbench-plugins}"
PLUGINS_REF="${WORKSTATION_PLUGINS_REF:-main}"

export DSH_HOME="${DSH_HOME:-/var/lib/workstation/home}"
export WORKSTATION_PORT="$PORT"

log() { echo "[workstation] $*"; }

# ── 1. plugin sources (named volume, cloned once) ──────────────────────────
mkdir -p "$CACHE_DIR"
PLUGINS_DIR="$CACHE_DIR/$(basename "$PLUGINS_REPO_URL" .git)"
if [ ! -d "$PLUGINS_DIR/.git" ]; then
  log "cloning plugin sources $PLUGINS_REPO_URL ($PLUGINS_REF) -> $PLUGINS_DIR"
  rm -rf "$PLUGINS_DIR"
  if ! git clone --depth 1 --branch "$PLUGINS_REF" "$PLUGINS_REPO_URL" "$PLUGINS_DIR"; then
    log "WARN: plugin source clone failed; continuing with whatever is cached"
  fi
else
  log "plugin sources already cached at $PLUGINS_DIR (no re-clone)"
fi

# ── 2. harness profile: minimal (headless) + our overlay ───────────────────
# The profile is assembled at run time from the harness' OWN bundles; nothing
# capability-related is baked into the image.
PROFILE_DIR="$DSH_HOME/profiles/$PROFILE"
mkdir -p "$PROFILE_DIR"

# make the cached plugin packages resolvable from the profile (node_modules
# symlinks: a package name such as `workbench-plugins/...` resolves through
# DSH_HOME/profiles/<profile>/node_modules).
if [ -d "$PLUGINS_DIR" ]; then
  mkdir -p "$PROFILE_DIR/node_modules"
  for pkg in "$PLUGINS_DIR"/*/package.json; do
    [ -f "$pkg" ] || continue
    src_dir=$(dirname "$pkg")
    name=$(basename "$src_dir")
    [ -e "$PROFILE_DIR/node_modules/$name" ] || ln -s "$src_dir" "$PROFILE_DIR/node_modules/$name"
  done
fi

if [ ! -f "$CONFIG_FILE" ]; then
  log "WARN: config file $CONFIG_FILE not found - booting the minimal harness only"
else
  log "using cordis sources+plugins config: $CONFIG_FILE"
fi

# ── 3. boot the harness CLI ────────────────────────────────────────────────
BIN="$HARNESS_DIR/apps/cli/lib/bin.js"
[ -f "$BIN" ] || BIN="$HARNESS_DIR/apps/cli/src/bin.ts"
log "booting harness: node $BIN --profile web --patch $CONFIG_FILE (internal port ${HARNESS_PORT:-0}; facade port $PORT)"

# The harness webserver must NOT bind the facade port: our compat adapter
# (`workstation-http`) owns 8080 and serves /health + /api/tool/call for the
# omni `workstation` remote plugin. Port 0 = OS-assigned internal port.
if [ -f "$CONFIG_FILE" ]; then
  # NOTE: the harness CLI only accepts `--patch` immediately after `--profile`;
  # any other option BEFORE it makes the profile subparser reject it
  # ("error: unknown option '--patch'").
  exec node "$BIN" --profile web --patch "$CONFIG_FILE" --no-open --port "${HARNESS_PORT:-0}"
else
  exec node "$BIN" --profile web --port "${HARNESS_PORT:-0}" --no-open
fi
