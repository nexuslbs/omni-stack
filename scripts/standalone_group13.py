#!/usr/bin/env python3
"""Standalone GROUP 13 test runner."""
import sys, json, os, time, uuid, subprocess, re
import urllib.request, urllib.error

BASE = "http://localhost:8080"
WORKSPACE = "/opt/workspace/omni-stack"
MM = "http://mattermost:8065"
TEST_PASS = "Mattermost_Fresh_Start_1"
TEST_USER = "testuser"

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def api_get(path):
    try:
        r = urllib.request.urlopen(f"{BASE}/api{path}", timeout=10)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try: return json.loads(body)
        except: return {"success": False, "error": body}

def api_post_body(path, body=None, timeout=15):
    """POST with JSON body. Returns (success, response_dict)."""
    import urllib.request, urllib.error, json
    url = f"{BASE}/api{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return (True, json.loads(r.read()))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try: return (False, json.loads(raw))
        except: return (False, {"error": raw, "code": e.code})
    except Exception as e:
        return (False, {"error": str(e)})

def _check_mm_container():
    rc = sh("docker inspect omni-mattermost-1 2>/dev/null | grep -q '\"Running\": true'")
    assert rc.returncode == 0, "Mattermost container (omni-mattermost-1) is not running"

def _mm_login(base_url, username, password):
    import urllib.request
    data = json.dumps({"login_id": username, "password": password}).encode()
    req = urllib.request.Request(f"{base_url}/api/v4/users/login", data=data, method="POST", headers={"Content-Type": "application/json"})
    token = urllib.request.urlopen(req, timeout=10).headers.get("Token")
    assert token, f"Login as {username} returned no Token header"
    return token

def _mm_send_message(base_url, channel_id, token, message):
    import urllib.request
    data = json.dumps({"channel_id": channel_id, "message": message}).encode()
    req = urllib.request.Request(f"{base_url}/api/v4/posts", data=data, method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())

def _mm_get_posts(base_url, channel_id, token):
    import urllib.request
    req = urllib.request.Request(f"{base_url}/api/v4/channels/{channel_id}/posts", method="GET", headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())

def _send_script_via_mm(mm_url, channel_id, token, script, wait_seconds=45):
    msg = json.dumps(script)
    msg_resp = _mm_send_message(mm_url, channel_id, token, msg)
    msg_id = msg_resp.get("id", "?")
    print(f"[script sent, post_id={msg_id}]")
    deadline = _time_module.time() + wait_seconds
    while _time_module.time() < deadline:
        _time_module.sleep(3)
        posts = _mm_get_posts(mm_url, channel_id, token)
        for pid, post in posts.get("posts", {}).items():
            pmsg = post.get("message", "")
            if "All " in pmsg and "tool call(s)" in pmsg:
                print(f"[response: {pmsg[:300]}]")
                return pmsg
    return None

def _get_setup_channel_id(mm_url, admin_token):
    team_resp = json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{mm_url}/api/v4/users/me/teams", method="GET",
                               headers={"Authorization": f"Bearer {admin_token}"}), timeout=10).read())
    team_id = next((t["id"] for t in team_resp if t["name"] == "omni"), None)
    if not team_id:
        return None, None
    channels_resp = json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{mm_url}/api/v4/teams/{team_id}/channels", method="GET",
                               headers={"Authorization": f"Bearer {admin_token}"}), timeout=10).read())
    setup_ch = next((ch for ch in channels_resp if ch["name"] == "setup"), None)
    return team_id, (setup_ch["id"] if setup_ch else None)

