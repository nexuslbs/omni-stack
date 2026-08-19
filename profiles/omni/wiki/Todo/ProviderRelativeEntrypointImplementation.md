# Provider Entrypoint: Resolve Relative Args Against the Plugin Directory

> Status: planned (omnidev board task)
> Scope: omniagent core (src/server/plugins_env.rs, src/provider/external/client.rs) + omni-plugins (providers/noop-full/plugin.json)

## Goal

Provider plugin entrypoints must support RELATIVE paths, resolved against
the plugin's install directory — not hardcoded absolute paths that break
when OMNI_DIR is set differently. Today `omni-plugins/providers/noop-full/
plugin.json` hardcodes `args: ["/opt/omni/plugins/providers/noop-full/
client.py"]`, which breaks if OMNI_DIR ≠ /opt/omni.

## Current state (verified 2026-08-18)

- **Platform loader ALREADY resolves relative args** (src/platform/external/
  mod.rs:158-180): each entrypoint arg that is not a flag and not absolute is
  joined against the plugin dir; if the candidate exists it is used, and the
  spawned config gets `current_dir: Some(plugin_dir)`. Platforms (telegram,
  test-python, test-js) already use relative `server.py`/`server.js` args.
- **Provider loader does NOT** (src/server/plugins_env.rs:119-181): for
  `source: remote` it only does a brittle string prefix replacement
  (`old_prefix` = `{data_dir}/plugins/{type_dir}/{bundled_dir}` →
  `base_dir` = `{data_dir}/plugins/{type_dir}/.remote/{name}/{subpath}`) —
  a relative arg passes through unchanged; for `built-in`/`bundled` args are
  used verbatim.
- **Provider spawn sets NO current_dir** (src/provider/external/client.rs:
  49-56: `Command::new(&self.command).args(&self.args)` with no `.current_dir`)
  — a relative arg would resolve against the omniagent process CWD, not the
  plugin dir.
- Affected files with hardcoded `/opt/omni`: providers/noop-full/plugin.json
  (entrypoint arg), tools/memory/server.py + tools/actions/server.py (script
  internals — check separately; not entrypoint args).

## Change

1. **omniagent — src/server/plugins_env.rs provider entrypoint resolution**:
   mirror the platform loader. For each provider entrypoint arg:
   - skip flags (starts with `-`) and absolute paths (pass through);
   - for relative args, join against the plugin's install dir (built-in:
     `/app/plugins/{type_dir}/{name}`; bundled:
     `{data_dir}/plugins/{type_dir}/{name}`; remote:
     `{data_dir}/plugins/{type_dir}/.remote/{name}/{subpath}`) — use the
     resolved absolute path when the candidate exists, else keep the arg.
   - keep the existing remote old-prefix replacement as a fallback for
     legacy absolute args (or remove it once no plugin.json ships absolute
     paths — prefer keeping for compat during the transition).
2. **omniagent — src/provider/external/client.rs**: add optional
   `current_dir` to `ExternalProviderClient` (new param or builder) and pass
   `Some(plugin_dir)` so relative args resolve against the plugin dir even
   if they are not joined at load time. Update `new()` callers (plugins_env
   reload path).
3. **omni-plugins — providers/noop-full/plugin.json**: change
   `"args": ["/opt/omni/plugins/providers/noop-full/client.py"]` →
   `"args": ["client.py"]` (relative; resolved by the loader). Grep the
   whole repo for other entrypoint args with absolute paths and fix them
   too (tools/memory, tools/actions only have /opt/omni in script internals
   — leave those unless they are entrypoint args).

## Verification gates

- `cargo check --workspace --all-targets` clean; `cargo test` green; `cargo
  fmt --check` clean (BARE commands — dev overlay SQLX_OFFLINE=false).
- A provider with `args: ["client.py"]` (noop-full) starts with OMNI_DIR set
  to a NON-default path (e.g. `/tmp/omni-test`): `GET /api/plugins` shows
  provider enabled/running; a chat completion through it succeeds.
- No `grep -rn "/opt/omni" omni-plugins/*/plugin.json` hits in entrypoint
  args (script internals may remain if they derive paths dynamically).

## Non-goals

- Do NOT change platform entrypoint resolution (already correct).
- Do NOT rename plugin.json fields or the remote.yml shape.
- Do NOT touch tools/memory or tools/actions script internals unless their
  /opt/omni references break with a different OMNI_DIR (out of scope).

## Repos

- omniagent (src/server/plugins_env.rs, src/provider/external/client.rs,
  src/provider/registry.rs if signature changes + tests)
- omni-plugins (providers/noop-full/plugin.json + any other absolute
  entrypoint args)

## Deliverable

Commit + push to origin/main on BOTH repos, report the commit SHAs. Provider
entrypoints support relative args resolved against the plugin dir, and
noop-full runs with any OMNI_DIR.
