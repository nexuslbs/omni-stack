# Provider/Model Overrides via config/models.yml — Implementation

**Status:** Todo (task 16 — LAST in the serial chain, after compact+prune task 15)
**Date:** 2026-08-19
**Scope:** omniagent (core config + provider registry + API), omni-stack
(config/models.yml sample), omni-dashboard (/models page)

## Goal

Allow overriding provider definitions and per-model settings WITHOUT writing a
new plugin or any custom code — a pure definition file `config/models.yml` in
OMNI_DIR. Providers defined there (with or without a backing plugin) appear in
provider selects and can be used on threads with provider+model. Per-model
definitions override plugin config; budgets and output-size settings become
scoped per provider and per model with precedence **model > provider >
plugin/core config**.

## Verified facts (do not re-derive — greps from 2026-08-19)

- **Provider plugins**: `/opt/workspace/omniagent/plugins/providers/`
  {deepseek, noop, noop-full, openai, opencode-go} + `/opt/workspace/omni-plugins/providers/`
  {noop, noop-full}. Manifest shape (deepseek/plugin.json): `name`, `version`,
  `type: "provider"`, `description`, `default_base_url`
  ("https://api.deepseek.com/v1"), `api_mode` ("chat_completions"),
  `supports_reasoning` (bool), `config_schema`: [{key:"api_key", type:"secret"},
  {key:"default_model", type:"enum", default, refresh_url,
  allowed_values:["deepseek-v4-flash","deepseek-v3","deepseek-r1"]}].
  NOTE: the deepseek allowed_values are WRONG for the user's real models —
  the motivation for this feature.
- **Core ProviderMetadata** (src/llm/mod.rs:57-69): name, default_base_url,
  api_mode, api_modes (HashMap mode→model-prefix wildcards, per-model API mode
  resolution), default_model, supports_reasoning. Loaded by
  `read_provider_manifest` (:88) + `scan_provider_manifests` (:154);
  resolvers `resolve_default_base_url` (:285), `resolve_provider_api_mode`
  (:327), `match_model_api_mode` (:352).
- **plugins.yml providers** (config/plugins.yml:114-134): deepseek
  (api_key: `$secret:DEEPSEEK_API_KEY`), noop, noop-full, openai (disabled),
  opencode-go; `source: built-in|bundled`.
- **$env:/$secret: expansion exists**: src/platform/external/mod.rs:291-315
  (`resolve $env:VAR` and `$secret:NAME` from the secrets table); plugins.yml
  api_key already uses it — models.yml api_key must reuse the same expansion.
- **api_key runtime lookup**: `resolve_llm_api_key` (src/llm/mod.rs:401) reads
  from the provider's resolved plugin config.
- **Settings keys**: `max_tokens` / `max_tokens_on_truncation` (execution
  category — settings.rs:177-178, 318-328, 659-660, 758-759; AgentConfig
  fields config.rs:74-77; used executor.rs:129). Token budgets: prompt plugin
  has `token_budget_soft/hard` (plugins/tools/prompt); core uses
  `prompt_char_budget_*` today — task 12 (budget unification) makes token
  budgets the single unit, task 15 (compact+prune→plugin) moves them
  plugin-owned. Per-model `token_budget_soft/hard` in models.yml must feed the
  effective per-thread budget accordingly (coordinate with tasks 12/15).
- **refresh-models API**: `POST /api/plugins/{type}/{source}/{name}/refresh-models`
  → refresh_models_handler (src/server/plugins.rs:90-91, 204).
- **Dashboard**: Providers menu (src/lib/plugin-list.ts:54, createPluginPage →
  pages/providers.ts); the channel models selector (src/lib/channel-config.ts
  :276-300+) reads `default_model`'s `allowed_values` from the provider
  plugin's config_schema (with a Refresh Models button) — THIS is what the
  models.yml `models` array replaces when present.
- omniagent supports ONLY two api formats natively: `chat_completions`
  (openai) and `anthropic` (messages). A custom provider plugin is only needed
  for formats omniagent does NOT support.

## Design (user spec 2026-08-19 — do NOT re-litigate)

New file `config/models.yml` in OMNI_DIR (no new plugin, no custom code):

```yaml
providers:
  deepseek:
    plugin: true            # true/name → use the provider plugin (plugins.yml); false → builtin support
    models: ["deepseek-v4-flash", "deepseek-v4-pro"]   # replaces default_model.allowed_values in selectors
  my_provider_01:
    plugin: false           # no plugin: works via builtin chat_completions/anthropic formats
    api_mode: "chat_completions"
    supports_reasoning: true
    default_base_url: "http://noop-provider:9090/v1"
    refresh_url: "https://api.deepseek.com/v1/models"
    default_model: "test-model-1"
    api_key: "$secret:MY_SECRET"   # supports $env: and $secret: notation
    models: ["my_model_01", "my_model_02", "my_model_03"]
    model_config:
      my_model_02:
        api_mode: "anthropic"       # per-model overrides (provider value = default)
        supports_reasoning: false
        token_budget_soft: 200000
        token_budget_hard: 1000000
        max_tokens: 32000
        max_tokens_on_truncation: 128000
```

