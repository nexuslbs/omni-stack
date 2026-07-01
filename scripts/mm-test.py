"""Post test messages to Mattermost setup channel and verify bot response."""
import json
import os
import subprocess
import sys
import time

# ── Helpers ──

def get_env(key):
    val = os.environ.get(key)
    if val:
        return val
    path = "/opt/omni-stack/.env"
    if not os.path.exists(path):
        return None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith(key + "="):
                raw = line[len(key) + 1:]
                if (raw.startswith('"') and raw.endswith('"')) or \
                   (raw.startswith("'") and raw.endswith("'")):
                    raw = raw[1:-1]
                return raw
    return None

def login():
    """Login as admin and return Bearer token string."""
    subprocess.run(["curl", "-s", "-D", "/tmp/h.txt", "-X", "POST",
         "http://omm-mattermost:8065/api/v4/users/login",
         "-H", "Content-Type: application/json",
         "-d", '{"login_id":"lucasbasquerotto","password":"AdminPass123!"}'],
        capture_output=True, text=True, timeout=15)
    with open("/tmp/h.txt") as f:
        for line in f:
            if "token:" in line.lower():
                return "Bearer " + line.split(":", 1)[1].strip()
    return None

def curl_post(auth, data):
    """Send POST to Mattermost API and return (status_code, body_json)."""
    r = subprocess.run(["curl", "-s", "-w", "\n%{http_code}", "-X", "POST",
         "http://omm-mattermost:8065/api/v4/posts",
         "-H", "Content-Type: application/json",
         "-H", "Authorization: " + auth,
         "-d", json.dumps(data)],
        capture_output=True, text=True, timeout=15)
    parts = r.stdout.strip().rsplit("\n", 1)
    body = parts[0] if len(parts) > 1 else ""
    sc = int(parts[-1]) if parts[-1].isdigit() else 0
    parsed = json.loads(body) if body else {}
    return sc, parsed


def main():
    auth = login()
    if not auth:
        print("FAIL: Could not login")
        sys.exit(1)
    print("Logged in as lucasbasquerotto")

    # Channel IDs
    setup_id = "1ip9txt6f7n1uyio7dbkdijw9r"

    # Step 1: Post "$new mm-setup"
    print("\n1. Posting '$new mm-setup' to setup channel...")
    sc, data = curl_post(auth, {"channel_id": setup_id, "message": "$new mm-setup"})
    if sc == 201:
        post_id = data.get("id", "?")
        print(f"   Posted! id={post_id}")
    else:
        print(f"   HTTP {sc}: {data.get('message', '?')}")
        if data.get("id") == "api.post.post_forbidden_for_plugin":
            print("   Bot posts as plugin, not user. Trying bot token...")
            # Try with bot token
            bot_token = get_env("MATTERMOST_ACCESS_TOKEN")
            if bot_token:
                bot_auth = "Bearer " + bot_token
                sc, data = curl_post(bot_auth, {"channel_id": setup_id, "message": "$new mm-setup"})
                if sc == 201:
                    print(f"   Bot posted! id={data.get('id', '?')}")
                else:
                    print(f"   Bot HTTP {sc}: {data.get('message', '?')}")

    # Step 2: Wait for bot to create channel
    print("\n2. Waiting 10s for bot processing...")
    time.sleep(10)

    # Step 3: Post "Hi"
    print("\n3. Posting 'Hi' to setup channel...")
    sc, data = curl_post(auth, {"channel_id": setup_id, "message": "Hi"})
    if sc == 201:
        print(f"   Posted! id={data.get('id', '?')}")
    else:
        print(f"   HTTP {sc}: {data.get('message', '?')}")

    # Step 4: Check if mm-setup channel was created in omniagent DB
    print("\n4. Checking omniagent DB for mm-setup channel...")
    pg_cmd = ["psql", "-U", "omniagent", "-h", "postgres", "-c"]
    r = subprocess.run(pg_cmd + ["SELECT id, name, platform, external_id FROM channels WHERE platform='mattermost' ORDER BY id;"],
                       capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        print(r.stdout)
    else:
        print(f"   psql error: {r.stderr[:200]}")

    print("\nDone!")


if __name__ == "__main__":
    main()
