#!/bin/bash
# Check Mattermost teams and channels
TOKEN=$(grep "^MATTERMOST_ACCESS_TOKEN=" /opt/data/.env | cut -d= -f2)

echo "=== ALL TEAMS ==="
curl -s -H "Authorization: Bearer $TOKEN" "http://mattermost:8065/api/v4/teams" | python3 -c "
import sys, json
teams = json.load(sys.stdin)
for t in teams:
    print(f'  {t[\"name\"]} (id: {t[\"id\"]})')
"

echo ""
echo "=== CHANNELS IN OMNIAGENT TEAM (w9kmbowq6ty1td5ufy8sdbugda) ==="
curl -s -H "Authorization: Bearer $TOKEN" "http://mattermost:8065/api/v4/teams/w9kmbowq6ty1td5ufy8sdbugda/channels" | python3 -c "
import sys, json
channels = json.load(sys.stdin)
for c in channels:
    print(f'  #{c[\"name\"]} (id: {c[\"id\"]}, type: {c.get(\"type\",\"?\")})')
"

echo ""
echo "=== CHANNELS IN TEST-TEAM (xqhhrmrrafn7tdtpzzxzb8wnur) ==="
curl -s -H "Authorization: Bearer $TOKEN" "http://mattermost:8065/api/v4/teams/xqhhrmrrafn7tdtpzzxzb8wnur/channels" | python3 -c "
import sys, json
channels = json.load(sys.stdin)
for c in channels:
    print(f'  #{c[\"name\"]} (id: {c[\"id\"]}, type: {c.get(\"type\",\"?\")})')
"
