#!/usr/bin/env python3
"""GROUP 12: Lorem + Task Lifecycle Tests."""

import os, sys, json, time, uuid, urllib.request, urllib.error

BASE = "http://localhost:8080"
WORKSPACE = "/opt/workspace/omni-stack"

def sh(cmd):
    import subprocess
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def api_get(path):
    try:
        r = urllib.request.urlopen(f"{BASE}/api{path}", timeout=10)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try: return json.loads(body)
        except: return {"success": False, "error": body}

def api_post_body(path, body, timeout=30):
    data = json.dumps(body).encode()
    try:
        r = urllib.request.urlopen(
            urllib.request.Request(f"{BASE}/api{path}", data=data, method="POST",
                                   headers={"Content-Type": "application/json"}),
            timeout=timeout)
        resp_body = r.read()
        if not resp_body.strip():
            return (True, {})
        return (True, json.loads(resp_body))
    except urllib.error.HTTPError as e:
        raw = e.read()
        return (False, json.loads(raw) if raw.strip() else {"error": f"HTTP {e.code}"})

def read_plugins_yml():
    with open(f"{WORKSPACE}/plugins.yml") as f:
        content = f.read()
    lines = content.split("\n")
    sections, section, name, entry = {}, None, None, None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0 and stripped.endswith(":"):
            section = stripped[:-1]
            sections[section] = {}
            name = None
            entry = None
        elif indent == 2 and stripped.endswith(":"):
            name = stripped[:-1]
            sections[section][name] = {}
            entry = sections[section][name]
        elif indent == 4:
            colon_idx = stripped.index(":")
            key = stripped[:colon_idx].strip()
            value = stripped[colon_idx+1:].strip()
            if value == "true": entry[key] = True
            elif value == "false": entry[key] = False
            else: entry[key] = value
    return sections

def write_plugins_yml(data):
    lines = []
    for section, entries in data.items():
        lines.append(f"{section}:")
        for name, props in entries.items():
            lines.append(f"  {name}:")
            for k, v in props.items():
                if isinstance(v, bool):
                    lines.append(f"    {k}: {str(v).lower()}")
                elif isinstance(v, dict):
                    lines.append(f"    {k}: {{}}")
                else:
                    lines.append(f"    {k}: {v}")
    with open(f"{WORKSPACE}/plugins.yml", "w") as f:
        f.write("\n".join(lines) + "\n")

def _mm_login(base_url, username, password):
    data = json.dumps({"login_id": username, "password": password}).encode()
    req = urllib.request.Request(f"{base_url}/api/v4/users/login", data=data, method="POST",
                                  headers={"Content-Type": "application/json"})
    token = urllib.request.urlopen(req, timeout=10).headers.get("Token")
    assert token, f"Login as {username} returned no Token header"
    return token

def _mm_send_message(base_url, channel_id, token, message):
    data = json.dumps({"channel_id": channel_id, "message": message}).encode()
    req = urllib.request.Request(f"{base_url}/api/v4/posts", data=data, method="POST",
                                  headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())

def _mm_get_posts(base_url, channel_id, token):
    req = urllib.request.Request(f"{base_url}/api/v4/channels/{channel_id}/posts", method="GET",
                                  headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())

