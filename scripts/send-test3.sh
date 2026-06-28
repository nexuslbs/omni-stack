#!/bin/bash
# Login and send test message - uses env var for token
set -e
curl -s -X POST http://mattermost:8065/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"testuser","password":"TestP@ss123!"}' \
  -D /tmp/lh6.txt -o /dev/null
USER_TOKEN=*** -i "^Token:" /tmp/lh6.txt | cut -d" " -f2 | tr -d "\r\n")
curl -s -X POST http://mattermost:8065/api/v4/posts \
  -H "Authorization: Bearer *** \
  -H "Content-Type: application/json" \
  -d '{"channel_id":"4eb9s63aibd3bepf1p1j3sj79w","message":"Testing provider resolution - tell me the current date."}'
echo ""
