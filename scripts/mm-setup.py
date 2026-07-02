#!/usr/bin/env python3
"""One-time Mattermost setup script for OmniAgent.

Creates 3 user accounts (main, test, bot), enables bot account creation,
generates a personal access token for the bot, creates a team and channel,
adds users to team and channel, writes results to .env.

Designed to run inside the omni-stack toolbox container.

Usage:  python3 /opt/omni-stack/scripts/mm-setup.py
"""
import json
import os
import subprocess
import sys
import time

ENV_PATH = "/opt/omni-stack/.env"

TOKEN_CACHE = None

def get_env_file(key):
    """Read from .env FILE only (ignore os.environ to avoid stale container env vars)."""
    if not os.path.exists(ENV_PATH):
        return None
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line.startswith(key + "="):
                raw = line[len(key) + 1:]
                if (raw.startswith('"') and raw.endswith('"')) or \
                   (raw.startswith("'") and raw.endswith("'")):
                    raw = raw[1:-1]
                return raw
    return None

def get_val(preferred, fallback_key, default=None):
    v = get_env_file(preferred)
    if v:
        return v
    v = get_env_file(fallback_key)
    if v:
        return v
    return default

def set_env_val(key, value):
    if not os.path.exists(ENV_PATH):
        with open(ENV_PATH, "w") as f:
            f.write(f"{key}={value}\n")
        return
    with open(ENV_PATH) as f:
        lines = f.readlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(key + "=") or line.strip().startswith("# " + key):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        if lines and lines[-1].endswith("\n"):
            lines.append(f"{key}={value}\n")
        else:
            lines.append(f"\n{key}={value}\n")
    with open(ENV_PATH, "w") as f:
        f.writelines(lines)

def check(condition, msg):
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {msg}")
    return condition

# ── API client ──

