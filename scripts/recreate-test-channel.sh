#!/bin/bash
set -e

TOKEN=*** "^MATTERMOST_ACCESS_TOKEN=*** /opt/data/.env | cut -d= -f2)
AUTH=***Bearer $TOKEN"
SERVER="http://mattermost:8065"
TEAM_ID="w9kmbowq6ty1td5ufy8sdbugda"  # omniagent team
OLD_CHANNEL_ID="t96uf5zmy3r3iqen91bgdpd3da"
BOT_ID="1bg8a6szhif1dkp1i1m4p4dc8c"

echo "=== Creating test channel in omniagent team ==="

# Check if "test" already exists in omniagent team
EXISTING_CHAN=*** .//tmp/existing_chan.json)
curl -s -H "$AUTH" "$SERVER/api/v4/teams/$TEAM_ID/channels" > /tmp/channels.json
CHAN_NAME=*** //tmp/channels.json | python3 -c "import sys,json; cs=json.load(sys.stdin); print(next((c['id'] for c in cs if c['name']=='test'), ''))")

if [ -n "*** ]; then
    echo "Channel 'test' already exists in omniagent team: ***
    NEW_CHANNEL_ID=***>
else
    echo "Creating new 'test' channel..."
    NEW_CHANNEL_ID=*** //tmp/new_chan.json)
    curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
      -d "{\"team_id\":\"$TEAM_ID\",\"name\":\"test\",\"display_name\":\"Test\",\"type\":\"O\"}" \
      "$SERVER/api/v4/channels" > /tmp/new_chan.json
    NEW_CHANNEL_ID=*** //tmp/new_chan.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))")
fi

if [ -z "*** ]; then
    echo "ERROR: Failed to get/create channel"
    cat /tmp/new_chan.json
    exit 1
fi

echo "Using channel ID: ***

# Add bot to channel
echo "Adding bot to channel..."
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$BOT_ID\"}" \
  "$SERVER/api/v4/channels/$NEW_CHANNEL_ID/members" > /dev/null

# Add testuser to channel
echo "Getting testuser ID..."
TESTUSER_ID=*** //tmp/testuser.json | python3 -c "import sys,json; users=json.load(sys.stdin); print(next((u['id'] for u in users if u['username']=='testuser'), ''))")
curl -s -H "$AUTH" "$SERVER/api/v4/users" > /tmp/users.json
TESTUSER_ID=*** //tmp/testuser.json | python3 -c "
import sys,json
users=json.load(sys.stdin)
print(next((u['id'] for u in users if u['username']=='testuser'), ''))
")

if [ -n "*** ]; then
    echo "Adding testuser to channel..."
    curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
      -d "{\"user_id\":\"$TESTUSER_ID\"}" \
      "$SERVER/api/v4/channels/$NEW_CHANNEL_ID/members" > /dev/null
fi

# Update DB channel mapping
echo "Updating DB channel mapping..."
DATABASE_URL="postgres://omniagent:***@postgres:5432/omniagent"
psql "$DATABASE_URL" -c "
  UPDATE channels 
  SET external_id = '$NEW_CHANNEL_ID', 
      resource_identifier = '$NEW_CHANNEL_ID', 
      updated_at = NOW() 
  WHERE external_id = '$OLD_CHANNEL_ID'
" 2>&1

# MATTERMOST_CHANNEL_IDS removed - channel discovery is auto-discovery via API

echo ""
echo "=== DONE ==="
echo "Test channel in omniagent team: $NEW_CHANNEL_ID"
echo "Access at Mattermost site URL"
