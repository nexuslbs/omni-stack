# Python Telegram Platform Plugin (Implementation)

**Status:** Planned
**Date:** 2026-08-16
**Scope:** omni-plugins (new python telegram platform plugin), omni-deployer (integration tests), omni-stack (config/channels wiring)

## Goal

Develop a **Python telegram platform plugin** for omniagent in the
**omni-plugins** repo. It must implement the omniagent platform plugin
protocol (JSON-lines over stdio) and work with the Telegram Bot API —
outbound (send/edit/delete messages) and inbound (polling for updates). It
must be implemented properly and verified as far as possible **WITHOUT a real
Telegram bot token** (mock-based testing), so integration tests can be created
too.

## Why (verified)

- omniagent ships a `plugins/platforms/telegram/plugin.json` entry pointing at
  `./target/release/telegram-platform`, but there is **NO source code** — it
  is an unimplemented stub (no crate, no .rs/.py anywhere in the repo). A
  working telegram platform is genuinely missing.
- External platforms are supported by the core:
  `src/platform/external/mod.rs` loads platform plugins (name, capabilities
  inbound/outbound, command, stdio transport).
- The platform protocol is demonstrated by
  `omni-plugins/platforms/test-python/platform.py`: JSON-lines over
  stdin/stdout, methods `initialize`, `configure`, `deliver`,
  `edit_message`, `delete_message`, `react`; outbound-only capability. The
  built-in mattermost platform (`omniagent/plugins/platforms/mattermost`)
  shows a full-featured platform with setup capability and inbound.
- Telegram Bot API: outbound = `sendMessage` / `editMessageText` /
  `deleteMessage`; inbound = long-polling `getUpdates` (offset-based) or
  webhook; auth via a bot token from @BotFather.

## Token / testing strategy (user rules — IMPORTANT)

- **NEVER use the hermes telegram bot token** — it belongs to Hermes, not
  omniagent. Do not reuse it, reference it, or test against it.
- **Prefer testing WITHOUT a real token**: implement a mock Telegram Bot API
  (a small HTTP server implementing `getUpdates`/`sendMessage`/
  `editMessageText`/`deleteMessage` with in-memory state) and test the
  platform end-to-end against the mock. This is the goal — it enables
  integration tests without real credentials.
- If a real token is genuinely required for final verification: **SKIP the
  real test**, document exactly what is needed for a real full test (create a
  fresh bot via @BotFather, the token env/secret name, the channel
  registration steps), and the operator will generate a NEW token/bot for
  omniagent. Never reuse hermes' bot.

## Design (executor picks cleanest implementation)

### 1. omni-plugins/platforms/telegram/ — new Python platform

- `plugin.json`: type=platform, capabilities inbound+outbound,
  config_schema: `bot_token` (secret, required), `polling_enabled`
  (boolean, default true), `poll_interval_secs`, `api_base_url`
  (default https://api.telegram.org — overridable for the mock!).
- `platform.py` implementing the protocol:
  - `initialize` → report name `telegram` + capabilities.
  - `configure` → store token + settings (api_base_url override is what
    makes mock testing possible without touching real API).
  - `deliver` → `POST sendMessage` to `chat_id` (the channel's
    resource_identifier = telegram chat id).
  - `edit_message` / `delete_message` → `editMessageText` / `deleteMessage`.
  - inbound: long-poll `getUpdates` loop (offset tracking, timeout, error
    backoff), delivering inbound messages to the agent the same way the
    mattermost platform does (investigate how inbound events are posted back
    — via the agent's HTTP API; the mattermost platform is the reference).
- Keep dependencies minimal (stdlib + requests/urllib); if deps are needed,
  declare `requirements.txt` (the install API supports it).

### 2. Live verification (omnidev, NO real token)

- Run a mock Telegram API server (small python http.server implementing the
  endpoints with in-memory messages).
- Configure the platform with `api_base_url` → mock. Verify outbound
  deliver/edit/delete hit the mock with the correct payloads; simulate
  inbound updates and verify they flow to the agent correctly.

### 3. Tester: integration tests

- omni-deployer `scripts/tests.py`, new group (G33 — G31 is boards, G32 is
  reference MCPs): boot the platform against the mock, assert outbound
  deliver/edit/delete payloads + correct inbound handling, with
  correct-return assertions.

## Acceptance criteria

1. Python telegram platform plugin in omni-plugins, protocol-correct
   (initialize/configure/deliver/edit_message/delete_message + inbound
   polling).
2. Works against a MOCK Telegram API with correct payloads/returns — no real
   token used anywhere.
3. Integration tests (G33) cover outbound + inbound against the mock; all
   gates green (cargo fmt/check/clippy if touched, tests.py G33).
4. If real-token testing was skipped: clear documentation of exactly what a
   real full test needs (fresh @BotFather bot for omniagent — NOT hermes'
   token).
5. omnidev-only; omnistable frozen (no migrations/rebuilds/restarts).

## Notes for the executor

- Do NOT use hermes' telegram bot token; do NOT test against the real
  Telegram API with any existing token.
- The built-in telegram stub (omniagent/plugins/platforms/telegram/
  plugin.json) has no source — you are implementing the real thing; do not
  modify that stub (or if a wiring change is truly needed, keep it minimal
  and documented).
- Reference `omni-plugins/platforms/test-python/` for the protocol shape and
  the mattermost platform for inbound behavior.
- Dev loop per `dev-development.md`: live temp DB, SQLX_OFFLINE=false;
  SQLX_OFFLINE=true is CI-only. omnistable frozen.
- Git identity for nexuslbs repos: `Hermes Agent` / `hermes@nexuslbs.org`.