class MMClient:
    def __init__(self, server_url, token=None):
        self.server_url = server_url.rstrip("/")
        self.token = token

    def _curl(self, method, path, data=None, params=None):
        url = f"{self.server_url}/api/v4{path}"
        hdr_file = "/tmp/mm_hdrs.txt"
        cmd = ["curl", "-s", "-D", hdr_file, "-w", "\n%{http_code}", "-X", method,
               "-H", "Content-Type: application/json"]
        if self.token:
            auth_val = "Bearer " + self.token
            cmd += ["-H", "Authorization: " + auth_val]
        if data is not None:
            cmd += ["-d", json.dumps(data)]
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        cmd += [url]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            parts = result.stdout.strip().rsplit("\n", 1)
            body = parts[0] if len(parts) > 1 else ""
            sc = int(parts[-1]) if parts[-1].isdigit() else 0
            parsed = json.loads(body) if body else {}
            return parsed, sc
        except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as e:
            return {"error": str(e)}, 0

    def get(self, path, params=None):
        return self._curl("GET", path, params=params)

    def post(self, path, data=None):
        return self._curl("POST", path, data)

    def put(self, path, data=None):
        return self._curl("PUT", path, data)

    def login(self, username, password):
        data, code = self._curl("POST", "/users/login",
                                {"login_id": username, "password": password})
        if code == 200:
            try:
                with open("/tmp/mm_hdrs.txt") as f:
                    for line in f:
                        if line.lower().startswith("token:"):
                            data["_token"] = line.split(":", 1)[1].strip()
                            break
            except FileNotFoundError:
                pass
            return data
        return None

    def ping(self):
        data, code = self.get("/system/ping", {"get_server_status": "true"})
        return data.get("status") == "OK" if isinstance(data, dict) else False

    def get_users(self):
        data, code = self.get("/users")
        return data if code == 200 and isinstance(data, list) else []

    def create_user(self, username, password, email, first_name="", last_name=""):
        data, code = self.post("/users", {
            "username": username, "password": password, "email": email,
            "first_name": first_name, "last_name": last_name,
        })
        if code == 201:
            return data
        if code == 409:
            return {"_exists": True}
        return data

    def find_user(self, username):
        for u in self.get_users():
            if u.get("username") == username:
                return u
        return None

    def get_me(self):
        data, code = self.get("/users/me")
        return data if code == 200 else None

    def get_teams(self):
        data, code = self.get("/teams")
        return data if code == 200 and isinstance(data, list) else []

    def create_team(self, name, display_name, team_type="O"):
        data, code = self.post("/teams", {
            "name": name, "display_name": display_name, "type": team_type,
        })
        if code == 201:
            return data
        if code == 409:
            return {"_exists": True}
        return data

    def add_team_member(self, team_id, user_id):
        data, code = self.post(f"/teams/{team_id}/members",
                               {"team_id": team_id, "user_id": user_id})
        if code == 201:
            return True
        # 409 means already a member -- that's fine
        return code == 409

    def get_channels(self, team_id):
        data, code = self.get(f"/teams/{team_id}/channels")
        return data if code == 200 and isinstance(data, list) else []

    def create_channel(self, team_id, name, display_name, channel_type="O"):
        data, code = self.post("/channels", {
            "team_id": team_id, "name": name,
            "display_name": display_name, "type": channel_type,
        })
        if code == 201:
            return data
        if code == 409:
            return {"_exists": True}
        return data

    def add_channel_member(self, channel_id, user_id):
        data, code = self.post(f"/channels/{channel_id}/members", {"user_id": user_id})
        if code == 201:
            return True
        return code == 409

    def create_bot_and_token(self, user_id):
        """Try to create a bot account. If that fails, try to get existing tokens.
        Returns a token string or None."""
        data, code = self.post("/bots", {
            "user_id": user_id,
            "display_name": "OmniAgent Bot",
            "description": "Bot account for OmniAgent agent messages",
        })
        if code == 201:
            print("   Bot account created via /bots endpoint")
        elif code == 409:
            print("   Bot account already exists")
        else:
            print(f"   /bots returned {code}, checking existing tokens...")

        # Get or create a user token
        tok_data, tok_code = self.get(f"/users/{user_id}/tokens")
        if tok_code == 200 and isinstance(tok_data, list) and tok_data:
            # Use the first active token
            for tok in tok_data:
                if tok.get("is_active") and tok.get("token"):
                    return tok["token"]
            # None were active, fall through to create
            print("   Found inactive tokens, creating new one...")
        else:
            print(f"   No existing tokens found, creating new one...")

        # Create a fresh token
        data2, code2 = self.post(f"/users/{user_id}/tokens",
                                 {"description": "OmniAgent bot access token"})
        if data2.get("token"):
            return data2["token"]
        print(f"   Token creation failed: {data2.get('message', json.dumps(data2)[:100])}")
        return None


