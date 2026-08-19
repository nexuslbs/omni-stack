# Plugins: omni_dir Config Field for OMNI_DIR (remove hardcoded /opt/omni)

> Status: planned (omnidev board task)
> Scope: omni-plugins (tools/memory, tools/actions, tools/prompt + any other
> plugin with a hardcoded OMNI_DIR fallback)

## Goal

Plugins must resolve their data directory via an `omni_dir` config field
(default `$env:OMNI_DIR`) instead of hardcoding `/opt/omni` (or another
fixed path) as a fallback. No external config changes needed by default, and
the plugins work with any custom OMNI_DIR value.

## Current state (verified 2026-08-18)

- `tools/memory/server.py:90` and `tools/actions/server.py:69`:
  `def get_omni_dir(): return os.environ.get("OMNI_DIR", "/opt/omni")` —
  hardcoded `/opt/omni` fallback. The `omni_dir` config_schema field
  EXISTS in both plugin.json files (default `$env:OMNI_DIR`) but the
  scripts never read it — they only read the raw env var.
- `tools/prompt/server.py:571`: `data_dir = os.environ.get("OMNI_DIR",
  os.path.expanduser("~/.omniagent"))` — different hardcoded fallback, and
  `tools/prompt/plugin.json` has NO config_schema (no `omni_dir` field).
- The framework already supports the pattern: `apply_config_schema_defaults`
  (omniagent src/mcp/external/config.rs:579-631) resolves config_schema
  defaults (`$env:` refs via `plugins_yaml::resolve_config_value`, which
  strips `$env:` and reads the env var) and injects them into the MCP
  subprocess env under the config key. The `cfg_env()` helper in the python
  servers reads config-as-env (e.g. `cfg_env("omni_dir", "OMNI_DIR")`).
- mcp-config.json for memory/actions/prompt already passes
  `OMNI_DIR: $env:OMNI_DIR` in `env`, so the raw env var is usually present
  — the bug is the HARDCODED FALLBACK when it is absent.

## Change

1. **tools/memory/server.py** — `get_omni_dir()`: read the `omni_dir` config
   field first (env key injected from config_schema by the framework), then
   `OMNI_DIR`, then ERROR (no silent hardcoded path):
   ```python
   def get_omni_dir():
       return cfg_env("omni_dir") or os.environ.get("OMNI_DIR") or _fail_omni_dir()
   ```
   (keep the existing `cfg_env` helper; raise a clear RuntimeError naming the
   config field when neither is set).
2. **tools/actions/server.py** — same `get_omni_dir()` change.
3. **tools/prompt/server.py** — same pattern at the `data_dir` site (:571);
   ALSO add an `omni_dir` config_schema entry to
   `tools/prompt/plugin.json` (default `$env:OMNI_DIR`, label "OMNI_DIR",
   type string) so the framework injects it consistently.
4. **Verify plugin.json config_schema** for memory + actions already declare
   `omni_dir` (they do) — no change needed there beyond the script fix.
5. **Audit all plugins** in omni-plugins for other hardcoded `/opt/omni`,
   `~/.omniagent`, or fixed data-dir fallbacks (grep the repo; fix any
   entrypoint/config-site hits; script internals may keep a DYNAMIC default
   derived from env, but never a bare fixed path).

## Verification gates

- Grep: `grep -rn "get_omni_dir\|OMNI_DIR" omni-plugins/tools/*/server.py`
  shows config-first resolution; `grep -rn '"/opt/omni"\|"~/.omniagent"'
  omni-plugins/` shows NO bare fixed-path fallbacks in entrypoint/config
  sites.
- With OMNI_DIR unset in the subprocess env (simulate: `env -u OMNI_DIR
  python3 server.py` + a tool call) → clear error naming `omni_dir`, NOT a
  silent /opt/omni write.
- With OMNI_DIR set to a custom path → memory promote/list, actions
  hindsight_populator/relevance_indexer, prompt generation all operate
  under that path (create/read files there).
- With default stack (no external config) → behaves exactly as before
  (framework injects `omni_dir` from `$env:OMNI_DIR`).

## Non-goals

- Do NOT change the omniagent Rust config-schema injection mechanism (it
  already supports this).
- Do NOT change mcp-config.json env maps (already correct).
- Do NOT rename config keys or change tool interfaces.

## Repos

- omni-plugins (tools/memory/server.py, tools/actions/server.py,
  tools/prompt/server.py + plugin.json, any audited siblings)

## Deliverable

Commit + push to origin/main, report the commit SHA. All plugins resolve
their data dir via the `omni_dir` config field (default `$env:OMNI_DIR`),
no hardcoded paths, working with custom OMNI_DIR values.
