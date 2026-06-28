#!/usr/bin/env python3
"""Setup script for Mattermost test - run inside omniagent container.
Reads token from .env file, never hardcodes. Run with: python3 /opt/data/scripts/mm-setup.py
"""
import subprocess, json, sys, os

# Read token from .env
def get_env_val(key):
    env_path = "/opt/data/.env"
    if not os.path.exists(env_path):
        # Try alternate locations
        for p in ["/opt/workspace/omni-stack/.env", "/app/.env"]:
            if os.path.exists(p):
                env_path = p
                break
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith(key + "="):
                return line[len(key)+1:]
    return ""

TOKEN = get_env_val("MATTERMOST_ACCESS_TOKEN")
if not TOKEN:
    print("ERROR: MATTERMOST_ACCESS_TOKEN not found")
    sys.exit(1)

SERVER = get_env_val("MATTERMOST_SERVER_URL")
if not SERVER:
    SERVER = "http://mattermost:8065"

AUTH = f"Authorization: Bearer {TOKEN}"

def api(method, path, data=None):
    url = f"{SERVER}/api/v4{path}"
    cmd = ["curl", "-s", "-X", method, "-H", AUTH, "-H", "Content-Type: application/json"]
    if data:
        cmd += ["-d", json.dumps(data)]
    cmd += [url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout) if result.stdout else {}
    except json.JSONDecodeError:
        print(f"  JSON decode error for {method} {path}: {result.stdout[:200]}")
        return {}

def check(condition, msg):
    if condition:
        print(f"  OK: {msg}")
    else:
        print(f"  FAIL: {msg}")
    return condition

print("=== Mattermost Setup ===")

# 1. Check system status
print("\n1. Checking Mattermost status...")
ping = api("GET", "/system/ping")
check(ping.get("status") == "OK", "System is running")

# 2. Check bot user
print("\n2. Checking bot user...")
me = api("GET", "/users/me")
bot_username = me.get('username', 'unknown')
if not check(bot_username == "omniagent", f"Bot user is omniagent (got: {bot_username})"):
    print(f"   Full response: {json.dumps(me, indent=2)[:500]}")
bot_id = me.get("id", "")
print(f"   Bot ID: {bot_id}")
print(f"   Bot roles: {me.get('roles', '')}")

# 3. List teams
print("\n3. Listing teams...")
teams = api("GET", "/teams")
if teams and isinstance(teams, list):
    for t in teams:
        print(f"   Team: {t['name']} (id: {t['id']})")
elif isinstance(teams, dict):
    print(f"   Error: {json.dumps(teams)[:300]}")
else:
    print("   No teams found or empty response")

# 4. Find or create test team
print("\n4. Finding/Creating test team...")
team = None
if isinstance(teams, list):
    for t in teams:
        if t["name"] == "test-team":
            team = t
            break

if not team:
    team = api("POST", "/teams", {
        "name": "test-team",
        "display_name": "Test Team",
        "type": "O"
    })
    if isinstance(team, dict) and team.get("id"):
        check(True, f"Created team test-team (id: {team.get('id')})")
    else:
        check(False, f"Failed to create team: {json.dumps(team)[:200]}")
else:
    print(f"   Team test-team exists (id: {team['id']})")

team_id = team.get("id") if isinstance(team, dict) else None

# 5. Create test channel
print("\n5. Creating test channel...")
channel = None
if team_id:
    channels_resp = api("GET", f"/teams/{team_id}/channels")
    channels = channels_resp if isinstance(channels_resp, list) else []
    for c in channels:
        if c["name"] == "test":
            channel = c
            break
    
    if not channel:
        channel = api("POST", "/channels", {
            "team_id": team_id,
            "name": "test",
            "display_name": "Test",
            "type": "O"
        })
        if isinstance(channel, dict) and channel.get("id"):
            check(True, f"Created channel test (id: {channel.get('id')})")
        else:
            check(False, f"Failed to create channel: {json.dumps(channel)[:200]}")
    else:
        print(f"   Channel test exists (id: {channel['id']})")
else:
    print("   Skipping - no team_id")

channel_id = channel.get("id", "") if isinstance(channel, dict) else ""

# 6. Add bot to channel
print("\n6. Adding bot to test channel...")
if channel_id:
    result = api("POST", f"/channels/{channel_id}/members", {"user_id": bot_id})
    success = isinstance(result, dict) and result.get("user_id") == bot_id
    check(success, f"Bot added to channel")
    if not success:
        print(f"   Response: {json.dumps(result)[:200]}")

# Summary
print("\n" + "="*50)
print("SETUP SUMMARY")
if team_id:
    print(f"  Team:     test-team (id: {team_id})")
if channel_id:
    print(f"  Channel:  test (id: {channel_id})")
print(f"  Bot:      {bot_username} (id: {bot_id})")
print(f"  Server:   {SERVER}")
print("="*50)
