#!/usr/bin/env python3
"""
Idempotent integration tests for the Remove API (DELETE /api/plugins/{name}).

EVERY test is fully self-contained:
  1. SETUP: upsert YAML entries, install remote plugins, copy bundled dirs
  2. RUN: make the API call
  3. VERIFY: check the result
  4. CLEANUP: restore plugins.yml, remote.yml, and any temporary dirs

Running twice produces identical results.
"""

import os, sys, json, shutil, subprocess, time, re
import urllib.request, urllib.error

# ═══════════════════════════════════════════════════════════════════════
#  Config
# ═══════════════════════════════════════════════════════════════════════

def _container_ip():
    return subprocess.run(
        ["docker", "inspect", "omni-omniagent-1", "--format",
         "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
        capture_output=True, text=True
    ).stdout.strip()

BASE = f"http://{_container_ip()}:8080"
WORKSPACE = "/opt/workspace/omni-stack"
REMOTE_REPO = "/opt/workspace/omni-plugins"

# ═══════════════════════════════════════════════════════════════════════
#  Shell helpers
# ═══════════════════════════════════════════════════════════════════════

def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r

# ═══════════════════════════════════════════════════════════════════════
#  API helpers
# ═══════════════════════════════════════════════════════════════════════

def api_get(path):
    try:
        r = urllib.request.urlopen(f"{BASE}/api{path}", timeout=10)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try: return json.loads(body)
        except: return {"success": False, "error": body}

def api_delete(path):
    req = urllib.request.Request(f"{BASE}/api{path}", method="DELETE")
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return (True, json.loads(r.read()))
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try: return (False, json.loads(body))
        except: return (False, {"error": body})

# ═══════════════════════════════════════════════════════════════════════
#  YAML helpers (manual parsing, no pyyaml)
# ═══════════════════════════════════════════════════════════════════════

def read_plugins_yml():
    r = sh(f"sudo cat {WORKSPACE}/plugins.yml")
    lines = r.stdout.split("\n")
    sections, section, name, entry = {}, None, None, None
    config_lines, in_config = None, False

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if in_config and indent <= 6:
            if config_lines:
                config_str = "\n".join(config_lines)
                entry["config"] = config_str
                config_lines = None
            in_config = False
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
            if value == "":
                entry[key] = {}
                in_config = True
                config_lines = []
            else:
                if value == "true": entry[key] = True
                elif value == "false": entry[key] = False
                elif value == "{}": entry[key] = {}
                elif value.startswith('"') and value.endswith('"'): entry[key] = value[1:-1]
                elif value.startswith("'") and value.endswith("'"): entry[key] = value[1:-1]
                else: entry[key] = value
        elif indent == 6 and in_config:
            colon_idx = stripped.index(":")
            subkey = stripped[:colon_idx].strip()
            subval = stripped[colon_idx+1:].strip()
            if subval.startswith('"') and subval.endswith('"'): subval = subval[1:-1]
            elif subval.startswith("'") and subval.endswith("'"): subval = subval[1:-1]
            if isinstance(entry.get("config"), dict):
                entry["config"][subkey] = subval
            else:
                config_lines.append(line)
    return sections

def write_plugins_yml(data):
    lines = []
    for section, entries in data.items():
        lines.append(f"{section}:")
        for name, props in entries.items():
            lines.append(f"  {name}:")
            for k, v in props.items():
                if isinstance(v, dict) and v:
                    lines.append(f"    {k}:")
                    for sk, sv in v.items():
                        sv_str = json.dumps(sv) if "'" in str(sv) or sv == "" else str(sv)
                        lines.append(f"      {sk}: {sv_str}")
                elif isinstance(v, bool):
                    lines.append(f"    {k}: {str(v).lower()}")
                elif isinstance(v, dict) and not v:
                    lines.append(f"    {k}: {{}}")
                elif v == "" or v is None:
                    lines.append(f"    {k}: ''")
                else:
                    lines.append(f"    {k}: {v}")
        lines.append("")
    content = "\n".join(lines)
    proc = subprocess.Popen(["sudo", "tee", f"{WORKSPACE}/plugins.yml"],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True)
    proc.communicate(content)
    proc.wait()

def yaml_get(entry_type, name):
    data = read_plugins_yml()
    return data.get(entry_type, {}).get(name, None)

def yaml_set(entry_type, name, data_dict):
    data = read_plugins_yml()
    if entry_type not in data:
        data[entry_type] = {}
    data[entry_type][name] = data_dict
    write_plugins_yml(data)

def yaml_del(entry_type, name):
    data = read_plugins_yml()
    if entry_type in data and name in data[entry_type]:
        del data[entry_type][name]
        write_plugins_yml(data)

def yaml_has(entry_type, name):
    return yaml_get(entry_type, name) is not None

def read_remote_yml():
    r = sh(f"sudo cat {WORKSPACE}/remote.yml")
    # parse simple key: value
    data = {"tools": {}, "platforms": {}, "providers": {}}
    section = None
    for line in r.stdout.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0 and stripped.endswith(":"):
            section = stripped[:-1]
            if section not in data:
                data[section] = {}
        elif indent == 2 and section:
            name = stripped.split(":")[0].strip()
            data[section][name] = True
    return data

def remote_yml_has(name, type_dir="tools"):
    data = read_remote_yml()
    return name in data.get(type_dir, {})

# ═══════════════════════════════════════════════════════════════════════
#  File helpers (sudo)
# ═══════════════════════════════════════════════════════════════════════

def exists(path):
    r = sh(f"test -e '{path}'")
    return r.returncode == 0

def cp(src, dst, recursive=False):
    flag = "-a" if recursive else ""
    sh(f"sudo cp {flag} '{src}' '{dst}'")

def mv(src, dst):
    sh(f"sudo mv '{src}' '{dst}'")

def rm_rf(path):
    sh(f"sudo rm -rf '{path}'")

def mkdir_p(path):
    sh(f"sudo mkdir -p '{path}'")

# ── Save/Restore state (per-test) ────────────────────────────────────
# Each test may call backup_* and restore_* inside its try/finally.
# The .bak file is the per-test contract — do not nest backup/restore.

def backup_plugins_yml():
    sh(f"sudo cp {WORKSPACE}/plugins.yml {WORKSPACE}/plugins.yml.bak")

def restore_plugins_yml():
    if os.path.exists(f"{WORKSPACE}/plugins.yml.bak"):
        sh(f"sudo cp {WORKSPACE}/plugins.yml.bak {WORKSPACE}/plugins.yml")
        sh(f"sudo rm -f {WORKSPACE}/plugins.yml.bak")
        sh(f"sudo chown hermes:hermes {WORKSPACE}/plugins.yml")

def backup_remote_yml():
    sh(f"sudo cp {WORKSPACE}/remote.yml {WORKSPACE}/remote.yml.bak")

def restore_remote_yml():
    if os.path.exists(f"{WORKSPACE}/remote.yml.bak"):
        sh(f"sudo cp {WORKSPACE}/remote.yml.bak {WORKSPACE}/remote.yml")
        sh(f"sudo rm -f {WORKSPACE}/remote.yml.bak")
        sh(f"sudo chown hermes:hermes {WORKSPACE}/remote.yml")

# ═══════════════════════════════════════════════════════════════════════
#  Idempotent Setup Helpers
# ═══════════════════════════════════════════════════════════════════════
#
# These ensure a plugin exists in the desired state so the test
# preconditions are always met, regardless of previous test runs.

def ensure_bundled_plugin(name, plugin_type="tools"):
    """Ensure a bundled plugin directory exists.
    Sources (checked in order):
      1. Already exists at target path
      2. .remote/ directory (for remote→bundled collision tests)
      3. omni-plugins repo (/opt/workspace/omni-plugins/)
      4. Workspace git checkout (for deleted omni-stack bundled plugins)
    """
    target = f"{WORKSPACE}/plugins/{plugin_type}/{name}"
    if exists(target):
        return  # already exists

    # Try .remote/ source (remote→bundled collision tests)
    remote_src = f"{WORKSPACE}/plugins/{plugin_type}/.remote/{name}/{plugin_type}/{name}"
    if exists(remote_src):
        cp(remote_src, target, recursive=True)
        return

    # Try local omni-plugins repo (used for remote plugin installs)
    repo_src = f"{REMOTE_REPO}/{plugin_type}/{name}"
    if exists(repo_src):
        mkdir_p(f"{WORKSPACE}/plugins/{plugin_type}")
        cp(repo_src, target, recursive=True)
        return

    # Try restoring from omni-stack git (for bundled plugins deleted by tests)
    subprocess.run(
        f"cd {WORKSPACE} && git checkout -- plugins/{plugin_type}/{name} 2>&1",
        shell=True, capture_output=True, text=True
    )
    if exists(target):
        return

    raise RuntimeError(
        f"Cannot create bundled plugin '{name}' in {plugin_type}: "
        f"no source found in .remote/, {REMOTE_REPO}, or git history"
    )

def remove_bundled_plugin(name, plugin_type="tools"):
    """Remove a bundled plugin directory we created temporarily."""
    target = f"{WORKSPACE}/plugins/{plugin_type}/{name}"
    if exists(target):
        rm_rf(target)

def ensure_remote_plugin(name, plugin_type="tools"):
    """Install a remote plugin from the local repo if not already installed."""
    remote_dir = f"{WORKSPACE}/plugins/{plugin_type}/.remote/{name}"
    if exists(remote_dir):
        return  # already installed

    # Check local omni-plugins repo
    repo_src = f"{REMOTE_REPO}/{plugin_type}/{name}"
    if not exists(repo_src):
        raise RuntimeError(f"Cannot install remote plugin '{name}': source not found in repo")

    # Copy source to .remote/<name>/<type>/<name>/
    dest_base = f"{WORKSPACE}/plugins/{plugin_type}/.remote/{name}"
    mkdir_p(f"{dest_base}/{plugin_type}")
    cp(repo_src, f"{dest_base}/{plugin_type}/{name}", recursive=True)

    # Register in remote.yml (via sh to the file)
    remote_yml_path = f"{WORKSPACE}/remote.yml"
    entry = f"\n  {name}:\n    url: https://github.com/nexuslbs/omni-plugins.git\n    path: {plugin_type}/{name}\n"
    sh(f"echo '{entry}' | sudo tee -a {remote_yml_path} > /dev/null")

def remove_remote_plugin(name, plugin_type="tools"):
    """Remove a remote plugin we installed temporarily."""
    remote_dir = f"{WORKSPACE}/plugins/{plugin_type}/.remote/{name}"
    if exists(remote_dir):
        rm_rf(remote_dir)
    # Remove from remote.yml
    sh(f"sudo sed -i '/^  {name}:/,/^  /d' {WORKSPACE}/remote.yml")
    sh(f"sudo sed -i '/^$/'d {WORKSPACE}/remote.yml")  # remove blank lines

# ── Restart agent ────────────────────────────────────────────────────

def get_container_ip():
    return _container_ip()

def restart_agent():
    global BASE
    sh("docker restart omni-omniagent-1")
    time.sleep(8)
    for _ in range(15):
        ip = get_container_ip()
        if ip:
            url = f"http://{ip}:8080/health"
            try:
                r = urllib.request.urlopen(url, timeout=3)
                if r.status == 200:
                    BASE = f"http://{ip}:8080"
                    return
            except:
                pass
        time.sleep(2)
    raise RuntimeError("Failed to restart omniagent")

# ═══════════════════════════════════════════════════════════════════════
#  Test harness
# ═══════════════════════════════════════════════════════════════════════

tests_run = 0
tests_pass = 0
tests_fail = 0

def test(fn):
    global tests_run, tests_pass, tests_fail
    tests_run += 1
    name = fn.__name__.replace("test_", "Test ").replace("_", " ")
    print(f"\n--- {name} ", end="", flush=True)
    try:
        fn()
        print("✓ PASS", flush=True)
        tests_pass += 1
    except AssertionError as e:
        print(f"✗ FAIL: {e}", flush=True)
        import traceback
        traceback.print_exc()
        tests_fail += 1
    except Exception as e:
        print(f"✗ ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        tests_fail += 1

def expect_error(resp, substring):
    assert not resp[0], f"expected error, got success={resp[1]}"
    err_text = json.dumps(resp[1]).lower()
    assert substring.lower() in err_text, f"expected '{substring}' in error, got: {resp[1]}"

# ═══════════════════════════════════════════════════════════════════════
#  TESTS
# ═══════════════════════════════════════════════════════════════════════
#
# Group A: Source NOT in YAML (3 tests)
#   A1. Built-in → 400 error
#   A2. Bundled → succeed, YAML unaffected
#   A3. Remote → succeed, YAML unaffected
#
# Group B: Source IN YAML (3 tests)
#   B1. Built-in → 400 error
#   B2. Bundled → succeed, YAML + disk removed
#   B3. Remote → succeed, YAML + .remote/ removed
#
# Group C: YAML entry but no disk (1 test)
#   C1. Phantom plugin → succeed, YAML only removed
#
# Group D: Provider tests (2 tests)
#   D1. Bundled provider IN YAML → succeed, YAML + disk
#   D2. Bundled provider NOT in YAML → succeed, YAML unaffected
#
# Group E: Platform tests (2 tests)
#   E1. Bundled platform IN YAML → succeed, YAML + disk
#   E2. Bundled platform NOT in YAML → succeed, YAML unaffected
#
# Group F: Name collision tests (2 tests)
#   F1. Bundled+remote same name, YAML source=bundled → removes bundled only
#   F2. Bundled+remote same name, YAML source=remote → removes remote only

# ── A1: Built-in NOT in YAML → 400 error ─────────────────────────────

def test_a1():
    """Built-in plugin with NO YAML entry → should ERROR 400"""
    plugin, ptype = "search", "tools"

    backup_plugins_yml()
    try:
        # Setup: remove YAML entry
        if yaml_has(ptype, plugin):
            yaml_del(ptype, plugin)
            restart_agent()

        success, resp = api_delete(f"/plugins/{plugin}")
        expect_error((success, resp), "cannot remove built-in")
    finally:
        # Restore: add YAML entry back
        if not yaml_has(ptype, plugin):
            yaml_set(ptype, plugin, {"enabled": True, "source": "built-in", "config": {}})
            restart_agent()
        restore_plugins_yml()
        restart_agent()


# ── A2: Bundled NOT in YAML → succeed, YAML unaffected ───────────────

def test_a2():
    """Bundled plugin with NO YAML entry → succeed, YAML unchanged, disk removed"""
    plugin, ptype = "fetch", "tools"
    plugin_dir = f"{WORKSPACE}/plugins/{ptype}/{plugin}"

    backup_plugins_yml()
    try:
        # Setup: ensure bundled exists on disk, no YAML entry
        ensure_bundled_plugin(plugin, ptype)
        if yaml_has(ptype, plugin):
            yaml_del(ptype, plugin)
            restart_agent()

        success, resp = api_delete(f"/plugins/{plugin}")
        assert success, f"expected success, got {resp}"
        assert not exists(plugin_dir), "plugin dir still on disk"
        # YAML should be unaffected (no entry existed)
        assert not yaml_has(ptype, plugin), "YAML was affected but shouldn't have been"
    finally:
        restore_plugins_yml()
        restart_agent()


# ── A3: Remote NOT in YAML → succeed, YAML unaffected ────────────────

def test_a3():
    """Remote plugin with NO YAML entry → succeed, YAML unchanged, .remote/ removed"""
    plugin, ptype = "test-rust-tool", "tools"
    remote_dir = f"{WORKSPACE}/plugins/{ptype}/.remote/{plugin}"

    backup_plugins_yml()
    backup_remote_yml()
    try:
        # Setup: ensure remote plugin installed, no YAML entry
        ensure_remote_plugin(plugin, ptype)
        if yaml_has(ptype, plugin):
            yaml_del(ptype, plugin)

        success, resp = api_delete(f"/plugins/{plugin}")
        assert success, f"expected success, got {resp}"
        assert not exists(remote_dir), ".remote dir still on disk"
        # YAML unaffected (no entry existed)
        assert not yaml_has(ptype, plugin), "YAML was affected but shouldn't have been"
        # remote.yml entry should be gone
        assert not remote_yml_has(plugin, ptype), "remote.yml entry should be removed"
    finally:
        restore_remote_yml()
        restore_plugins_yml()


# ── B1: Built-in IN YAML → 400 error ─────────────────────────────────

def test_b1():
    """Built-in plugin WITH YAML entry → should ERROR 400, YAML untouched"""
    plugin, ptype = "search", "tools"

    # Setup: ensure YAML entry with source=built-in
    entry = yaml_get(ptype, plugin)
    if not entry or entry.get("source") != "built-in":
        yaml_set(ptype, plugin, {"enabled": True, "source": "built-in", "config": {}})
        restart_agent()

    success, resp = api_delete(f"/plugins/{plugin}")
    expect_error((success, resp), "cannot remove built-in")

    # Verify YAML entry is still intact
    assert yaml_has(ptype, plugin), "YAML entry was removed but should remain"


# ── B2: Bundled IN YAML → succeed, YAML + disk removed ───────────────

def test_b2():
    """Bundled plugin WITH YAML entry → succeed, YAML + disk removed"""
    plugin, ptype = "filesystem", "tools"
    plugin_dir = f"{WORKSPACE}/plugins/{ptype}/{plugin}"

    # Setup: ensure bundled dir exists
    ensure_bundled_plugin(plugin, ptype)

    backup_plugins_yml()
    try:
        # Upsert YAML with source=bundled
        yaml_set(ptype, plugin, {"enabled": True, "source": "bundled", "config": {}})
        restart_agent()

        success, resp = api_delete(f"/plugins/{plugin}")
        assert success, f"expected success, got {resp}"
        assert not exists(plugin_dir), "plugin dir still on disk"
        assert not yaml_has(ptype, plugin), "YAML entry still present"
    finally:
        restore_plugins_yml()
        restart_agent()


# ── B3: Remote IN YAML → succeed, YAML + .remote/ removed ────────────

def test_b3():
    """Remote plugin WITH YAML entry → succeed, YAML + .remote/ removed"""
    plugin, ptype = "test-python-tool", "tools"
    remote_dir = f"{WORKSPACE}/plugins/{ptype}/.remote/{plugin}"

    # Setup: ensure remote plugin installed
    ensure_remote_plugin(plugin, ptype)

    backup_plugins_yml()
    backup_remote_yml()
    try:
        # Upsert YAML with source=remote
        yaml_set(ptype, plugin, {"enabled": True, "source": "remote", "config": {}})
        restart_agent()

        success, resp = api_delete(f"/plugins/{plugin}")
        assert success, f"expected success, got {resp}"
        assert not exists(remote_dir), ".remote dir still on disk"
        assert not yaml_has(ptype, plugin), "YAML entry still present"
        assert not remote_yml_has(plugin, ptype), "remote.yml entry should be removed"
    finally:
        restore_remote_yml()
        restore_plugins_yml()
        restart_agent()


# ── C1: Phantom plugin in YAML but not on disk → succeed, YAML only ──

def test_c1():
    """Plugin in YAML (source=built-in) but NOT on disk → succeed, YAML only"""
    plugin, ptype = "phantom-plugin", "tools"
    fake_entry = {"enabled": True, "source": "built-in", "config": {}}

    # Safety check: plugin must not exist anywhere
    for t in ["tools", "platforms", "providers"]:
        for base in [WORKSPACE, "/app"]:
            p = f"{base}/plugins/{t}/{plugin}"
            cmd = ["docker", "exec", "omni-omniagent-1", "test", "-e", p]
            r = subprocess.run(cmd, capture_output=True)
            assert r.returncode != 0, f"Plugin '{plugin}' exists at {p} — test would fail!"

    backup_plugins_yml()
    try:
        # Add YAML entry for a phantom plugin (source=built-in but no disk)
        yaml_set(ptype, plugin, fake_entry)
        restart_agent()

        success, resp = api_delete(f"/plugins/{plugin}")
        assert success, f"expected success, got {resp}"
        assert not yaml_has(ptype, plugin), "YAML entry still present"
    finally:
        restore_plugins_yml()
        restart_agent()


# ── D1: Bundled provider IN YAML → succeed, YAML + disk removed ──────

def test_d1():
    """Bundled provider WITH YAML entry → succeed, YAML + disk removed"""
    plugin, ptype = "noop", "providers"
    plugin_dir = f"{WORKSPACE}/plugins/{ptype}/{plugin}"

    # Setup: ensure bundled provider dir exists
    ensure_bundled_plugin(plugin, ptype)

    backup_plugins_yml()
    try:
        # Upsert YAML with source=bundled
        yaml_set(ptype, plugin, {"enabled": True, "source": "bundled", "config": {}})
        restart_agent()

        success, resp = api_delete(f"/plugins/{plugin}")
        assert success, f"expected success, got {resp}"
        assert not exists(plugin_dir), "provider dir still on disk"
        assert not yaml_has(ptype, plugin), "YAML entry still present"
    finally:
        restore_plugins_yml()
        restart_agent()


# ── D2: Bundled provider NOT in YAML → succeed, YAML unaffected ──────

def test_d2():
    """Bundled provider with NO YAML entry → succeed, YAML unchanged, disk removed"""
    plugin, ptype = "noop-full", "providers"
    plugin_dir = f"{WORKSPACE}/plugins/{ptype}/{plugin}"

    backup_plugins_yml()
    try:
        # Setup: ensure bundled exists on disk, no YAML entry
        ensure_bundled_plugin(plugin, ptype)
        if yaml_has(ptype, plugin):
            yaml_del(ptype, plugin)
            restart_agent()

        success, resp = api_delete(f"/plugins/{plugin}")
        assert success, f"expected success, got {resp}"
        assert not exists(plugin_dir), "provider dir still on disk"
        assert not yaml_has(ptype, plugin), "YAML was affected but shouldn't have been"
    finally:
        restore_plugins_yml()
        restart_agent()


# ── E1: Bundled platform IN YAML → succeed, YAML + disk removed ──────

def test_e1():
    """Bundled platform WITH YAML entry → succeed, YAML + disk removed"""
    plugin, ptype = "mattermost", "platforms"
    plugin_dir = f"{WORKSPACE}/plugins/{ptype}/{plugin}"

    # Setup: ensure bundled platform dir exists
    ensure_bundled_plugin(plugin, ptype)

    backup_plugins_yml()
    try:
        # Upsert YAML with source=bundled
        yaml_set(ptype, plugin, {"enabled": True, "source": "bundled", "config": {}})
        restart_agent()

        success, resp = api_delete(f"/plugins/{plugin}")
        assert success, f"expected success, got {resp}"
        assert not exists(plugin_dir), "platform dir still on disk"
        assert not yaml_has(ptype, plugin), "YAML entry still present"
    finally:
        restore_plugins_yml()
        restart_agent()


# ── E2: Bundled platform NOT in YAML → succeed, YAML unaffected ──────

def test_e2():
    """Bundled platform with NO YAML entry → succeed, YAML unchanged, disk removed"""
    plugin, ptype = "telegram", "platforms"
    plugin_dir = f"{WORKSPACE}/plugins/{ptype}/{plugin}"

    backup_plugins_yml()
    try:
        # Setup: ensure bundled exists on disk, no YAML entry
        ensure_bundled_plugin(plugin, ptype)
        if yaml_has(ptype, plugin):
            yaml_del(ptype, plugin)
            restart_agent()

        success, resp = api_delete(f"/plugins/{plugin}")
        assert success, f"expected success, got {resp}"
        assert not exists(plugin_dir), "platform dir still on disk"
        assert not yaml_has(ptype, plugin), "YAML was affected but shouldn't have been"
    finally:
        restore_plugins_yml()
        restart_agent()


# ── F1: Name collision — bundled source, both exist ──────────────────

def test_f1():
    """Same name bundled+remote, YAML source=bundled → removes bundled only"""
    plugin, ptype = "test-rust-tool", "tools"
    bundled_dir = f"{WORKSPACE}/plugins/{ptype}/{plugin}"
    remote_dir = f"{WORKSPACE}/plugins/{ptype}/.remote/{plugin}"

    # Ensure both bundled and remote exist
    ensure_remote_plugin(plugin, ptype)
    ensure_bundled_plugin(plugin, ptype)  # copies from .remote/ to bundled

    backup_plugins_yml()
    backup_remote_yml()
    try:
        # YAML says source=bundled
        yaml_set(ptype, plugin, {"enabled": True, "source": "bundled", "config": {}})
        restart_agent()

        success, resp = api_delete(f"/plugins/{plugin}")
        assert success, f"expected success, got {resp}"

        # Bundled dir should be gone
        assert not exists(bundled_dir), "bundled dir should have been removed"
        # Remote dir should remain (source mismatch — YAML says bundled, disk has remote too)
        assert exists(remote_dir), "remote dir should NOT have been removed"
        # YAML entry should be gone (source matched bundled)
        assert not yaml_has(ptype, plugin), "YAML entry should have been removed"
        # remote.yml should still have the entry
        assert remote_yml_has(plugin, ptype), "remote.yml entry should remain"
    finally:
        # Restore remote plugin (bundled was deleted, remote is still there)
        # clean up the bundled copy we created (if it was re-created during test)
        remove_bundled_plugin(plugin, ptype)
        restore_remote_yml()
        restore_plugins_yml()
        restart_agent()


# ── F2: Name collision — remote source, both exist ───────────────────

def test_f2():
    """Same name bundled+remote, YAML source=remote → removes remote only"""
    plugin, ptype = "test-python-tool", "tools"
    bundled_dir = f"{WORKSPACE}/plugins/{ptype}/{plugin}"
    remote_dir = f"{WORKSPACE}/plugins/{ptype}/.remote/{plugin}"

    # Ensure both bundled and remote exist
    ensure_remote_plugin(plugin, ptype)
    ensure_bundled_plugin(plugin, ptype)  # copies from .remote/ to bundled

    backup_plugins_yml()
    backup_remote_yml()
    try:
        # YAML says source=remote
        yaml_set(ptype, plugin, {"enabled": True, "source": "remote", "config": {}})
        restart_agent()

        success, resp = api_delete(f"/plugins/{plugin}")
        assert success, f"expected success, got {resp}"

        # Remote dir should be gone
        assert not exists(remote_dir), ".remote dir should have been removed"
        # Bundled dir should remain (source mismatch — YAML says remote, disk has bundled too)
        assert exists(bundled_dir), "bundled dir should NOT have been removed"
        # YAML entry should be gone (source matched remote)
        assert not yaml_has(ptype, plugin), "YAML entry should have been removed"
        # remote.yml entry should be gone
        assert not remote_yml_has(plugin, ptype), "remote.yml entry should have been removed"
    finally:
        # Clean up: remove the temporary bundled copy, restore remote
        remove_bundled_plugin(plugin, ptype)
        restore_remote_yml()
        restore_plugins_yml()
        restart_agent()


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        r = urllib.request.urlopen(f"{BASE}/health", timeout=5)
        assert r.status == 200
        print(f"API healthy at {BASE}\n")
    except Exception as e:
        print(f"API not accessible: {e}")
        sys.exit(1)

    for fn in [
        test_a1, test_a2, test_a3,
        test_b1, test_b2, test_b3,
        test_c1,
        test_d1, test_d2,
        test_e1, test_e2,
        test_f1, test_f2,
    ]:
        test(fn)

    print(f"\n{'='*50}")
    print(f"Results: {tests_pass}/{tests_run} passed, {tests_fail} failed")
    print(f"{'='*50}")

    sys.exit(0 if tests_fail == 0 else 1)
