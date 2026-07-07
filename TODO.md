# Plugin System Restructure — TODO

**Goal:** Unify and simplify the plugin directory layout, config files, and YAML conventions across omni-stack, omniagent, and omni-dashboard.

## Key Design Decisions

1. **`OMNI_DIR` = omni-stack root.** The omni-stack repository IS the data directory. No copies, no propagation. At runtime `OMNI_DIR` points to wherever the repo is mounted (`/opt/workspace/omni-stack`, `/opt/omni` in container).

2. **`plugins.yml` is the single source of truth** for plugin state. Each entry has an explicit `source` field (`built-in` / `bundled` / `remote`) — no more `builtin: bool` or `remote: {...}` guessing. The YAML entry **is** the source of truth: whatever `source` says, that's the active source.

3. **`remote.yml` is the single source of truth** for remote plugin metadata (URL, path, ref). When `plugins.yml` has `source: remote`, the lookup is: `remote.yml → context.my_plugin → {url, path, ref}`. The `remote:` field in `plugins.yml` is removed entirely.

4. **Omni-stack defines what plugins exist.** If a plugin isn't listed in `plugins.yml`, it isn't shown — regardless of whether its source files exist on disk. Exception: unlisted sources for a listed plugin (built-in binary, bundled source files, etc.) are still discovered and shown as "duplicated" / "available for switch".

5. **No backward compatibility.** Cut-over. Old files (`tools.yml`, `platforms.yml`, `providers.yml`, inline `remote:` fields) are removed. Old directory paths (`plugins/mcp/`) are migrated.

## Updated Data Model

### `plugins.yml` — plugin state (versioned)

```yaml
# {OMNI_DIR}/plugins.yml
platforms:
  slack:
    enabled: false
    source: bundled
    config: {}
tools:
  cron:
    enabled: true
    source: built-in
    config: {}
  test-rust-tool:
    enabled: true
    source: remote
    config: {}
providers:
  deepseek:
    enabled: true
    source: bundled
    config:
      api_key: "$env:DEEPSEEK_API_KEY"
      default_model: deepseek-v4-flash
```

- `source` is REQUIRED: `"built-in"` | `"bundled"` | `"remote"`
- No `builtin:` field
- No `remote:` field — remote metadata lives in `remote.yml`
- When `source: remote`, the URL/path/ref is looked up from `remote.yml` at `{context}.{key}` (e.g. `remote.yml → tools.test-rust-tool`)

### `remote.yml` — remote plugin metadata (versioned)

```yaml
# {OMNI_DIR}/remote.yml
platforms:
  example-platform:
    url: https://github.com/nexuslbs/omni-plugins.git
    path: platforms/example-platform
    ref: main
tools:
  test-rust-tool:
    url: https://github.com/nexuslbs/omni-plugins.git
    path: tools/test-rust-tool
providers:
  example-provider:
    url: https://github.com/nexuslbs/omni-plugins.git
    path: providers/example-provider
    ref: v1.2
```

- `ref` is optional — defaults to repo HEAD
- `path` is optional — defaults to plugin root (where `plugin.json` is)
- Top-level sections: `platforms`, `tools`, `providers` — mirrors `plugins.yml`
- Only contains entries for plugins whose source is `remote` in `plugins.yml`

### Directory Layout

```
{OMNI_DIR}/
├── plugins.yml              # Plugin state (versioned)
├── remote.yml               # Remote plugin metadata (versioned)
├── plugins/
│   ├── tools/               # Bundled tool plugins (renamed from mcp/)
│   │   ├── actions/
│   │   ├── cron/
│   │   └── ...
│   ├── platforms/           # Bundled platform plugins
│   │   └── mattermost/
│   ├── providers/           # Bundled provider plugins
│   │   └── openai/
│   └── .remote/             # Cloned remote plugin files (gitignored)
│       ├── tools/
│       │   └── test-rust-tool/
│       ├── platforms/
│       └── providers/
├── .gitignore
│   # plugins/.remote/ — regenerated from remote.yml
```

- `plugins/.remote/` is gitignored — cloned from `remote.yml` on demand
- `remote.yml` is versioned — defines what CAN be cloned
- Builtin plugins: compiled into omniagent binary or sidecar binaries at the bin path (not in `plugins/`)

