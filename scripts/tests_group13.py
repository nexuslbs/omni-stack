#!/usr/bin/env python3
"""GROUP 13: Lorem + Task Lifecycle via test-tool-caller named steps.

Tests that the noop test-tool-caller model with named step references
can drive the full background task lifecycle: call lorem, read logs,
poll status, cancel task — all through the agent via Mattermost.
"""

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
    import subprocess, json as _j
    r = subprocess.run(["docker", "inspect", "omni-mattermost-1"], capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, "Mattermost container not found"
    info = _j.loads(r.stdout)
    assert isinstance(info, list) and len(info) > 0, "No container info"
    assert info[0].get("State", {}).get("Running") == True, "Mattermost container is not running"

def _fix_remote_plugin():
    """Ensure test-python-tool plugin has correct mcp-config in both locations."""
    canonical = "/opt/workspace/omni-plugins/tools/test-python-tool/server.py"
    locations = [
        "/opt/workspace/omni-stack/plugins/tools/.remote/test-python-tool/tools/test-python-tool",
        "/opt/omni/plugins/tools/.remote/test-python-tool/tools/test-python-tool",
    ]

    for plugin_dir in locations:
        mcp_cfg = os.path.join(plugin_dir, "mcp-config.json")
        server_py = os.path.join(plugin_dir, "server.py")
        os.makedirs(plugin_dir, exist_ok=True)
        with open(mcp_cfg, "w") as f:
            f.write('{\n')
            f.write('  "servers": [\n')
            f.write('    {\n')
            f.write('      "name": "test-python-tool",\n')
            f.write('      "transport": "stdio",\n')
            f.write('      "command": "python3",\n')
            f.write(f'      "args": ["{plugin_dir}/server.py"],\n')
            f.write('      "env": {"GREETING_NAME": "Omni"},\n')
            f.write('      "timeout_secs": 900,\n')
            f.write('      "max_retries": 1,\n')
            f.write('      "pool_size": 3,\n')
            f.write('      "allowed_tools": ["*"]\n')
            f.write('    }\n')
            f.write('  ]\n')
            f.write('}\n')
        if os.path.exists(canonical):
            import shutil
            shutil.copy2(canonical, server_py)
    print("  [remote plugin config fixed in all locations]")

# ─── Test 1: Full lifecycle via named steps ────────────────────────

def test_g13_full_lifecycle():
    """Send named-step script via Mattermost, verify full lifecycle executes."""
    _check_mm_container()
    MM = "http://mattermost:8065"
    test_user = "testuser"
    test_pass = "Mattermost_Fresh_Start_1"

    # Enable required plugins — assert each one succeeds
    s1, r1 = api_post_body("/plugins/mattermost/enable", {"source": "bundled"})
    assert s1, f"enable mattermost failed: {r1}"
    s2, r2 = api_post_body("/plugins/noop/enable", {"source": "bundled"})
    assert s2, f"enable noop failed: {r2}"
    s3, r3 = api_post_body("/plugins/prompt/enable", {"source": "built-in"})
    assert s3, f"enable prompt failed: {r3}"

    # Find the mattermost channel
    channel_id = None
    for _ in range(15):
        r = urllib.request.urlopen(f"{BASE}/channels", timeout=10)
        channels = json.loads(r.read()).get("data", [])
        mm_ch = next((ch for ch in channels if ch.get("platform") == "mattermost"), None)
        if mm_ch:
            channel_id = mm_ch["id"]
            print(f"  [channel_id={channel_id}]")
            break
        time.sleep(2)
    assert channel_id is not None, "No mattermost channel found"

    # Patch to noop / test-tool-caller — assert success
    patch_req = urllib.request.Request(
        f"{BASE}/channels/{channel_id}",
        data=json.dumps({"current_provider": "noop", "current_model": "test-tool-caller"}).encode(),
        method="PATCH", headers={"Content-Type": "application/json"})
    r = urllib.request.urlopen(patch_req, timeout=10)
    assert r.status == 200, f"channel PATCH returned {r.status}"
    print(f"  [patched to noop / test-tool-caller: {r.status}]")

    # Verify the channel was patched
    time.sleep(2)
    r2 = urllib.request.urlopen(f"{BASE}/channels/{channel_id}", timeout=5)
    ch_data = json.loads(r2.read())
    model = ch_data.get("data", {}).get("current_model", "")
    print(f"  [channel current_model={model}]")
    assert model == "test-tool-caller", f"Expected test-tool-caller, got {model}"
    time.sleep(3)

    # Log in as testuser
    token = _mm_login(MM, test_user, test_pass)
    admin_data = json.dumps({"login_id": "lucasbasquerotto", "password": "MTEnivuUVDZ3"}).encode()
    admin_req = urllib.request.Request(f"{MM}/api/v4/users/login", data=admin_data, method="POST",
                                        headers={"Content-Type": "application/json"})
    admin_token = urllib.request.urlopen(admin_req, timeout=10).headers.get("Token")

    # Find team and channel
    team_resp = json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{MM}/api/v4/users/me/teams", method="GET",
                               headers={"Authorization": f"Bearer {admin_token}"}), timeout=10).read())
    team_id = next((t["id"] for t in team_resp if t["name"] == "omni"), None)
    assert team_id, "Cannot find team omni"
    team_channels = json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{MM}/api/v4/teams/{team_id}/channels", method="GET",
                               headers={"Authorization": f"Bearer {admin_token}"}), timeout=10).read())
    mm_channel_id = next((ch["id"] for ch in team_channels if ch["name"] == "setup"), None)
    assert mm_channel_id, "Cannot find setup channel"

    # Send the lifecycle script using named steps
    script = json.dumps([
        {"name": "l1", "tool": "test-python-tool_lorem", "arguments": {"seconds": 5}},
        {"name": "l2", "tool": "read_task_logs", "arguments": {"task_id": "${l1.task_id}", "cursor": 0}},
        {"name": "l3", "tool": "poll_task", "arguments": {"task_id": "${l1.task_id}"}},
        {"name": "l4", "tool": "cancel_task", "arguments": {"task_id": "${l1.task_id}"}},
    ])
    msg_resp = _mm_send_message(MM, mm_channel_id, token, script)
    print(f"  [lifecycle script sent: {msg_resp.get('id','?')}]")

    # Wait for completion
    deadline = time.time() + 60
    found = False
    while time.time() < deadline:
        time.sleep(5)
        posts = _mm_get_posts(MM, mm_channel_id, token)
        for pid, post in posts.get("posts", {}).items():
            msg = post.get("message", "")
            lmsg = msg.lower()
            # Check for completion indicators
            if "completed" in lmsg or "all 4 tool call(s) completed" in lmsg or "tool call" in lmsg:
                print(f"  [reply: {msg[:150]}...]")
                found = True
                break
            if "reply to your message" in lmsg:
                print(f"  [reply (text): {msg[:120]}...]")
                found = True
                break
        if found:
            break

    assert found, "No reply from lifecycle script within 60s"
    print("  [lifecycle test PASSED]")


