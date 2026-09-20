# syntax=docker/dockerfile:1
#
# workbench service image: a Node runtime that carries the workbench CORE
# checkout, cloned from git AT BUILD TIME (never at container start, never from
# a bind-mounted source). workbench is omniagent-agnostic: this image knows
# nothing about the omni stack except how to run the core.
#
# The clone lands in /workbench, deliberately OUTSIDE /opt: the compose service
# bind-mounts the host /opt at /opt (in-and-out), so a checkout under /opt in
# the image would be shadowed at run time.
#
# CLIENT TOOLS for the plugins' external transports (behind the scenes):
#   git             - the build-time clone above, and plugin sources of kind git
#   curl            - the compose healthcheck
#   openssh-client  - the `ssh` / `ssh+container` transports (keys live under
#                     ${OMNI_DIR}/data/ssh, visible through the /opt mount)
#   docker-ce-cli + - the `container` transport: `docker compose -p <project>
#   docker-compose-   --env-file <env> -f <file> exec -T <service> sh -c '<args>'
#   plugin            into a SIBLING service of the stack (himalaya lives only in
#                     the omni `toolbox` image). CLIENT ONLY: no daemon, no
#                     docker-in-docker, no privileged mode - the container talks
#                     to the HOST daemon through the socket the compose service
#                     mounts (/var/run/docker.sock).
# All of them are installed at BUILD time only: a container start installs
# nothing and the image stays runnable offline.
#
# Build (public repo, no auth - the default; works with the classic builder):
#   docker compose build workbench
#
# Private fork instead of the public nexuslbs/workbench? The token is supplied
# as a BuildKit build secret, so it never touches this file, the compose file or
# any committed artifact: comment out the public clone RUN below, uncomment the
# secret-mount RUN further down, and build with BuildKit (docker-buildx):
#   WORKBENCH_GIT_TOKEN=<token> DOCKER_BUILDKIT=1 docker build \
#     --secret id=github_token,env=WORKBENCH_GIT_TOKEN \
#     -t ghcr.io/nexuslbs/workbench:latest services/workbench

FROM node:22-bookworm-slim

# Debian codename of the Docker apt repository used below. Kept as a build arg
# (the base image is bookworm) so the repository line never depends on shell
# quoting. The Docker apt repo CHANNEL ("stable") is what is pinned, NOT an exact
# package version: Docker prunes old builds, so a version pin turns a rebuild
# into a failure. The resolved versions are printed below at build time.
# Alternative route (not used): the STATIC client binaries
# (download.docker.com/linux/static/stable) - no apt repo and no key, but the
# compose v2 plugin comes from its own GitHub release and must be kept in sync
# by hand.
ARG DOCKER_APT_CODENAME=bookworm

# git (the build-time clone) + curl (the compose healthcheck) + the CLIENT tools
# described in the header (ssh transport, container transport). Docker's apt repo
# supplies docker-ce-cli (the CLI only, NO daemon) and docker-compose-plugin (the
# compose v2 plugin that `docker compose ...` needs).
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates curl openssh-client; \
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

# Clone coordinates: override with build args or the compose service vars.
ARG WORKBENCH_REPO_URL=https://github.com/nexuslbs/workbench
ARG WORKBENCH_REF=main

ENV WORKBENCH_DIR=/workbench

# Build-time clone, anonymous HTTPS (the repo is public: no credential is used,
# passed or stored anywhere). --depth 1 keeps the layer small; the ref is pinned
# by WORKBENCH_REF so a rebuild is reproducible.
RUN set -eux; \
    git clone --depth 1 --branch "${WORKBENCH_REF}" "${WORKBENCH_REPO_URL}" "${WORKBENCH_DIR}"; \
    git -C "${WORKBENCH_DIR}" log -1 --oneline

# Private-fork variant (BuildKit only; see the header). The token lives in the
# secret mount for this single RUN and is not stored in a layer; the public
# remote URL is restored afterwards so no credential ends up in .git/config.
# RUN --mount=type=secret,id=github_token \
#     set -eux; \
#     url="${WORKBENCH_REPO_URL}"; \
#     if [ -s /run/secrets/github_token ]; then \
#       tok="$(cat /run/secrets/github_token)"; \
#       case "$url" in \
#         https://*) url="https://${tok}@${url#https://}" ;; \
#         *) echo "secret github_token ignored: WORKBENCH_REPO_URL is not https" >&2 ;; \
#       esac; \
#     fi; \
#     git clone --depth 1 --branch "${WORKBENCH_REF}" "${url}" "${WORKBENCH_DIR}"; \
#     git -C "${WORKBENCH_DIR}" remote set-url origin "${WORKBENCH_REPO_URL}"; \
#     git -C "${WORKBENCH_DIR}" log -1 --oneline

# Runtime dependencies only: the core strips TypeScript at run time (Node >=
# 22.18), so there is no build step and no dev dependency. Installed HERE, which
# keeps the image runnable offline - the container start installs nothing.
RUN cd "${WORKBENCH_DIR}" \
 && npm ci --omit=dev --no-audit --no-fund \
 && npm cache clean --force

WORKDIR ${WORKBENCH_DIR}

# Status endpoint of the long-running `serve` command (published by the dev
# overlay). CONFIG_FILE is read from the environment at start: empty = the core
# default config (${WORKBENCH_DIR}/workbench.config.yml), non-empty = that path.
EXPOSE 8080

# Long-running entrypoint: boot the plugins and STAY UP (a sleep loop would
# report Up while hosting nothing). --max-old-space-size keeps the V8 heap
# inside the service mem_limit instead of growing until the cgroup OOM-kills it.
CMD ["node", "--max-old-space-size=32", "src/cli.ts", "serve"]
