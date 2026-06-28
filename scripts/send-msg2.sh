#!/bin/bash
set -e
# Log in as testuser and send a message

# Get user token
USER=... ${USER}...)
curl -s -X POST http://mattermost:8065/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"testuser","password":"TestP@ss123!"}' \
  -D /tmp/login_hdr5.txt -o /dev/null 2>/dev/null
USER_TOKEN=$(grep -i "^Token:" /tmp/login_hdr5.txt | cut -d' ' -f2 | tr -d '\r\n')

echo "Sending test message..."
curl -s -X POST http://mattermost:8065/api/v4/posts \
  -H "Authorization: Bearer *** \
  -H "Content-Type: application/json" \
  -d '{"channel_id":"4eb9s63aibd3bepf1p1j3sj79w","message":"Hello omniagent! Just testing - what is 2+2?"}'
echo ""
