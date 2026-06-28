#!/bin/bash
set -e
# Read token from .env
TOKEN=$(grep "^MATTERMOST_ACCESS_TOKEN=" /opt/data/.env | cut -d= -f2)

# Login as testuser, get token
LOGIN_RESP=$(curl -s -X POST http://mattermost:8065/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"testuser","password":"TestP@ss123!"}')

# Get token from response header
USER_TOKEN=$(curl -s -X POST http://mattermost:8065/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"testuser","password":"TestP@ss123!"}' \
  -D /tmp/login_hdr4.txt -o /dev/null 2>/dev/null && \
  grep -i "^Token:" /tmp/login_hdr4.txt | cut -d' ' -f2 | tr -d '\r\n')

echo "=== Sending test message ==="
RESULT=$(curl -s -X POST http://mattermost:8065/api/v4/posts \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel_id":"4eb9s63aibd3bepf1p1j3sj79w","message":"Hello omniagent! Please summarize FastAPI vs Sanic vs aiohttp."}')
echo "Result: $RESULT"