def main():
    server_url = get_env_file("MATTERMOST_SERVER_URL") or "http://omm-mattermost:8065"
    site_url = get_env_file("MATTERMOST_SITE_URL") or ""

    main_user = get_val("MM_USERNAME", "MATTERMOST_ADMIN_USER", "lucasbasquerotto")
    main_pass = get_val("MM_USER_PASSWORD", "MATTERMOST_ADMIN_PASSWORD")
    test_user = get_val("MM_TEST_USERNAME", "MATTERMOST_TEST_USER", "testuser")
    test_pass = get_val("MM_TEST_PASSWORD", "MATTERMOST_TEST_PASSWORD")
    bot_user = get_val("MM_BOT_USERNAME", "MATTERMOST_BOT_USER", "omniagent")
    bot_pass = get_val("MM_BOT_PASSWORD", "MATTERMOST_BOT_PASSWORD")
    team_name = get_val("MM_TEAM", "MATTERMOST_TEAM_NAME", "")
    channel_name = get_val("MM_CHANNEL", "MATTERMOST_CHANNEL_NAME", "setup")

    mm_team_set = bool(get_env_file("MM_TEAM") or get_env_file("MATTERMOST_TEAM_NAME"))
    create_team_chan = mm_team_set and bool(team_name)

    if not main_pass and not test_pass and not bot_pass:
        print("ERROR: No passwords found.")
        sys.exit(1)

    if main_user and not main_pass:
        print("ERROR: Main user is set but MM_USER_PASSWORD is empty. Set MM_USER_PASSWORD in .env.")
        sys.exit(1)

    print(f"Mattermost Server: {server_url}")
    print(f"Site URL:          {site_url}")
    print(f"Main User:         {main_user} {'(password set)' if main_pass else '(SKIP)'}")
    print(f"Test User:         {test_user} {'(password set)' if test_pass else '(SKIP)'}")
    print(f"Bot User:          {bot_user} {'(password set)' if bot_pass else '(SKIP)'}")
    if team_name:
        print(f"Team:              {team_name}")
        print(f"Channel:           {channel_name}")
    else:
        print("Team:              (not configured)")

    # Step 1: Wait for Mattermost
    print("\n1. Waiting for Mattermost...")
    mm = MMClient(server_url)
    for attempt in range(30):
        if mm.ping():
            check(True, "Mattermost is running")
            break
        time.sleep(2)
    else:
        check(False, "Mattermost not ready after 60s")
        sys.exit(1)

    # Step 2: Authenticate
    print("\n2. Authenticating...")
    session = mm.login(main_user, main_pass)
    if not session:
        print("   Login failed with configured password.")
        # Check if user already exists
        existing = mm.find_user(main_user)
        if existing:
            print(f"   User '{main_user}' exists but password doesn't match configured value.")
            print(f"   To reset, run:")
            print(f"   docker exec omm-mattermost /tmp/mmctl --local user change-password {main_user} --password '<new-password>'")
            print(f"   Then update MM_USER_PASSWORD in .env to match.")
            sys.exit(1)
        else:
            print("   Creating first admin user...")
            r = mm.create_user(main_user, main_pass,
                               f"{main_user}@local.host",
                               first_name="User", last_name="")
            if r.get("_exists"):
                check(True, f"User '{main_user}' exists")
            elif r.get("id"):
                check(True, f"User '{main_user}' created")
            else:
                check(False, f"Create user failed: {json.dumps(r)[:200]}")
                sys.exit(1)
            session = mm.login(main_user, main_pass)
            if not session:
                check(False, "Login failed after creation")
                sys.exit(1)

    raw_token = session.get("_token") or session.get("token") or session.get("id")
    mm.token = raw_token
    me = mm.get_me()
    admin_id = me.get("id", "") if me else ""
    check(bool(admin_id), f"Authenticated as '{main_user}' (id: {admin_id})")
    if not admin_id:
        sys.exit(1)

    # Step 3: Enable features
    print("\n3. Enabling features...")
    cfg, _ = mm.get("/config")
    if isinstance(cfg, dict) and "ServiceSettings" in cfg:
        cfg["ServiceSettings"]["EnableBotAccountCreation"] = True
        cfg["ServiceSettings"]["EnableUserAccessTokens"] = True
        if site_url:
            cfg["ServiceSettings"]["SiteURL"] = site_url
        result, _ = mm.put("/config", cfg)
        check(isinstance(result, dict), "Bot creation + user tokens enabled")
    else:
        check(False, "Could not read config")

    # Step 4: Create/get test user
    test_id = None
    if test_pass:
        print(f"\n4. Ensuring test user '{test_user}'...")
        u = mm.find_user(test_user)
        if u:
            test_id = u.get("id")
            check(True, f"Exists (id: {test_id})")
        else:
            r = mm.create_user(test_user, test_pass, f"{test_user}@localhost.local",
                               first_name="Test", last_name="User")
            if r.get("id") and not r.get("_exists"):
                test_id = r.get("id")
                check(True, f"Created (id: {test_id})")
            elif r.get("_exists"):
                u = mm.find_user(test_user)
                test_id = u.get("id") if u else ""
                check(bool(test_id), f"Exists (id: {test_id})")
            else:
                check(False, f"Failed: {json.dumps(r)[:200]}")

    # Step 5: Create/get bot user + token
    bot_user_id = None
    if bot_pass:
        print(f"\n5. Setting up bot user '{bot_user}'...")
        u = mm.find_user(bot_user)
        if u:
            bot_user_id = u.get("id")
            check(True, f"User exists (id: {bot_user_id})")
        else:
            r = mm.create_user(bot_user, bot_pass, f"{bot_user}@localhost.local",
                               first_name="OmniAgent", last_name="Bot")
            if r.get("id") and not r.get("_exists"):
                bot_user_id = r.get("id")
                check(True, f"Created (id: {bot_user_id})")
            elif r.get("_exists"):
                u = mm.find_user(bot_user)
                bot_user_id = u.get("id") if u else ""
                check(bool(bot_user_id), f"Exists (id: {bot_user_id})")
            else:
                check(False, f"Failed: {json.dumps(r)[:200]}")
                sys.exit(1)

        if bot_user_id:
            # Try to create bot account + get a working token
            token = mm.create_bot_and_token(bot_user_id)
            if token:
                set_env_val("MATTERMOST_ACCESS_TOKEN", token)
                check(True, "Bot access token ready")
                # Trigger hot-reload of the Mattermost platform plugin in omniagent
                # so it picks up the new token without a container restart.
                # POST /api/plugins/mattermost/config triggers update_config_handler
                # which refreshes process env from .env before respawning the plugin.
                print("\n   Triggering Mattermost plugin reload in omniagent...")
                omniagent_url = "http://omniagent:8080"
                try:
                    import urllib.request
                    body = json.dumps({"config": {"bot_username": bot_user}}).encode()
                    req = urllib.request.Request(
                        f"{omniagent_url}/api/plugins/mattermost/config",
                        data=body,
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        check(resp.status == 200, "Mattermost plugin reload triggered")
                except Exception as e:
                    check(False, f"Mattermost plugin reload failed: {e}")
            else:
                check(False, "Could not obtain bot token")

    # Step 6: Create team + channel
    team_id = None
    channel_id = None
    if create_team_chan:
        print(f"\n6. Ensuring team '{team_name}' and channel '{channel_name}'...")
        bot_client = mm

        teams = bot_client.get_teams()
        team = None
        for t in teams:
            if t.get("name") == team_name:
                team = t
                break
        if not team:
            team = bot_client.create_team(team_name, team_name.title())
            if isinstance(team, dict) and (team.get("id") or team.get("_exists")):
                check(True, f"Team '{team_name}' created")
            else:
                check(False, f"Team creation failed: {json.dumps(team)[:200]}")
        else:
            check(True, f"Team '{team_name}' exists")
        team_id = team.get("id") if isinstance(team, dict) else ""

        if team_id:
            print("   Adding users to team...")
            for uid, label in [(admin_id, main_user), (test_id, test_user), (bot_user_id, bot_user)]:
                if uid:
                    ok = bot_client.add_team_member(team_id, uid)
                    check(ok, f"Added '{label}'")

            channels = bot_client.get_channels(team_id)
            channel = None
            for c in channels:
                if c.get("name") == channel_name:
                    channel = c
                    break
            if not channel:
                channel = bot_client.create_channel(team_id, channel_name, channel_name.title())
                if isinstance(channel, dict) and (channel.get("id") or channel.get("_exists")):
                    check(True, f"Channel '#{channel_name}' created")
                else:
                    check(False, f"Channel creation failed: {json.dumps(channel)[:200]}")
            else:
                check(True, f"Channel '#{channel_name}' exists")
            channel_id = channel.get("id") if isinstance(channel, dict) else ""

            if channel_id:
                print("   Adding users to channel...")
                for uid, label in [(admin_id, main_user), (test_id, test_user), (bot_user_id, bot_user)]:
                    if uid:
                        ok = bot_client.add_channel_member(channel_id, uid)
                        check(ok, f"Added '{label}'")

                # Channel IDs are now auto-discovered via the Mattermost API
    else:
        print("\n6. Skipping team/channel (set MM_TEAM to enable)")

    # Summary
    print("\n" + "=" * 60)
    print("SETUP COMPLETE")
    print("=" * 60)
    print(f"  Server:    {server_url}")
    if site_url:
        print(f"  Site URL:  {site_url}")
    print(f"  Main:      {main_user} (id: {admin_id})")
    print(f"  Test user: {test_user} (id: {test_id or 'N/A'})")
    print(f"  Bot user:  {bot_user} (id: {bot_user_id or 'N/A'})")
    if team_id:
        print(f"  Team:      {team_name} (id: {team_id})")
    if channel_id:
        print(f"  Channel:   {channel_name} (id: {channel_id})")
    print()
    print("Next steps:")
    print("  Start omniagent: docker compose up -d")
    print("=" * 60)


if __name__ == "__main__":
    main()
