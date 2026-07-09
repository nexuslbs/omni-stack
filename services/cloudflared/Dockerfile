FROM cloudflare/cloudflared:latest

COPY config.yaml /etc/cloudflared/config.yaml

ENTRYPOINT ["cloudflared", "tunnel", "--config", "/etc/cloudflared/config.yaml", "run"]
