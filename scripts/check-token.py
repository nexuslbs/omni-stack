#!/usr/bin/env python3
import os, subprocess, json

token = os.environ.get("GITHUB_TOKEN", "")
print(f"Token len: {len(token)}, first 4: {token[:4]}")

# Test access to omni-stack repo
result = subprocess.run([
    "curl", "-s",
    "-H", f"Authorization: Bearer {token}",
    "-H", "Accept: application/vnd.github.v3+json",
    "https://api.github.com/repos/nexuslbs/omni-stack"
], capture_output=True, text=True, timeout=10)
data = json.loads(result.stdout) if result.stdout.strip() else {}
print(json.dumps(data, indent=2)[:400])
