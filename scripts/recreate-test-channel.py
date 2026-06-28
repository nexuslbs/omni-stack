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

# 4. Update the .env to include the new channel ID
with open("/opt/data/.env") as f:
    env_content = f.read()

old_ids_line = None
for line in env_content.split("\n"):
    if line.startswith("MATTERMOST_CHANNEL_IDS="):
        old_ids_line = line
        break

if old_ids_line:
    current_ids = old_ids_line.split("=", 1)[1]
    ids = [x.strip() for x in current_ids.split(",") if x.strip()]
    if new_channel_id not in ids:
        ids.append(new_channel_id)
    # Remove old channel ID if present
    ids = [x for x in ids if x != old_channel_id]
    new_ids = ",".join(ids)
    new_line = f"MATTERMOST_CHANNEL_IDS={new_ids}"
    env_content = env_content.replace(old_ids_line, new_line)
    with open("/opt/data/.env", "w") as f:
        f.write(env_content)
    print(f"Updated MATTERMOST_CHANNEL_IDS (added {new_channel_id}, removed {old_channel_id})")
else:
    # Append new line
    env_content += f"\nMATTERMOST_CHANNEL_IDS={new_channel_id}\n"
    with open("/opt/data/.env", "a") as f:
        f.write(f"\nMATTERMOST_CHANNEL_IDS={new_channel_id}\n")
    print(f"Added MATTERMOST_CHANNEL_IDS={new_channel_id}")

print(f"\n=== NEW CHANNEL INFO ===")
print(f"Channel:  test (id: {new_channel_id})")
print(f"Team:     omniagent")
