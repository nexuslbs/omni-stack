     1|     1|#!/usr/bin/env python3
     2|     2|"""One-time Mattermost setup script for OmniAgent.
     3|     3|
     4|     4|Creates 3 user accounts (admin, test, bot), enables bot account creation,
     5|     5|generates a personal access token for the bot, and writes it to .env.
     6|     6|
     7|     7|Usage:  python3 scripts/mm-setup.py
     8|     8|
     9|     9|Reads credentials from the .env file in the repo root.
    10|    10|"""
    11|    11|import argparse
    12|    12|import json
    13|    13|import os
    14|    14|import re
    15|    15|import subprocess
    16|    16|import sys
    17|    17|import time
    18|    18|
    19|    19|ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    20|    20|
    21|    21|# ---------------------------------------------------------------------------
    22|    22|# Helpers
    23|    23|# ---------------------------------------------------------------------------
    24|    24|
    25|    25|def get_env_val(key, fallback=None):
    26|    26|    """Read a single key from .env (file or environment)."""
    27|    27|    val = os.environ.get(key)
    28|    28|    if val is not None:
    29|    29|        return val
    30|    30|    if not os.path.exists(ENV_PATH):
    31|    31|        return fallback
    32|    32|    with open(ENV_PATH) as f:
    33|    33|        for line in f:
    34|    34|            line = line.strip()
    35|    35|            if line.startswith(key + "="):
    36|    36|                raw = line[len(key) + 1:]
    37|    37|                # Strip surrounding quotes if present
    38|    38|                if (raw.startswith('"') and raw.endswith('"')) or \
    39|    39|                   (raw.startswith("'") and raw.endswith("'")):
    40|    40|                    raw = raw[1:-1]
    41|    41|                return raw
    42|    42|    return fallback
    43|    43|
    44|    44|
    45|    45|def set_env_val(key, value):
    46|    46|    """Set a key=value in .env, creating or replacing the line."""
    47|    47|    if not os.path.exists(ENV_PATH):
    48|    48|        with open(ENV_PATH, "w") as f:
    49|    49|            f.write(f"{key}={value}\n")
    50|    50|        return
    51|    51|    with open(ENV_PATH) as f:
    52|    52|        lines = f.readlines()
    53|    53|    found = False
    54|    54|    for i, line in enumerate(lines):
    55|    55|        if line.strip().startswith(key + "=") or line.strip().startswith("# " + key):
    56|    56|            lines[i] = f"{key}={value}\n"
    57|    57|            found = True
    58|    58|            break
    59|    59|    if not found:
    60|    60|        if lines and lines[-1].endswith("\n"):
    61|    61|            lines.append(f"{key}={value}\n")
    62|    62|        else:
    63|    63|            lines.append(f"\n{key}={value}\n")
    64|    64|    with open(ENV_PATH, "w") as f:
    65|    65|        f.writelines(lines)
    66|    66|
    67|    67|
    68|    68|def check(condition, msg):
    69|    69|    status = "OK" if condition else "FAIL"
    70|    70|    print(f"  [{status}] {msg}")
    71|    71|    return condition
    72|    72|
    73|    73|
    74|    74|# ---------------------------------------------------------------------------
    75|    75|# Mattermost API client (uses session token from admin login)
    76|    76|# ---------------------------------------------------------------------------
    77|    77|
    78|    78|class MMClient:
    79|    79|    def __init__(self, server_url, token=None):
    80|    80|        self.server_url = server_url.rstrip("/")
    81|    81|        self.token = token
    82|    82|
    83|    83|    def _run_curl(self, method, path, data=None, params=None):
    84|    84|        url = f"{self.server_url}/api/v4{path}"
    85|    85|        cmd = ["curl", "-s", "-w", "\n%{http_code}", "-X", method]
    86|    86|        cmd += ["-H", "Content-Type: application/json"]
    87|    87|        if self.token:
    88|    88|            cmd += ["-H", f"Authorization: Bearer ***
    89|    89|        if data is not None:
    90|    90|            cmd += ["-d", json.dumps(data)]
    91|    91|        if params:
    92|    92|            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    93|    93|        cmd += [url]
    94|    94|
    95|    95|        try:
    96|    96|            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    97|    97|            parts = result.stdout.strip().rsplit("\n", 1)
    98|    98|            body = parts[0] if len(parts) > 1 else ""
    99|    99|            status_code = int(parts[-1]) if parts[-1].isdigit() else 0
   100|   100|            parsed = json.loads(body) if body else {}
   101|   101|            return parsed, status_code
   102|   102|        except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as e:
   103|   103|            return {"error": str(e)}, 0
   104|   104|
   105|   105|    def get(self, path):
   106|   106|        return self._run_curl("GET", path)
   107|   107|
   108|   108|    def post(self, path, data=None):
   109|   109|        return self._run_curl("POST", path, data)
   110|   110|
   111|   111|    def put(self, path, data=None):
   112|   112|        return self._run_curl("PUT", path, data)
   113|   113|
   114|   114|    def login(self, username, password):
   115|   115|        """Login and return a session token."""
   116|   116|        data, code = self.post("/users/login", {"login_id": username, "password": password})
   117|   117|        if code == 200:
   118|   118|            return data
   119|   119|        return None
   120|   120|
   121|   121|    def ping(self):
   122|   122|        """Check if Mattermost is running."""
   123|   123|        data, code = self.get("/system/ping?get_server_status=true")
   124|   124|        return data.get("status") == "OK" if isinstance(data, dict) else False
   125|   125|
   126|   126|    def get_users(self):
   127|   127|        """List all users on the system."""
   128|   128|        data, code = self.get("/users")
   129|   129|        if code == 200 and isinstance(data, list):
   130|   130|            return data
   131|   131|        return []
   132|   132|
   133|   133|    def create_user(self, username, password, email, first_name="", last_name=""):
   134|   134|        """Create a user (requires admin session)."""
   135|   135|        data, code = self.post("/users", {
   136|   136|            "username": username,
   137|   137|            "password": password,
   138|   138|            "email": email,
   139|   139|            "first_name": first_name,
   140|   140|            "last_name": last_name,
   141|   141|        })
   142|   142|        if code == 201:
   143|   143|            return data
   144|   144|        if code == 409:
   145|   145|            return {"id": username, "already_exists": True}
   146|   146|        return data
   147|   147|
   148|   148|    def create_bot(self, user_id, display_name="", description=""):
   149|   149|        """Create a bot account for a user (requires admin session)."""
   150|   150|        data, code = self.post("/bots", {
   151|   151|            "user_id": user_id,
   152|   152|            "display_name": display_name or display_name,
   153|   153|            "description": description,
   154|   154|        })
   155|   155|        if code == 201:
   156|   156|            return data
   157|   157|        if code == 409:
   158|   158|            return {"already_exists": True}
   159|   159|        return data
   160|   160|
   161|   161|    def create_user_token(self, user_id, description="Bot token for OmniAgent"):
   162|   162|        """Create a personal access token for a user (requires admin session)."""
   163|   163|        data, code = self.post(f"/users/{user_id}/tokens", {
   164|   164|            "description": description,
   165|   165|        })
   166|   166|        if code == 201:
   167|   167|            return data
   168|   168|        return data
   169|   169|
   170|   170|    def find_user_by_username(self, username):
   171|   171|        """Find a user by username."""
   172|   172|        users = self.get_users()
   173|   173|        for u in users:
   174|   174|            if u.get("username") == username:
   175|   175|                return u
   176|   176|        return None
   177|   177|
   178|   178|    def get_me(self):
   179|   179|        """Get authenticated user info."""
   180|   180|        data, code = self.get("/users/me")
   181|   181|        return data if code == 200 else None
   182|   182|
   183|   183|    def get_teams(self):
   184|   184|        """List all teams."""
   185|   185|        data, code = self.get("/teams")
   186|   186|        return data if code == 200 and isinstance(data, list) else []
   187|   187|
   188|   188|    def create_team(self, name, display_name, team_type="O"):
   189|   189|        """Create a team."""
   190|   190|        data, code = self.post("/teams", {
   191|   191|            "name": name,
   192|   192|            "display_name": display_name,
   193|   193|            "type": team_type,
   194|   194|        })
   195|   195|        if code == 201:
   196|   196|            return data
   197|   197|        if code == 409:
   198|   198|            return {"id": name, "already_exists": True}
   199|   199|        return data
   200|   200|
   201|   201|    def get_channels(self, team_id):
   202|   202|        """Get channels for a team."""
   203|   203|        data, code = self.get(f"/teams/{team_id}/channels")
   204|   204|        return data if code == 200 and isinstance(data, list) else []
   205|   205|
   206|   206|    def create_channel(self, team_id, name, display_name, channel_type="O"):
   207|   207|        """Create a channel."""
   208|   208|        data, code = self.post("/channels", {
   209|   209|            "team_id": team_id,
   210|   210|            "name": name,
   211|   211|            "display_name": display_name,
   212|   212|            "type": channel_type,
   213|   213|        })
   214|   214|        if code == 201:
   215|   215|            return data
   216|   216|        if code == 409:
   217|   217|            return {"id": name, "already_exists": True}
   218|   218|        return data
   219|   219|
   220|   220|    def add_channel_member(self, channel_id, user_id):
   221|   221|        """Add a user to a channel."""
   222|   222|        data, code = self.post(f"/channels/{channel_id}/members", {"user_id": user_id})
   223|   223|        return data if code == 201 else data
   224|   224|
   225|   225|
   226|   226|# ---------------------------------------------------------------------------
   227|   227|# Main
   228|   228|# ---------------------------------------------------------------------------
   229|   229|
   230|   230|def main():
   231|   231|    parser = argparse.ArgumentParser(description="Setup Mattermost for OmniAgent")
   232|   232|    parser.add_argument("--env-file", default=ENV_PATH, help="Path to .env file")
   233|   233|    parser.add_argument("--server-url", help="Mattermost server URL (overrides .env)")
   234|   234|    parser.add_argument("--site-url", help="Set MATTERMOST_SITE_URL in Mattermost config")
   235|   235|    args = parser.parse_args()
   236|   236|
   237|   237|    global ENV_PATH
   238|   238|    if args.env_file:
   239|   239|        ENV_PATH = args.env_file
   240|   240|
   241|   241|    # Read config from .env
   242|   242|    server_url = args.server_url or get_env_val("MATTERMOST_SERVER_URL", "http://mattermost:8065")
   243|   243|    site_url = args.site_url or get_env_val("MATTERMOST_SITE_URL", "")
   244|   244|    admin_user = get_env_val("MATTERMOST_ADMIN_USER", "admin")
   245|   245|    admin_pass = get_env_val("MATTERMOST_ADMIN_PASSWORD")
   246|   246|    test_user = get_env_val("MATTERMOST_TEST_USER", "testuser")
   247|   247|    test_pass = get_env_val("MATTERMOST_TEST_PASSWORD")
   248|   248|    bot_user = get_env_val("MATTERMOST_BOT_USER", "omniagent")
   249|   249|    bot_pass = get_env_val("MATTERMOST_BOT_PASSWORD")
   250|   250|
   251|   251|    if not all([admin_pass, test_pass, bot_pass]):
   252|   252|        print("ERROR: Missing Mattermost passwords in .env. Required:")
   253|   253|        print("  MATTERMOST_ADMIN_PASSWORD")
   254|   254|        print("  MATTERMOST_TEST_PASSWORD")
   255|   255|        print("  MATTERMOST_BOT_PASSWORD")
   256|   256|        sys.exit(1)
   257|   257|
   258|   258|    print(f"Mattermost Server: {server_url}")
   259|   259|    print(f"Site URL:          {site_url}")
   260|   260|    print(f"Admin User:        {admin_user}")
   261|   261|    print(f"Test User:         {test_user}")
   262|   262|    print(f"Bot User:          {bot_user}")
   263|   263|    print()
   264|   264|
   265|   265|    # ── Step 1: Wait for Mattermost to be ready ────────────────────────
   266|   266|    print("1. Waiting for Mattermost to be ready...")
   267|   267|    mm = MMClient(server_url)
   268|   268|    for attempt in range(30):
   269|   269|        if mm.ping():
   270|   270|            check(True, "Mattermost is running")
   271|   271|            break
   272|   272|        time.sleep(2)
   273|   273|    else:
   274|   274|        check(False, "Mattermost did not become ready in 60s")
   275|   275|        sys.exit(1)
   276|   276|
   277|   277|    # ── Step 2: Login as admin ─────────────────────────────────────────
   278|   278|    print("\n2. Authenticating as admin...")
   279|   279|
   280|   280|    admin_session = mm.login(admin_user, admin_pass)
   281|   281|
   282|   282|    if not admin_session:
   283|   283|        print("   Admin login failed. Attempting first-time setup...")
   284|   284|        users = mm.get_users()
   285|   285|        if not users or (isinstance(users, dict) and users.get("error")):
   286|   286|            # System is fresh — create the first admin user
   287|   287|            print("   No users found. Creating first admin user...")
   288|   288|            email_admin = get_env_val("MATTERMOST_ADMIN_EMAIL", f"{admin_user}@localhost.local")
   289|   289|            result = mm.create_user(admin_user, admin_pass, email_admin,
   290|   290|                                    first_name="Admin", last_name="User")
   291|   291|            if result.get("id") or result.get("already_exists"):
   292|   292|                check(True, f"Admin user '{admin_user}' created/exists")
   293|   293|            else:
   294|   294|                check(False, f"Failed to create admin user: {json.dumps(result)[:200]}")
   295|   295|                sys.exit(1)
   296|   296|
   297|   297|            admin_session = mm.login(admin_user, admin_pass)
   298|   298|            if not admin_session:
   299|   299|                check(False, "Could not login after creating admin user")
   300|   300|                sys.exit(1)
   301|   301|        else:
   302|   302|            check(False, f"Users exist but login for '{admin_user}' failed. Check credentials.")
   303|   303|            sys.exit(1)
   304|   304|
   305|   305|    mm.token = admin_session.get("token") or admin_session.get("id")
   306|   306|    if not mm.token:
   307|   307|        check(False, "Could not extract session token from login response")
   308|   308|        sys.exit(1)
   309|   309|
   310|   310|    admin_me = mm.get_me()
   311|   311|    admin_id = admin_me.get("id", "") if admin_me else ""
   312|   312|    check(bool(admin_id), f"Authenticated as '{admin_user}' (id: {admin_id})")
   313|   313|
   314|   314|    # Enable bot account creation and user access tokens
   315|   315|    print("\n3. Enabling Mattermost features...")
   316|   316|    data, _ = mm.get("/config")
   317|   317|    if isinstance(data, dict):
   318|   318|        if "ServiceSettings" in data:
   319|   319|            data["ServiceSettings"]["EnableBotAccountCreation"] = True
   320|   320|            data["ServiceSettings"]["EnableUserAccessTokens"] = True
   321|   321|            if site_url:
   322|   322|                data["ServiceSettings"]["SiteURL"] = site_url
   323|   323|            result, _ = mm.put("/config", data)
   324|   324|            check(isinstance(result, dict),
   325|   325|                  "Enabled bot account creation + user access tokens")
   326|   326|        else:
   327|   327|            check(False, "Could not read config")
   328|   328|
   329|   329|    # ── Step 3: Ensure test user exists ──────────────────────────────
   330|   330|    print(f"\n4. Ensuring test user '{test_user}'...")
   331|   331|
   332|   332|    existing_test = mm.find_user_by_username(test_user)
   333|   333|    if existing_test:
   334|   334|        check(True, f"Test user '{test_user}' already exists (id: {existing_test.get('id')})")
   335|   335|        test_id = existing_test.get("id")
   336|   336|    else:
   337|   337|        email_test = get_env_val("MATTERMOST_TEST_EMAIL", f"{test_user}@localhost.local")
   338|   338|        result = mm.create_user(test_user, test_pass, email_test,
   339|   339|                                first_name="Test", last_name="User")
   340|   340|        if result.get("id"):
   341|   341|            test_id = result.get("id")
   342|   342|            check(True, f"Created test user '{test_user}' (id: {test_id})")
   343|   343|        elif result.get("already_exists"):
   344|   344|            u = mm.find_user_by_username(test_user)
   345|   345|            test_id = u.get("id") if u else ""
   346|   346|            check(bool(test_id), f"Test user '{test_user}' already exists (id: {test_id})")
   347|   347|        else:
   348|   348|            check(False, f"Failed to create test user: {json.dumps(result)[:200]}")
   349|   349|            sys.exit(1)
   350|   350|
   351|   351|    # ── Step 4: Create bot user and access token ──────────────────────
   352|   352|    print(f"\n5. Setting up bot user '{bot_user}'...")
   353|   353|
   354|   354|    existing_bot = mm.find_user_by_username(bot_user)
   355|   355|    if existing_bot:
   356|   356|        bot_user_id = existing_bot.get("id")
   357|   357|        check(True, f"Bot user '{bot_user}' exists (id: {bot_user_id})")
   358|   358|    else:
   359|   359|        email_bot = get_env_val("MATTERMOST_BOT_EMAIL", f"{bot_user}@localhost.local")
   360|   360|        result = mm.create_user(bot_user, bot_pass, email_bot,
   361|   361|                                first_name="OmniAgent", last_name="Bot")
   362|   362|        if result.get("id"):
   363|   363|            bot_user_id = result.get("id")
   364|   364|            check(True, f"Created bot user '{bot_user}' (id: {bot_user_id})")
   365|   365|        elif result.get("already_exists"):
   366|   366|            u = mm.find_user_by_username(bot_user)
   367|   367|            bot_user_id = u.get("id") if u else ""
   368|   368|            check(bool(bot_user_id), f"Bot user '{bot_user}' exists (id: {bot_user_id})")
   369|   369|        else:
   370|   370|            check(False, f"Failed to create bot user: {json.dumps(result)[:200]}")
   371|   371|            sys.exit(1)
   372|   372|
   373|   373|    # Register the user as a bot account
   374|   374|    bot_data = mm.create_bot(bot_user_id, display_name="OmniAgent Bot",
   375|   375|                             description="Bot account for OmniAgent agent messages")
   376|   376|    check(
   377|   377|        isinstance(bot_data, dict) and (bot_data.get("user_id") or bot_data.get("already_exists")),
   378|   378|        f"Bot account registered (or already exists)"
   379|   379|    )
   380|   380|
   381|   381|    # Create a personal access token for the bot
   382|   382|    print("\n   Generating personal access token for bot...")
   383|   383|    existing_token = get_env_val("MATTERMOST_ACCESS_TOKEN", "")
   384|   384|    if existing_token:
   385|   385|        print(f"   MATTERMOST_ACCESS_TOKEN already set, skipping")
   386|   386|    else:
   387|   387|        token_data = mm.create_user_token(bot_user_id,
   388|   388|                                          description="OmniAgent bot access token")
   389|   389|        if isinstance(token_data, dict) and token_data.get("token"):
   390|   390|            new_token = token_data["token"]
   391|   391|            set_env_val("MATTERMOST_ACCESS_TOKEN", new_token)
   392|   392|            check(True, f"Generated bot access token and saved to .env")
   393|   393|        else:
   394|   394|            check(False, f"Failed to create token: {json.dumps(token_data)[:200]}")
   395|   395|
   396|   396|    # ── Step 5: Ensure team and channels exist ───────────────────────
   397|   397|    print("\n6. Ensuring team and channel...")
   398|   398|
   399|   399|    current_token = get_env_val("MATTERMOST_ACCESS_TOKEN", "")
   400|   400|    if current_token:
   401|   401|        bot_client = MMClient(server_url, current_token)
   402|   402|    else:
   403|   403|        bot_client = mm
   404|   404|
   405|   405|    teams = bot_client.get_teams()
   406|   406|    existing_teams = [t for t in teams if isinstance(t, dict)]
   407|   407|    team_name = get_env_val("MATTERMOST_TEAM_NAME", "test-team")
   408|   408|    team_display = get_env_val("MATTERMOST_TEAM_DISPLAY_NAME", "Test Team")
   409|   409|
   410|   410|    team = None
   411|   411|    for t in existing_teams:
   412|   412|        if t.get("name") == team_name:
   413|   413|            team = t
   414|   414|            break
   415|   415|
   416|   416|    if not team:
   417|   417|        team = bot_client.create_team(team_name, team_display)
   418|   418|        if isinstance(team, dict) and (team.get("id") or team.get("already_exists")):
   419|   419|            check(True, f"Team '{team_name}' created/exists")
   420|   420|        else:
   421|   421|            check(False, f"Failed to create team: {json.dumps(team)[:200]}")
   422|   422|    else:
   423|   423|        check(True, f"Team '{team_name}' exists (id: {team.get('id')})")
   424|   424|
   425|   425|    team_id = team.get("id") if isinstance(team, dict) else ""
   426|   426|    channel_name = get_env_val("MATTERMOST_CHANNEL_NAME", "test")
   427|   427|    channel_display = get_env_val("MATTERMOST_CHANNEL_DISPLAY_NAME", "Test")
   428|   428|
   429|   429|    if team_id:
   430|   430|        channels = bot_client.get_channels(team_id)
   431|   431|        channel = None
   432|   432|        for c in channels:
   433|   433|            if c.get("name") == channel_name:
   434|   434|                channel = c
   435|   435|                break
   436|   436|
   437|   437|        if not channel:
   438|   438|            channel = bot_client.create_channel(team_id, channel_name, channel_display)
   439|   439|            if isinstance(channel, dict) and (channel.get("id") or channel.get("already_exists")):
   440|   440|                check(True, f"Channel '{channel_name}' created/exists")
   441|   441|            else:
   442|   442|                check(False, f"Failed to create channel: {json.dumps(channel)[:200]}")
   443|   443|        else:
   444|   444|            check(True, f"Channel '{channel_name}' exists (id: {channel.get('id')})")
   445|   445|
   446|   446|        channel_id = channel.get("id") if isinstance(channel, dict) else ""
   447|   447|
   448|   448|        # Add all 3 users to the channel
   449|   449|        print("\n7. Adding users to channel...")
   450|   450|        for uid, label in [(admin_id, admin_user), (test_id, test_user), (bot_user_id, bot_user)]:
   451|   451|            if uid and channel_id:
   452|   452|                result = bot_client.add_channel_member(channel_id, uid)
   453|   453|                success = isinstance(result, dict) and result.get("user_id") == uid
   454|   454|                check(success, f"Added '{label}' to channel")
   455|   455|
   456|   456|        # Update MATTERMOST_CHANNEL_IDS in .env
   457|   457|        cur_ids_str = get_env_val("MATTERMOST_CHANNEL_IDS", "")
   458|   458|        cur_ids = [c.strip() for c in cur_ids_str.split(",") if c.strip()]
   459|   459|        if channel_id and channel_id not in cur_ids:
   460|   460|            cur_ids.append(channel_id)
   461|   461|            set_env_val("MATTERMOST_CHANNEL_IDS", ",".join(cur_ids))
   462|   462|            check(True, f"Updated MATTERMOST_CHANNEL_IDS")
   463|   463|    else:
   464|   464|        channel_id = ""
   465|   465|
   466|   466|    # ── Summary ──────────────────────────────────────────────────────
   467|   467|    print("\n" + "=" * 60)
   468|   468|    print("SETUP COMPLETE")
   469|   469|    print("=" * 60)
   470|   470|    print(f"  Server:    {server_url}")
   471|   471|    if site_url:
   472|   472|        print(f"  Site URL:  {site_url}")
   473|   473|    print(f"  Admin:     {admin_user} (id: {admin_id})")
   474|   474|    print(f"  Test user: {test_user} (id: {test_id})")
   475|   475|    print(f"  Bot user:  {bot_user} (id: {bot_user_id})")
   476|   476|    if team_id:
   477|   477|        print(f"  Team:      {team_name} (id: {team_id})")
   478|   478|    if channel_id:
   479|   479|        print(f"  Channel:   {channel_name} (id: {channel_id})")
   480|   480|    print()
   481|   481|    print("Next steps:")
   482|   482|    print("  1. Start omniagent: docker compose up -d")
   483|   483|    print("  2. Access Mattermost at " + (site_url or server_url))
   484|   484|    print("  3. Create additional channels as needed")
   485|   485|    print("  4. Configure channels via Dashboard (http://localhost:12346)")
   486|   486|    print("=" * 60)
   487|   487|
   488|   488|
   489|   489|if __name__ == "__main__":
   490|   490|    main()
   491|   491|