def _ensure_mm_for_group13():
    _check_mm_container()
    MM = "http://mattermost:8065"
    test_pass = "Mattermost_Fresh_Start_1"
    test_user = "testuser"
    for p in [("mattermost", "bundled"), ("noop", "bundled"),
              ("test-python-tool", "remote"), ("prompt", "built-in")]:
        s, r = api_post_body(f"/plugins/{p[0]}/enable", {"source": p[1]})
        assert s, f"enable {p[0]} failed: {r}"
    for _ in range(15):
        try:
            r = urllib.request.urlopen(urllib.request.Request(f"{BASE}/mcp/tools"), timeout=5)
            tools_data = json.loads(r.read())
            tools = tools_data if isinstance(tools_data, list) else (tools_data.get("tools") or tools_data.get("data") or [])
            tool_str = json.dumps(tools)
            if all(x in tool_str for x in ["lorem", "poll_task", "cancel_task", "read_task_logs"]):
                print("[all tools ready]")
                break
        except:
            pass
        _time_module.sleep(1)
    else:
        assert False, "Timed out waiting for lifecycle tools to register after enable"
    channel_id = None
    for _ in range(15):
        r = urllib.request.urlopen(f"{BASE}/channels", timeout=10)
        channels = json.loads(r.read()).get("data", [])
        mm_ch = next((ch for ch in channels if ch.get("platform") == "mattermost"), None)
        if mm_ch:
            channel_id = mm_ch["id"]
            print(f"[found channel id={channel_id}]")
            break
        _time_module.sleep(2)
    assert channel_id, "No mattermost channel found"
    req = urllib.request.Request(f"{BASE}/channels/{channel_id}",
        data=json.dumps({"current_provider": "noop", "current_model": "test-tool-caller"}).encode(),
        method="PATCH", headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)
    print("[channel patched: noop + test-tool-caller]")
    _time_module.sleep(3)
    admin_data = json.dumps({"login_id": "lucasbasquerotto", "password": "MTEnivuUVDZ3"}).encode()
    admin_req = urllib.request.Request(f"{MM}/api/v4/users/login", data=admin_data,
        method="POST", headers={"Content-Type": "application/json"})
    admin_token = urllib.request.urlopen(admin_req, timeout=10).headers.get("Token")
    assert admin_token, "Admin login failed"
    test_token = _mm_login(MM, test_user, test_pass)
    _, setup_ch_id = _get_setup_channel_id(MM, admin_token)
    assert setup_ch_id, "Cannot find 'setup' channel"
    return MM, setup_ch_id, test_token, admin_token, channel_id

def test_mm13a_lorem_lifecycle():
    """Start lorem via test-tool-caller, cancel it, verify lifecycle."""
    MM, setup_ch_id, test_token, admin_token, _ch_id = _ensure_mm_for_group13()
    script = [
        {"name": "l1", "tool": "test-python-tool_lorem", "arguments": {"seconds": 8}},
        {"name": "p1", "tool": "poll_task", "arguments": {"task_id": "${l1.task_id}"}},
        {"name": "c1", "tool": "cancel_task", "arguments": {"task_id": "${l1.task_id}"}},
        {"name": "p2", "tool": "poll_task", "arguments": {"task_id": "${l1.task_id}"}},
    ]
    result = _send_script_via_mm(MM, setup_ch_id, test_token, script, wait_seconds=50)
    assert result is not None, "No agent response within timeout"
    assert "[4]" in result, f"Expected [4] (poll after cancel), got: {result[:200]}"
    assert "cancelled" in result.lower(), f"Expected cancelled, got: {result[:300]}"
    assert "task_" in result, f"Missing task_id: {result[:300]}"
    print("[lorem lifecycle PASSED]")

def test_mm13b_lorem_complete():
    """Start lorem, wait for completion, read logs, verify output."""
    MM, setup_ch_id, test_token, admin_token, _ch_id = _ensure_mm_for_group13()
    script = [
        {"name": "l1", "tool": "test-python-tool_lorem", "arguments": {"seconds": 4}},
        {"name": "w1", "tool": "wait_task", "arguments": {"task_id": "${l1.task_id}", "timeout_secs": 30}},
        {"name": "r1", "tool": "read_task_logs", "arguments": {"task_id": "${l1.task_id}", "limit": 100}},
        {"name": "p1", "tool": "poll_task", "arguments": {"task_id": "${l1.task_id}"}},
    ]
    result = _send_script_via_mm(MM, setup_ch_id, test_token, script, wait_seconds=50)
    assert result is not None, "No agent response within timeout"
    assert "[4]" in result, f"Expected [4] (poll after wait), got: {result[:200]}"
    assert "completed" in result.lower() or "lorem" in result.lower(), \
        f"Expected completed lorem, got: {result[:300]}"
    print("[lorem completion PASSED]")

