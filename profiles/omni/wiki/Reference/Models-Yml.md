# Models-Yml — Provider/Model Overrides via `config/models.yml`

Reference: how to override provider definitions and per-model settings WITHOUT
writing a plugin or any custom code. Pure definition file, loaded at startup
from `{OMNI_DIR}/config/models.yml`. Absent/empty file → zero behavior change;
malformed file → startup fails with a clear error.

Spec: `Todo/ModelOverridesConfigImplementation.md` (omni-stack commit e0210f6).

## When to use

- A provider plugin's hardcoded `default_model.allowed_values` is wrong or
  missing new models (e.g. deepseek plugin lacks `deepseek-v4-pro`).
- You want a provider that has no plugin at all — builtin
  `chat_completions` / `anthropic_messages` support is enough.
- You want per-provider / per-model token budgets, `max_tokens` /
  `max_tokens_on_truncation`, `api_mode`, `supports_reasoning`, base URL or
  API key without touching plugin config.

## Format

```yaml
providers:
  deepseek:
    plugin: true                        # use the provider plugin (plugins.yml)
    models: ["deepseek-v4-flash", "deepseek-v4-pro"]  # replaces allowed_values in selectors
  my_provider_01:
    plugin: false                       # no plugin: builtin chat_completions/anthropic
    api_mode: "chat_completions"        # "chat_completions" | "anthropic_messages"
    supports_reasoning: true
    default_base_url: "http://noop-provider:9090/v1"
    refresh_url: "https://api.deepseek.com/v1/models"
    default_model: "test-model-1"
    api_key: "$secret:MY_SECRET"        # $env:VAR and $secret:NAME both supported
    models: ["my_model_01", "my_model_02", "my_model_03"]
    model_config:
      my_model_02:
        api_mode: "anthropic"
        supports_reasoning: false
        token_budget_soft: 200000
        token_budget_hard: 1000000
        max_tokens: 32000
        max_tokens_on_truncation: 128000
```

## Semantics

- `providers.<name>.plugin`: `true` or a plugin name → the provider plugin is
  used for transport (plugins.yml); `false` → builtin support. A name that
  matches an existing provider plugin OVERRIDES it: selectors and definitions
  come from models.yml, the plugin still handles transport.
- `providers.<name>.models` replaces `default_model.allowed_values` in every
  selector (channels page, providers page, /models page). Refresh button on a
  provider with `refresh_url` upserts this list.
- Provider-level fields override the plugin manifest/config:
  `api_mode`, `supports_reasoning`, `default_base_url`, `refresh_url`,
  `default_model`, `api_key`, `token_budget_soft`, `token_budget_hard`,
  `max_tokens`, `max_tokens_on_truncation`.
- `model_config.<model>` overrides per model — highest precedence.

## Budget fallback chain (exact, per user spec 2026-08-19)

For EACH of soft and hard token budget INDEPENDENTLY:

1. `model_config.<model>` budget (models.yml);
2. else provider-level budget (`providers.<name>` soft/hard);
3. else GLOBAL settings budget (`prompt_token_budget_soft` default 100000 /
   `prompt_token_budget_hard` default 500000 in settings.yml).

`max_tokens` / `max_tokens_on_truncation` follow the same chain
(model > provider > settings).

omniagent RESOLVES the effective values and passes them to the prompt plugin's
compact-messages tool as `soft_budget` / `hard_budget` params. The prompt
plugin stays agnostic of models.yml — it only ever sees resolved budgets.

## API

- `GET /api/models` — parsed models.yml content.
- `PUT /api/models` — validates + atomically writes models.yml; provider
  metadata rebuilds immediately (no restart).

## Refresh flow

The dashboard refresh button (providers page, channel model selector, /models
page) never mutates the plugin: it fetches the remote models (`refresh_url`,
reusing the existing `fetch_enum_values` + api_key resolution) and UPSERTS the
models.yml entry via the omniagent API:

- entry absent → `plugin: true` + `models: [fetched]`;
- entry present → ONLY `models` updated, every other field byte-identical.

Plugin manifest / config_schema / DYNAMIC_ENUM_CACHE are never touched.

## Dashboard /models page

Menu entry right after Providers. Modeled on the /channels page (list rows,
inline add/edit/delete, save) but backed by GET/PUT `/api/models`. Includes an
Import flow (mirroring the plugins import): paste a models.yml-like URL,
per-provider `add` / `override` / `same` suggestions, Confirm & Execute merges
only the marked providers via the omniagent API. Import never deletes local
entries; deletion is a /models page action.