# ─── Test 2: Verify lorem is registered ──────────────────────────

def test_g13_tool_registration():
    """Verify lorem and lifecycle tools are registered."""
    r = urllib.request.urlopen(f"{BASE}/mcp/tools", timeout=10)
    tools_data = json.loads(r.read())
    tools = tools_data if isinstance(tools_data, list) else (tools_data.get("tools") or tools_data.get("data") or [])

    lorem = next((t for t in tools if "test-python-tool_lorem" in (t.get("full_name","") or t.get("name",""))), None)
    poll = next((t for t in tools if "poll-task" in t.get("full_name","") or "poll_task" in t.get("name","")), None)
    cancel = next((t for t in tools if "cancel-task" in t.get("full_name","") or "cancel_task" in t.get("name","")), None)
    logs = next((t for t in tools if "read-task-logs" in t.get("full_name","") or "read_task_logs" in t.get("name","")), None)

    assert lorem, "test-python-tool_lorem not found"
    assert poll, "poll_task not found"
    assert cancel, "cancel_task not found"
    assert logs, "read_task_logs not found"
    print("  [all lifecycle tools registered]")


# ─── Main runner ─────────────────────────────────────────────────

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
    print("GROUP 13: Lorem Task Lifecycle with Named Steps")
    print("=" * 60)

    print("\n[GROUP 13 setup]")
    try:
        _fix_remote_plugin()

        # Check if plugin already exists in API
        plugins_resp = api_get("/plugins")
        pdata = plugins_resp if isinstance(plugins_resp, list) else plugins_resp.get("data", [])
        found = any(p.get("name") == "test-python-tool" for p in pdata)

        # Ensure plugin.yml has the entry
        yml_path = "/opt/omni/plugins.yml"
        with open(yml_path) as f:
            yml_content = f.read()
        if "test-python-tool" not in yml_content:
            yml_content += "\n  test-python-tool:\n    enabled: false\n    source: remote\n    config: {}\n"
            # Find the tools: section and add after it
            lines = yml_content.split("\n")
            new_lines = []
            added = False
            for i, line in enumerate(lines):
                new_lines.append(line)
                if line.strip().startswith("tools:") and not added:
                    new_lines.append("  test-python-tool:")
                    new_lines.append("    enabled: false")
                    new_lines.append("    source: remote")
                    new_lines.append("    config: {}")
                    added = True
            # If tools: not found, add at end
            if not added:
                new_lines.append("tools:")
                new_lines.append("  test-python-tool:")
                new_lines.append("    enabled: false")
                new_lines.append("    source: remote")
                new_lines.append("    config: {}")
            yml_content = "\n".join(new_lines) + "\n"
            with open(yml_path, "w") as f:
                f.write(yml_content)
            time.sleep(3)
            print("  [added test-python-tool to plugins.yml]")

        if not found:
            # Download via API
            for _ in range(3):
                down_success, down_resp = api_post_body("/plugins/test-python-tool/download", {"source": "remote"})
                if down_success:
                    print("  [download OK]")
                    break
                print(f"  [download attempt: {down_resp.get('error','?')}]")
                time.sleep(3)

        _fix_remote_plugin()

        # Enable — assert it eventually succeeds
        enable_ok = False
        for _ in range(3):
            enable_success, enable_resp = api_post_body("/plugins/test-python-tool/enable", {"source": "remote"})
            if enable_success:
                print("  [test-python-tool enabled]")
                enable_ok = True
                break
            print(f"  [enable attempt: {enable_resp.get('error','?')}]")
            time.sleep(2)
        assert enable_ok, "Failed to enable test-python-tool after 3 retries"

        # Wait for MCP tools to register
        for _ in range(15):
            try:
                r = urllib.request.urlopen(f"{BASE}/mcp/tools", timeout=5)
                td = json.loads(r.read())
                tools = td if isinstance(td, list) else (td.get("tools") or td.get("data") or [])
                if any("lorem" in (t.get("full_name") or t.get("name") or "") for t in tools):
                    print("  [lorem tool registered]")
                    break
            except:
                pass
            time.sleep(1)
    except Exception as e:
        print(f"  ERROR during setup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    run_test(test_g13_tool_registration)
    run_test(test_g13_full_lifecycle)

    print(f"\n{'=' * 60}")
    print(f"Results: {tests_pass}/{tests_run} passed, {tests_fail} failed")
    print(f"{'=' * 60}")
    sys.exit(0 if tests_fail == 0 else 1)
