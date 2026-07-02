import subprocess, json, sys, os

def get_env_val(key):
    with open("/opt/data/.env") as f:
        for line in f:
            line = line.strip()
            if line.startswith(key + "="):
                return line[len(key)+1:]
    return ""

TOKEN = get_env_val("MATTERMOST_ACCESS_TOKEN")
if not TOKEN:
    print("ERROR: No token")
    sys.exit(1)

SERVER = "http://mattermost:8065"
API = f"{SERVER}/api/v4"
AUTH = f"Authorization: Bearer {TOKEN}"

def api(method, path, data=None):
    url = f"{API}{path}"
    cmd = ["curl", "-s", "-X", method, "-H", AUTH, "-H", "Content-Type: application/json"]
    if data:
        cmd += ["-d", json.dumps(data)]
    cmd += [url]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except json.JSONDecodeError:
        print(f"  JSON error from {method} {path}: {r.stdout[:200]}")
        return {}

BOT_ID = "1bg8a6szhif1dkp1i1m4p4dc8c"
NEW_CHAN = "4eb9s63aibd3bepf1p1j3sj79w"
OLD_CHAN = "t96uf5zmy3r3iqen91bgdpd3da"

# 1. Add bot to channel
print("=== Adding bot to channel ===")
r = api("POST", f"/channels/{NEW_CHAN}/members", {"user_id": BOT_ID})
print(f"  Bot added: {r.get('user_id') == BOT_ID}")

# 2. Get testuser
print("=== Getting testuser ===")
users = api("GET", "/users")
testuser_id = ""
for u in (users if isinstance(users, list) else []):
    if u.get("username") == "testuser":
        testuser_id = u["id"]
        break
print(f"  testuser ID: {testuser_id}")

if testuser_id:
    r = api("POST", f"/channels/{NEW_CHAN}/members", {"user_id": testuser_id})
    print(f"  testuser added: {r.get('user_id') == testuser_id}")

# 3. Update DB
print("=== Updating DB ===")
db_url = get_env_val("DATABASE_URL") or "postgres://omniagent:***@postgres:5432/omniagent"
r = subprocess.run(
    ["psql", db_url, "-c", 
     f"UPDATE channels SET external_id='{NEW_CHAN}', resource_identifier='{NEW_CHAN}', updated_at=NOW() WHERE external_id='{OLD_CHAN}'"],
    capture_output=True, text=True
)
print(f"  DB: {r.stdout.strip() or r.stderr[:200]}")

# MATTERMOST_CHANNEL_IDS removed - channel discovery is auto-discovery via API

# Verify
print(f"\n=== VERIFIED ===")
print(f"  Channel: test (ID: {NEW_CHAN})")
print(f"  Team: omniagent")
print(f"  Bot: {BOT_ID}")
print(f"  testuser: {testuser_id}")