## Display & Status Logic

| Condition | Status | Show |
|-----------|--------|------|
| Plugin in `plugins.yml` and source files found on disk | `enabled` / `disabled` (per YAML) | Normal card with toggle |
| Plugin in `plugins.yml` but NO source found in any of the 3 locations | `not_found` | Red badge. If `source: remote`, show **Download** button (clones from `remote.yml` + compiles) |
| Plugin in `plugins.yml`, source found, compilable but not compiled | `disabled` | Show **Install** button. If `source: remote`, also show **Remove** (deletes `.remote/` dir + `remote.yml` entry) |
| Plugin in `plugins.yml`, source found, compilable and compiled | `enabled` / `disabled` | Show **Uninstall** (removes `target/` dir) and **Reinstall** buttons |
| Plugin in `plugins.yml`, source found, non-compilable (script) | `enabled` / `disabled` | Show **Update** (re-clone) for remote. Show **Remove** for remote |
| Plugin has YAML entry but config is inconsistent / code can't load | `error` | Red error badge |
| Plugin source exists on disk but is NOT in `plugins.yml` (for a plugin that IS in the YAML under a different source) | `disabled` + `is_duplicated: true` | Duplicated badge (yellow) — shows alternative source that can be switched to |

## Implementation Steps

### Phase 1 — omni-stack (directory & config migration)

- [ ] Rename `plugins/mcp/` → `plugins/tools/`
- [ ] Create `plugins.yml` by merging existing `tools.yml` + `platforms.yml` + `providers.yml`, converting:
  - `builtin: true` → `source: built-in`
  - `builtin: false` (no remote) → `source: bundled`
  - `remote: {url, path, ...}` + no builtin → `source: remote` + entry goes into `remote.yml`
- [ ] Create `remote.yml` extracting all inline `remote:` fields from old YAMLs
- [ ] Delete `tools.yml`, `platforms.yml`, `providers.yml`
- [ ] Add `plugins/.remote/` to `.gitignore`
- [ ] Update README with new structure
- [ ] Update CI/CD pipelines if they reference old file paths

### Phase 2 — omniagent (code)

**Part A: Path & type renames**

- [ ] `PluginYamlType::Tool::type_dir_name()` → return `"tools"` instead of `"mcp"`
- [ ] Replace all hardcoded `"mcp"` strings:
  - `discover_plugins` → directory scan uses `type_dir_name()` dynamically
  - `get_plugin_dir_for_category` → same
  - `detect_plugin_category` → same
  - `delete_plugin_handler` → `.remote/` paths
  - `installer.rs` → `install_from_git`, `find_remote_plugin_json`
  - Container data dir `plugins/mcp/` → migrate to `plugins/tools/`

**Part B: `plugins.yml` — single file loading**

- [ ] Remove per-file loading (`load_raw(data_dir, pt)` that reads `tools.yml` / `platforms.yml` / `providers.yml`)
- [ ] New `load_plugins_yaml(data_dir)` reads single `{OMNI_DIR}/plugins.yml`, returns `(BTreeMap<Platform>, BTreeMap<Tool>, BTreeMap<Provider>)`
- [ ] Update all callers that use `load_raw` to use the new unified loader
- [ ] Remove `PluginYamlType::yaml_file()` (no more per-type filenames)

**Part C: Source field instead of builtin/remote flags**

- [ ] `PluginYamlEntry` struct:
  - Remove `builtin: Option<bool>` field
  - Remove `remote: Option<PluginRemote>` field
  - Add `source: PluginSource` enum: `BuiltIn`, `Bundled`, `Remote`
- [ ] `pick_primary_source` → simplified: YAML's `source` is the authority. No guessing from flags.
- [ ] `PluginDetail.source` → maps from `PluginSource`
- [ ] `detect_plugin_category` → reads from YAML `source` field
- [ ] Enable handler → no more `desired_builtin` logic. Sets `source` from the request body.
- [ ] `set_entry_with_builtin_override` → replaced by `set_entry_with_source`
- [ ] `clear_remote_field` → removed (no remote field in YAML)
- [ ] `set_entry_with_remote` → removed (remote lives in `remote.yml`)
- [ ] `build_plugin_detail` → no more `builtin`/`remote` YAML fields to pass through. Source is directly from `PluginYamlEntry.source`.