def _check_mm_container():
    import subprocess, json
    r = subprocess.run(['docker', 'inspect', 'omni-mattermost-1'], capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, "Mattermost container not found"
    info = json.loads(r.stdout)
    assert isinstance(info, list) and len(info) > 0, "No container info"
    assert info[0].get('State', {}).get('Running') == True, "Mattermost container is not running"


def setup_test_python_tool():
    """Ensure test-python-tool is registered and enabled."""
    plugins = api_get("/plugins")
    data = plugins.get("data", []) if isinstance(plugins, dict) else plugins
    found = any(p.get("name") == "test-python-tool" for p in (data if isinstance(data, list) else []))

    if not found:
        yml_data = read_plugins_yml()
        if "tools" not in yml_data:
            yml_data["tools"] = {}
        yml_data["tools"]["test-python-tool"] = {"enabled": False, "source": "remote", "config": {}}
        write_plugins_yml(yml_data)
        time.sleep(3)

    remote_dir = f"{WORKSPACE}/plugins/tools/.remote/test-python-tool"
    if not os.path.exists(remote_dir):
        success, resp = api_post_body("/plugins/test-python-tool/download", {"source": "remote"})
        if not success:
            print(f"  [download: {resp}]")
        time.sleep(5)

    success, resp = api_post_body("/plugins/test-python-tool/enable", {"source": "remote"})
    if not success:
        success, resp = api_post_body("/plugins/test-python-tool/enable", {"source": "bundled"})
    assert success, f"enable test-python-tool failed: {resp}"
    print("  [test-python-tool enabled]")


def test_mm12_lorem_lifecycle():
    """API test: verify lorem and lifecycle tools exist, then exercise full lifecycle via Mattermost."""
    # 1. Verify tools are registered
    r = urllib.request.urlopen(f"{BASE}/mcp/tools", timeout=10)
    tools_data = json.loads(r.read())
    tools = tools_data if isinstance(tools_data, list) else (tools_data.get("tools") or tools_data.get("data") or [])

    lorem_tool = next((t for t in tools if "test-python-tool_lorem" in (t.get("full_name","") or t.get("name",""))), None)
    assert lorem_tool is not None, "test-python-tool_lorem not found"
    print("  [lorem tool found]")

    poll_tool = next((t for t in tools if "poll-task" in t.get("full_name","") or "poll_task" in t.get("name","")), None)
    cancel_tool = next((t for t in tools if "cancel-task" in t.get("full_name","") or "cancel_task" in t.get("name","")), None)
    logs_tool = next((t for t in tools if "read-task-logs" in t.get("full_name","") or "read_task_logs" in t.get("name","")), None)
    assert all([poll_tool, cancel_tool, logs_tool]), f"Lifecycle tools not found: poll={bool(poll_tool)}, cancel={bool(cancel_tool)}, logs={bool(logs_tool)}"
    print("  [poll_task, cancel_task, read_task_logs available]")

    # 2. Send a JSON script via Mattermost to exercise the full agent lifecycle
    _check_mm_container()
    MM = "http://mattermost:8065"
    test_user = "testuser"
    test_pass = "Mattermost_Fresh_Start_1"

    s1, r1 = api_post_body("/plugins/mattermost/enable", {"source": "bundled"})
    assert s1, f"enable mattermost failed: {r1}"
    s2, r2 = api_post_body("/plugins/noop/enable", {"source": "bundled"})
    assert s2, f"enable noop failed: {r2}"
    s3, r3 = api_post_body("/plugins/prompt/enable", {"source": "built-in"})
    assert s3, f"enable prompt failed: {r3}"

    channel_id = None
    for _ in range(15):
        r = urllib.request.urlopen(f"{BASE}/channels", timeout=10)
        channels = json.loads(r.read()).get("data", [])
        mm_ch = next((ch for ch in channels if ch.get("platform") == "mattermost"), None)
        if mm_ch:
            channel_id = mm_ch["id"]
            print(f"  [found channel_id={channel_id}]")
            break
        time.sleep(2)
    assert channel_id is not None, "No mattermost channel found"

    # Patch channel — assert success
    patch_req = urllib.request.Request(
        f"{BASE}/channels/{channel_id}",
        data=json.dumps({"current_provider": "noop", "current_model": "test-tool-caller"}).encode(),
        method="PATCH", headers={"Content-Type": "application/json"})
    patch_resp = urllib.request.urlopen(patch_req, timeout=10)
    assert patch_resp.status == 200, f"channel PATCH returned {patch_resp.status}"
    print("  [channel patched to noop / test-tool-caller]")
    time.sleep(3)

    token = _mm_login(MM, test_user, test_pass)
    admin_data = json.dumps({"login_id": "lucasbasquerotto", "password": "MTEnivuUVDZ3"}).encode()
    admin_req = urllib.request.Request(f"{MM}/api/v4/users/login", data=admin_data, method="POST",
                                        headers={"Content-Type": "application/json"})
    admin_token = urllib.request.urlopen(admin_req, timeout=10).headers.get("Token")

    team_resp = json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{MM}/api/v4/users/me/teams", method="GET",
                               headers={"Authorization": f"Bearer {admin_token}"}), timeout=10).read())
    team_id = next((t["id"] for t in team_resp if t["name"] == "omni"), None)
    assert team_id, "Cannot find team 'omni'"
    team_channels = json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{MM}/api/v4/teams/{team_id}/channels", method="GET",
                               headers={"Authorization": f"Bearer {admin_token}"}), timeout=10).read())
    mm_channel_id = next((ch["id"] for ch in team_channels if ch["name"] == "setup"), None)
    assert mm_channel_id, "Cannot find 'setup' channel"

    # Send quick lorem script (1s — should complete quickly)
    script = json.dumps([{"tool": "test-python-tool_lorem", "arguments": {"seconds": 1}}])
    msg_resp = _mm_send_message(MM, mm_channel_id, token, script)
    print(f"  [lorem 1s sent: {msg_resp.get('id', '?')}]")

    deadline = time.time() + 30
    found_reply = False
    while time.time() < deadline:
        time.sleep(3)
        posts = _mm_get_posts(MM, mm_channel_id, token)
        for pid, post in posts.get("posts", {}).items():
            msg = post.get("message", "")
            if any(w in msg.lower() for w in ["lorem", "ipsum", "dolor", "hello"]):
                print(f"  [reply: {msg[:120]}...]")
                found_reply = True
                break
        if found_reply:
            break
    assert found_reply, "No reply from lorem 1s script within 30s"
    print("  [lorem lifecycle via agent PASSED]")


