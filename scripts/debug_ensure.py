#!/usr/bin/env python3
import sys, os
sys.path.insert(0, "/opt/workspace/omni-stack/scripts")

# Copy the needed functions without importing the module
WORKSPACE = "/opt/workspace/omni-stack"
REMOTE_REPO = "/opt/workspace/omni-plugins"
BASE = "http://localhost:8080/api"

def exists(path):
    return os.path.exists(path)

def mkdir_p(path):
    os.makedirs(path, exist_ok=True)

def cp(src, dst, recursive=True):
    import shutil
    if recursive:
        shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)

name = "test-rust-tool"
plugin_type = "tools"
remote_dir = "%s/plugins/%s/.remote/%s" % (WORKSPACE, plugin_type, name)
plugin_json = "%s/%s/%s/plugin.json" % (remote_dir, plugin_type, name)

print("plugin_json path: %s" % plugin_json)
print("Exists: %s" % exists(plugin_json))

repo_src = "%s/%s/%s" % (REMOTE_REPO, plugin_type, name)
print("Repo source: %s" % repo_src)
print("Repo exists: %s" % exists(repo_src))

# Perform copy
if not exists(plugin_json):
    print("Copying from repo...")
    if os.path.exists(remote_dir):
        import shutil
        shutil.rmtree(remote_dir)
    dest_base = remote_dir
    mkdir_p("%s/%s" % (dest_base, plugin_type))
    cp(repo_src, "%s/%s/%s" % (dest_base, plugin_type, name), recursive=True)
    print("Copied!")

# Check
cargo_path = "%s/%s/%s/Cargo.toml" % (remote_dir, plugin_type, name)
print("Cargo.toml at %s: %s" % (cargo_path, exists(cargo_path)))

# Show structure
for root, dirs, files in os.walk(remote_dir):
    for f in files:
        if f in ("plugin.json", "Cargo.toml"):
            rel = os.path.relpath(os.path.join(root, f), remote_dir)
            print("  FILE: %s" % rel)
    if root.count(os.sep) - remote_dir.count(os.sep) >= 2:
        del dirs[:]  # limit depth