def test_mm13c_file_upload():
    """Upload a file to Mattermost and verify agent responds."""
    MM, setup_ch_id, test_token, admin_token, _ch_id = _ensure_mm_for_group13()
    test_content = b"Hello from test file upload!"
    boundary = _uuid.uuid4().hex
    data = b""
    data += f"--{boundary}\r\n".encode()
    data += b'Content-Disposition: form-data; name="channel_id"\r\n\r\n'
    data += f"{setup_ch_id}\r\n".encode()
    data += f"--{boundary}\r\n".encode()
    data += b'Content-Disposition: form-data; name="files"; filename="test.txt"\r\n'
    data += b"Content-Type: text/plain\r\n\r\n"
    data += test_content + b"\r\n"
    data += f"--{boundary}--\r\n".encode()
    upload_req = urllib.request.Request(
        f"{MM}/api/v4/files", data=data, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Authorization": f"Bearer {test_token}"})
    upload_resp = json.loads(urllib.request.urlopen(upload_req, timeout=15).read())
    file_id = upload_resp.get("file_infos", [{}])[0].get("id")
    assert file_id, f"File upload failed: {upload_resp}"
    print(f"[file uploaded: {file_id}]")
    tag = _uuid.uuid4().hex[:8]
    msg = f"File test [{tag}]"
    _mm_send_message(MM, setup_ch_id, test_token, msg)
    print(f"[post sent]")
    deadline = _time_module.time() + 40
    while _time_module.time() < deadline:
        _time_module.sleep(3)
        posts = _mm_get_posts(MM, setup_ch_id, test_token)
        for pid, post in posts.get("posts", {}).items():
            pmsg = post.get("message", "")
            if tag in pmsg or "reply to your message" in pmsg:
                print(f"[response: {pmsg[:150]}]")
                print("[file upload PASSED]")
                return
    assert False, "No response to file upload"

def test_mm13d_mcp_execute_lifecycle():
    """Verify lifecycle tools via /mcp/execute."""
    def _mcp(name, args=None):
        body = json.dumps({"name": name, "arguments": args or {}}).encode()
        req = urllib.request.Request(f"{BASE}/mcp/execute",
            data=body, method="POST", headers={"Content-Type": "application/json"})
        try:
            r = urllib.request.urlopen(req, timeout=10)
            return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return {"success": False, "error": e.read().decode()[:200]}
    r1 = _mcp("poll_task", {"task_id": "task_99999_1"})
    assert r1.get("success"), f"poll_task failed: {r1}"
    assert "not_found" in str(r1).lower() or "status" in str(r1).lower(), f"poll_task unexpected: {r1}"
    r2 = _mcp("cancel_task", {"task_id": "task_99999_1"})
    assert r2.get("success"), f"cancel_task failed: {r2}"
    r3 = _mcp("read_task_logs", {"task_id": "task_99999_1", "limit": 10})
    assert r3.get("success"), f"read_task_logs failed: {r3}"
    r4 = _mcp("test-python-tool_echo", {"input": "lifecycle-test"})
    assert r4.get("success"), f"echo failed: {r4}"
    assert "Hello" in str(r4), f"echo unexpected: {r4}"
    print("[mcp_execute lifecycle tools PASSED]")


tests_run = 0; tests_pass = 0; tests_fail = 0

def test(fn):
    global tests_run, tests_pass, tests_fail
    tests_run += 1
    name = fn.__name__
    print(f'  [{tests_run}] {name}...', end=' ', flush=True)
    try:
        fn()
        print('PASS')
        tests_pass += 1
    except AssertionError as e:
        print(f'FAIL: {e}')
        tests_fail += 1
    except Exception as e:
        import traceback
        print(f'ERROR: {e}')
        traceback.print_exc()
        tests_fail += 1

print(); print('=' * 60)
print('GROUP 13: Background Task Lifecycle + File Upload Tests')
print('=' * 60)

for fn in [test_mm13a_lorem_lifecycle, test_mm13b_lorem_complete, test_mm13c_file_upload, test_mm13d_mcp_execute_lifecycle]:
    test(fn)

print(f'\nResults: {tests_pass}/{tests_run} passed, {tests_fail} failed')
sys.exit(0 if tests_fail == 0 else 1)
