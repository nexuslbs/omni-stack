#!/usr/bin/env python3
"""Run all tests: GROUP 12 first, then main suite."""
import subprocess, sys, os

tests_py = "/opt/workspace/omni-stack/scripts/tests.py"
group12_py = "/opt/workspace/omni-stack/scripts/tests_group12.py"
plugin_dir = "/opt/workspace/omni-stack/plugins/tools/.remote/test-python-tool/tools/test-python-tool"
mcp_cfg = os.path.join(plugin_dir, "mcp-config.json")
server_py = os.path.join(plugin_dir, "server.py")
canonical = "/opt/workspace/omni-plugins/tools/test-python-tool/server.py"

print("=" * 60)
print("SETUP: Fix remote plugin config")
print("=" * 60)

os.makedirs(plugin_dir, exist_ok=True)
with open(mcp_cfg, "w") as f:
    f.write('{\n')
    f.write('  "servers": [\n')
    f.write('    {\n')
    f.write('      "name": "test-python-tool",\n')
    f.write('      "transport": "stdio",\n')
    f.write('      "command": "python3",\n')
    f.write('      "args": ["%s"],\n' % server_py)
    f.write('      "env": {"GREETING_NAME": "Omni"},\n')
    f.write('      "timeout_secs": 900,\n')
    f.write('      "max_retries": 1,\n')
    f.write('      "pool_size": 3,\n')
    f.write('      "allowed_tools": ["*"]\n')
    f.write('    }\n')
    f.write('}\n')
print("  mcp-config.json written")

if os.path.exists(canonical):
    import shutil
    shutil.copy2(canonical, server_py)
    print("  server.py copied from canonical")
else:
    print("  WARNING: canonical not found")

print()
print("=" * 60)
print("PHASE 1: GROUP 12")
print("=" * 60)
sys.stdout.flush()
r1 = subprocess.run([sys.executable, "-u", group12_py], capture_output=False, timeout=120)
if r1.returncode != 0:
    sys.exit(r1.returncode)
print("OK: GROUP 12 passed")

print()
print("=" * 60)
print("PHASE 2: Main Suite")
print("=" * 60)
sys.stdout.flush()
r2 = subprocess.run([sys.executable, "-u", tests_py], capture_output=False, timeout=600)
if r2.returncode != 0:
    sys.exit(r2.returncode)
print("OK: Main suite passed")

print()
print("=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)