**Part D: `remote.yml` loading**

- [ ] `RemotePluginStore` → load from `{OMNI_DIR}/remote.yml` instead of `{OMNI_DIR}/plugins/.remote/plugins.yml`
- [ ] `save_remote_plugin`, `remove_remote_plugin`, `get_remote_plugin` → all operate on `remote.yml`
- [ ] When `source: remote` in `plugins.yml`, the URL/path/ref is found by looking up `remote.yml.{context}.{key}`
- [ ] Download handler reads `remote.yml` to get clone info
- [ ] Install handler: when source is remote, reads `remote.yml`
- [ ] Reinstall handler: re-clones remote via `remote.yml` info

**Part E: Display logic — not found & source missing detection**

- [ ] `list_plugins`: After grouping discovered sources, iterate `plugins.yml` entries. For each entry:
  - If no source group matches the key → create `status: "not_found"` entry
  - If `source: remote` → `needs_download: true`
  - If `source: bundled` → `needs_download: false`
- [ ] `get_plugin`: Same detection for single plugin lookup
- [ ] Unused YAML-only entries with no disk source get `has_source_code: false, needs_build: false`

### Phase 3 — omni-dashboard

- [ ] `plugin_type: "mcp"` → `plugin_type: "tool"` everywhere (API + frontend checks)
- [ ] Remove `isDuplicated && p.status === "disabled"` special-casing (source field is now explicit)
- [ ] Update enable/disable payload to send `{ source: "built-in" | "bundled" | "remote" }`
- [ ] Verify Download button for `status: "not_found"` + `source: "remote"` plugins
- [ ] Verify Install/Reinstall/Uninstall buttons per the display logic table above
- [ ] Verify Remove button for remote plugins (deletes `.remote/` dir + `remote.yml` entry)

### Phase 4 — validation & testing

- [ ] `plugins/mcp/` no longer exists — all tools under `plugins/tools/`
- [ ] `plugins.yml` loads and all plugins detected
- [ ] `remote.yml` is the sole source of remote info
- [ ] Enable built-in → YAML shows `source: built-in`
- [ ] Enable bundled → YAML shows `source: bundled`
- [ ] Enable remote → YAML shows `source: remote`, clone info from `remote.yml`
- [ ] Not-found status for YAML-only entries (both remote and non-remote)
- [ ] Download button clones from `remote.yml` and compiles
- [ ] Remove button deletes `.remote/` dir and `remote.yml` entry
- [ ] `"mcp"` no longer appears anywhere in the codebase (except possibly in MCP protocol references)

## Migration Script

A one-shot Python script should handle the omni-stack config migration:

```python
# 1. Load tools.yml, platforms.yml, providers.yml
# 2. For each entry:
#    - builtin: true  → source: built-in
#    - builtin: false (no remote) → source: bundled
#    - remote: {...}  → source: remote, extract to remote.yml
# 3. Write plugins.yml
# 4. Write remote.yml
# 5. Rename old files to *.bak
```

## Affected Files (omniagent)

| File | What changes |
|------|-------------|
| `src/plugins_yaml.rs` | Core data model: remove `builtin`/`remote` fields, add `source`, load single `plugins.yml`, load `remote.yml` |
| `src/server/plugins.rs` | Enable/disable/install/reinstall/delete/download handlers — use `source` field, read `remote.yml` |
| `src/plugin/installer.rs` | Discovery paths: `"mcp"` → `type_dir_name()` |
| `src/plugin/mod.rs` | `PluginManifest` — no changes needed |
| `AGENTS.md` | Full rewrite of plugin system docs |

## Affected Files (omni-dashboard)

| File | What changes |
|------|-------------|
| `src/pages/tools.ts` | `plugin_type: "mcp"` → `"tool"`, source handling |
| `src/pages/platforms.ts` | Same |
| `src/pages/providers.ts` | Same |
| `src/lib/plugin-config.ts` | Any source-dependent logic |