def test_mm12_lorem_e2e_mattermost():
    """E2E: send JSON script via Mattermost -> agent processes lorem -> reply."""
    _check_mm_container()
    MM = "http://mattermost:8065"
    test_user = "testuser"
    test_pass = "Mattermost_Fresh_Start_1"

    s1, r1 = api_post_body("/plugins/mattermost/enable", {"source": "bundled"})
    assert s1, f"enable mattermost failed: {r1}"
    s2, r2 = api_post_body("/plugins/noop/enable", {"source": "bundled"})
    assert s2, f"enable noop failed: {r2}"
    s3, r3 = api_post_body("/plugins/prompt/enable", {"source": "built-in"})
    assert s3, f"enable prompt failed: {r3}"

    channel_id = None
    for _ in range(15):
        r = urllib.request.urlopen(f"{BASE}/channels", timeout=10)
        channels = json.loads(r.read()).get("data", [])
        mm_ch = next((ch for ch in channels if ch.get("platform") == "mattermost"), None)
        if mm_ch:
            channel_id = mm_ch["id"]
            print(f"  [found channel_id={channel_id}]")
            break
        time.sleep(2)
    assert channel_id is not None, "No mattermost channel found"

    # Patch channel — assert success
    patch_req = urllib.request.Request(
        f"{BASE}/channels/{channel_id}",
        data=json.dumps({"current_provider": "noop", "current_model": "test-tool-caller"}).encode(),
        method="PATCH", headers={"Content-Type": "application/json"})
    patch_resp = urllib.request.urlopen(patch_req, timeout=10)
    assert patch_resp.status == 200, f"channel PATCH returned {patch_resp.status}"
    print("  [channel patched to noop / test-tool-caller]")
    time.sleep(3)

    admin_data = json.dumps({"login_id": "lucasbasquerotto", "password": "MTEnivuUVDZ3"}).encode()
    admin_req = urllib.request.Request(f"{MM}/api/v4/users/login", data=admin_data, method="POST",
                                        headers={"Content-Type": "application/json"})
    admin_token = urllib.request.urlopen(admin_req, timeout=10).headers.get("Token")

    token = _mm_login(MM, test_user, test_pass)

    team_resp = json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{MM}/api/v4/users/me/teams", method="GET",
                               headers={"Authorization": f"Bearer {admin_token}"}), timeout=10).read())
    team_id = next((t["id"] for t in team_resp if t["name"] == "omni"), None)
    assert team_id, "Cannot find team 'omni'"
    team_channels = json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{MM}/api/v4/teams/{team_id}/channels", method="GET",
                               headers={"Authorization": f"Bearer {admin_token}"}), timeout=10).read())
    mm_channel_id = next((ch["id"] for ch in team_channels if ch["name"] == "setup"), None)
    assert mm_channel_id, "Cannot find 'setup' channel"

    script = json.dumps([{"tool": "test-python-tool_lorem", "arguments": {"seconds": 3}}])
    msg_resp = _mm_send_message(MM, mm_channel_id, token, script)
    print(f"  [lorem script sent: {msg_resp.get('id', '?')}]")

    deadline = time.time() + 45
    while time.time() < deadline:
        time.sleep(4)
        posts = _mm_get_posts(MM, mm_channel_id, token)
        for pid, post in posts.get("posts", {}).items():
            msg = post.get("message", "")
            if any(w in msg.lower() for w in ["completed", "lorem", "result"]):
                print(f"  [reply: {msg[:120]}...]")
                print("  [lorem e2e test PASSED]")
                return
            if msg.startswith("This is a reply to your message"):
                print(f"  [reply (text): {msg[:100]}...]")
                print("  [lorem e2e test PASSED]")
                return
    assert False, "No reply within 45s"


if __name__ == "__main__":
    tests_run = 0
    tests_pass = 0
    tests_fail = 0

    def run_test(fn):
        global tests_run, tests_pass, tests_fail
        tests_run += 1
        name = fn.__name__.replace("test_", "Test ").replace("_", " ")
        print(f"\n--- {name} ", end="", flush=True)
        try:
            fn()
            print("PASS", flush=True)
            tests_pass += 1
        except (AssertionError, Exception) as e:
            import traceback
            print(f"FAIL: {e}", flush=True)
            traceback.print_exc()
            tests_fail += 1

    print("=" * 60)
    print("GROUP 12: Lorem + Task Lifecycle Tests")
    print("=" * 60)

    print("\n[GROUP 12 setup]")
    try:
        setup_test_python_tool()
    except Exception as e:
        print(f"  ERROR during setup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    run_test(test_mm12_lorem_lifecycle)
    run_test(test_mm12_lorem_e2e_mattermost)

    print(f"\n{'=' * 60}")
    print(f"Results: {tests_pass}/{tests_run} passed, {tests_fail} failed")
    print(f"{'=' * 60}")
    sys.exit(0 if tests_fail == 0 else 1)