Semantics:
- `providers` top-level; each child = provider name. May or may not have a
  plugin. Field `plugin:` (bool or plugin name) identifies "use the provider
  plugin" vs "use builtin provider support". Look at what current plugins do.
- Providers with NO plugin still appear in provider selects and can be set on
  threads (provider+model) — resolved through builtin chat_completions /
  anthropic message formats.
- Same name as an existing provider plugin → OVERRIDES it (models.yml wins);
  the plugin is still used behind the scenes (api transport), but selectors +
  per-model definitions come from models.yml.
- Fields at provider level (api_mode, default_base_url, refresh_url,
  default_model, api_key, supports_reasoning, + any plugin.json config keys):
  when a provider plugin exists, these OVERRIDE the plugin config.
- Per-model config allowed for `api_mode` and `supports_reasoning` (one model
  may reason, another not; provider-level = default for all).
- Per-model config for `token_budget_soft/hard`, `max_tokens`,
  `max_tokens_on_truncation` (same names as prompt plugin / core settings),
  scoped per provider+model. Precedence: **model > provider > plugin/core config**.

## Requirements

1. **models.yml parsing** (core): serde structs (ProviderOverride, ModelConfig);
   load from `{OMNI_DIR}/config/models.yml` at startup; absent/empty file →
   zero behavior change (backward compatible). Malformed file → startup error
   or logged warning with disabled overrides (decide; prefer fail-loud with a
   clear message).
2. **Provider registry overlay**: merge models.yml over the manifest-derived
   ProviderMetadata map; provider-level fields override; add plugin-less
   providers with builtin formats (chat_completions/anthropic); `api_key`
   resolved via existing $env:/$secret: expansion; expose merged provider list
   (incl. models array) in the plugins/providers API the dashboard consumes.
3. **Precedence resolution**: per-thread (provider+model) resolution of
   api_mode, supports_reasoning, budgets (token_budget_soft/hard) and
   max_tokens/max_tokens_on_truncation — model > provider > plugin/core.
   Feed resolved values to the executor LLM call (max_tokens,
   executor.rs:129 path) and to the effective per-thread token budget
   (prompt plugin after tasks 12/15 — coordinate so per-model budgets win).
4. **Dashboard models selector**: when models.yml defines a provider, the
   channel model selector (channel-config.ts) and provider page show the
   `models` array INSTEAD of `default_model.allowed_values`; keep
   allowed_values/refresh-models as the fallback for providers NOT in
   models.yml.
5. **API**: GET /api/models (parsed models.yml or raw) + PUT /api/models
   (atomic write of config/models.yml; validate before write). Provider list
   API includes models.yml-only providers + merged metadata.
6. **Dashboard /models page**: new menu entry "Models" right after "Providers"
   (plugin-list.ts + router.ts + new pages/models.ts): render models.yml
   content, add/edit/delete provider definitions + fields + models +
   per-model config; Save → PUT /api/models; reload behavior consistent with
   other config pages.
7. **omni-stack sample**: add config/models.yml with the deepseek example
   (models: ["deepseek-v4-flash", "deepseek-v4-pro"]) as the documented
   pattern (commented or minimal), plus a Reference page in the wiki
   (Reference/Models-Yml.md or extend Agent-Guidance-Architecture).
8. **Tests**: unit — YAML parse, merge precedence (model>provider>plugin),
   secret expansion ($env:/$secret:), plugin-less provider resolution,
   malformed yml; integration — thread runs with a models.yml-defined
   plugin-less provider (noop-style chat_completions via builtin) and a
   models.yml-overridden provider (deepseek models list surfaces in API);
   dashboard /models CRUD smoke; no regression when models.yml absent.

## Non-goals / DO NOT CHANGE

- NO new plugin type, NO custom-code plugins, NO changes to the plugin
  registry/loading mechanism (MCP stays).
- NO DB migration — models.yml is a config file only.
- Do NOT change how providers behave when models.yml is absent/empty.
- Do NOT add new api formats (still chat_completions + anthropic; a custom
  plugin remains the path for others).
- Do NOT break the existing Providers page / refresh-models flow for providers
  not present in models.yml.

## Verification gates

- cargo check / clippy -D warnings / cargo test / fmt --check clean.
- deploy.py dev passes (omni-deployer dev-flavor).
- Live smoke (omnidev): (1) define a plugin-less provider in models.yml →
  appears in GET /plugins provider list + channel model selector shows its
  `models`; (2) run a thread with provider=that, model=X (builtin
  chat_completions/anthropic path) — completes; (3) override deepseek models →
  selector shows models.yml list, not plugin.json allowed_values; (4) PUT
  /api/models persists + survives reload; (5) absent models.yml → byte-identical
  behavior to before.
- Precedence unit test: same key at model, provider, and core levels → model
  wins; provider beats plugin.json; plugin.json beats core defaults.
- Secret expansion test: api_key "$env:X" and "$secret:Y" both resolve; no
  secret ever leaks into logs/API responses.
- Dashboard /models page: add/edit/delete a provider def → saved file matches
  the edited YAML.

## Deliverable

omniagent commit(s) (core + API) + omni-stack commit (models.yml sample +
wiki reference) + omni-dashboard commit (/models page) + SHAs + evidence.
Standing release loop: tasks → deploy.py dev → main → stable (never push
stable while omnistable tasks run).
