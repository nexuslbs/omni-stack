ARG VECTOR_IMAGE

FROM ${VECTOR_IMAGE}

USER root

RUN apt-get update && apt-get install -y systemd && rm -rf /var/lib/apt/lists/*

ENV VECTOR_CONFIG_DIR=/etc/vector-main/

COPY sources.toml /etc/vector-main/sources.toml
COPY transforms.toml /etc/vector-main/transforms.toml
COPY sinks.toml /etc/vector-main/sinks.toml
