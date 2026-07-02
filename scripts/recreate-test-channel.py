#!/usr/bin/env python3
"""Recreate test channel in omniagent team and update DB."""

import subprocess, json, sys

def get_env_val(key):
    with open("/opt/data/.env") as f:
        for line in f:
            line = line.strip()
            if line.startswith(key + "="):
                return line[len(key)+1:]
    return ""

TOKEN=get_en...
SERVER = "http://mattermost:8065"
AUTH=*** Bearer {TOKEN}"

def api(method, path, data=None):
    url = f"{SERVER}/api/v4{path}"
    cmd = ["curl", "-s", "-X", method, "-H", AUTH, "-H", "Content-Type: application/json"]
    if data:
        cmd += ["-d", json.dumps(data)]
    cmd += [url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout) if result.stdout else {}
    except:
        return {}

team_id = "w9kmbowq6ty1td5ufy8sdbugda"  # omniagent team
old_channel_id = "t96uf5zmy3r3iqen91bgdpd3da"  # old test channel (test-team)

# 1. Check if "test" already exists in omniagent team
channels = api("GET", f"/teams/{team_id}/channels")
existing = None
for c in channels if isinstance(channels, list) else []:
    if c["name"] == "test":
        existing = c
        break

if existing:
    print(f"Channel 'test' already exists in omniagent team: {existing['id']}")
    new_channel_id = existing["id"]
else:
    # Create "test" channel in omniagent team
    chan = api("POST", "/channels", {
        "team_id": team_id,
        "name": "test",
        "display_name": "Test",
        "type": "O"
    })
    new_channel_id = chan.get("id", "")
    print(f"Created 'test' channel in omniagent team: {new_channel_id}")

if not new_channel_id:
    print("ERROR: Could not get/create channel")
    sys.exit(1)

# 2. Add bot to the new channel
bot_id = "1bg8a6szhif1dkp1i1m4p4dc8c"
result = api("POST", f"/channels/{new_channel_id}/members", {"user_id": bot_id})
if isinstance(result, dict) and result.get("user_id") == bot_id:
    print(f"Bot added to new channel")
else:
    print(f"Failed to add bot: {json.dumps(result)[:200]}")

# 3. Update DB - change the channel mapping from old channel to new
# The omniagent DB has channel 5 (test-mattermost) with external_id = old_channel_id
# We need to update it to point to new_channel_id

# Check PostgreSQL
pg_cmd = f'psql "$DATABASE_URL" -c "UPDATE channels SET external_id = \'{new_channel_id}\', updated_at = NOW() WHERE external_id = \'{old_channel_id}\'"'
print(f"\nUpdating DB channel mapping...")
result = subprocess.run(
    ["psql", "$DATABASE_URL"],
    capture_output=True, text=True,
    env={"DATABASE_URL": get_env_val("DATABASE_URL") | "postgres://omniagent:omniagent@postgres:5432/omniagent"}
)

# Actually let me just do it directly
db_url = "postgres://omniagent:omniagent@postgres:5432/omniagent"
pg = subprocess.run(
    ["psql", db_url, "-c", f"UPDATE channels SET external_id = '{new_channel_id}', resource_identifier = '{new_channel_id}', updated_at = NOW() WHERE external_id = '{old_channel_id}'"],
    capture_output=True, text=True
)
print(f"DB update: {pg.stdout} {pg.stderr[:200] if pg.stderr else ''}")

# MATTERMOST_CHANNEL_IDS removed - channel discovery is auto-discovery via API

print(f"\n=== NEW CHANNEL INFO ===")
print(f"Channel:  test (id: {new_channel_id})")
print(f"Team:     omniagent")
