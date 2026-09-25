# syntax=docker/dockerfile:1
#
# workstation service image - ghcr.io/nexuslbs/deepseek-harness
#
# A MIRROR of services/workbench/Dockerfile, but the runtime is the official
# DeepSeek Harness (forked to nexuslbs/deepseek-harness) instead of the
# nexuslbs/workbench core.
#
# CONTRACT (operator directive):
#   * the harness repo is THIRD-PARTY/UPSTREAM and is NEVER modified here: we
#     only `git clone` it at build time (no patch, no injected file);
#   * the image ships the BARE/MINIMAL harness (core only, no capability
#     bundle): every capability - email, sms, totp, browser, web - arrives at
#     RUN TIME from config/workstation.yml and from the plugin sources on the
#     `workstation-cache` NAMED VOLUME (/var/lib/workstation/sources), never
#     from an image layer;
#   * the cordis patch file is a RUN-TIME input, injected through
#     WORKSTATION_CONFIG_FILE (bind-mount + env var), exactly like
#     WORKBENCH_CONFIG_FILE for the workbench service.
#
# BUILD ARGS (the dev overlay passes them; mirrors WORKBENCH_REPO_URL/_REF):
#   WORKSTATION_REPO_URL  default https://github.com/nexuslbs/deepseek-harness
#   WORKSTATION_REF       default master (branch, tag, or commit of the fork)
#   WORKSTATION_PLUGINS_REPO_URL / _REF  plugin sources cloned into the volume
#                        at container start (defaults: workbench-plugins @main)

ARG NODE_IMAGE=node:22-bookworm-slim

# ── stage 1: build the harness from source ─────────────────────────────────
FROM ${NODE_IMAGE} AS builder

# Native toolchain: the harness `pnpm run build` compiles native modules
# (scripts/build.ts -> build:native-system) and needs a C compiler (`cc`),
# make and python3. The slim node image ships none of them
# (root cause of `spawnSync cc ENOENT`).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential python3 make g++ ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

ARG WORKSTATION_REPO_URL=https://github.com/nexuslbs/deepseek-harness
ARG WORKSTATION_REF=master

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git \
 && rm -rf /var/lib/apt/lists/*

# pnpm is the harness' own package manager (pnpm workspace).
RUN corepack enable && corepack prepare pnpm@11.7.0 --activate

WORKDIR /harness
RUN git clone --depth 1 --branch "${WORKSTATION_REF}" "${WORKSTATION_REPO_URL}" . \
 || (git init -q . && git remote add origin "${WORKSTATION_REPO_URL}" \
     && git fetch --depth 1 origin "${WORKSTATION_REF}" && git checkout -q FETCH_HEAD)

# The harness' own install + build (its documented workflow, unmodified).
RUN pnpm install --frozen-lockfile || pnpm install
RUN pnpm run build

# ── stage 2: runtime ───────────────────────────────────────────────────────
FROM ${NODE_IMAGE} AS runtime

ARG WORKSTATION_REPO_URL=https://github.com/nexuslbs/deepseek-harness
ARG WORKSTATION_REF=master
ARG WORKSTATION_PLUGINS_REPO_URL=https://github.com/nexuslbs/workbench-plugins
ARG WORKSTATION_PLUGINS_REF=main

# Debian codename of the Docker apt repository used below (the base image is
# bookworm). Mirrors services/workbench/Dockerfile.
ARG DOCKER_APT_CODENAME=bookworm

# The runtime carries BASE SERVICES ONLY: bash (base image), ssh
# (openssh-client) and the docker CLIENT (docker-ce-cli + docker-compose-plugin,
# NO daemon). A browser is NEVER part of this image and NO Chromium runtime libs
# are baked in: the browser is a SEPARATE service of the stack and the
# `browser-use-playwright` provider ATTACHES to it over CDP
# (`browserService.endpoint` -> http://browser:9222).
ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates git curl openssh-client tini; \
    install -m 0755 -d /etc/apt/keyrings; \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc; \
    chmod a+r /etc/apt/keyrings/docker.asc; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${DOCKER_APT_CODENAME} stable" > /etc/apt/sources.list.d/docker.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin; \
    docker --version; \
    docker compose version; \
    ssh -V; \
    rm -rf /var/lib/apt/lists/*
RUN corepack enable && corepack prepare pnpm@11.7.0 --activate

# the harness sources + build output, verbatim from stage 1
COPY --from=builder /harness /harness

# our compat layer (the ONLY code we add; it lives in THIS repo, not upstream)
# NOTE: /opt is BIND-MOUNTED from the host at runtime (base compose mounts
# /opt:/opt so the live config and plugin sources are visible). Anything the
# image puts under /opt is therefore SHADOWED -> the adapter must live outside
# /opt (a missing adapter silently disables the workbench tool-API shim, which
# makes every workbench plugin die with 'ctx.tools.registerTool is not a function').
COPY adapter /usr/local/share/workstation-adapter
COPY entrypoint.sh /usr/local/bin/workstation-entrypoint

# env contract - same names/semantics as the workbench service, WS prefix
ENV WORKSTATION_DIR=/harness \
    WORKSTATION_CONFIG_FILE=/opt/omni/config/workstation.yml \
    WORKSTATION_CACHE_DIR=/var/lib/workstation/sources \
    WORKSTATION_PROFILE=workstation \
    WORKSTATION_PORT=8080 \
    DSH_HOME=/var/lib/workstation/home \
    WORKSTATION_PLUGINS_REPO_URL=${WORKSTATION_PLUGINS_REPO_URL} \
    WORKSTATION_PLUGINS_REF=${WORKSTATION_PLUGINS_REF} \
    WORKSTATION_REPO_URL=${WORKSTATION_REPO_URL} \
    WORKSTATION_REF=${WORKSTATION_REF}

# the plugin sources live on a NAMED VOLUME so a container/image rebuild never
# re-clones them (mirror of WORKBENCH_CACHE_DIR).
VOLUME ["/var/lib/workstation"]

WORKDIR /harness
RUN chmod +x /usr/local/bin/workstation-entrypoint
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=10 \
  CMD curl -fsS "http://127.0.0.1:${WORKSTATION_PORT}/health" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/workstation-entrypoint"]
CMD []
