/**
 * workstation HTTP facade + workbench-compat layer.
 *
 * WHAT THIS IS
 * ------------
 * `nexuslbs/deepseek-harness` (upstream third-party) is loaded with the
 * **workbench-plugins** package set. Those plugins were written against the
 * workbench core cordis API, which differs from the harness API in exactly two
 * places we bridge here:
 *
 *   1. TOOL REGISTRATION
 *        workbench : ctx.tools.registerTool({ name, description, parameters, handler })
 *                    parameters = map of { type, description?, required?, enum? }
 *        harness   : ctx.tools.register({ name, description, parameters, execute, output })
 *                    parameters = raw JSON Schema, `output.schema` + `output.render` REQUIRED
 *      -> registerTool() is (re)installed as a thin adapter that converts the
 *         workbench parameter map to JSON Schema and supplies a default
 *         `output` (any JSON + a text renderer). It also records the plugin
 *         handler so the HTTP facade can call it by name.
 *
 *   2. HTTP SURFACE
 *        workbench core served `/health` and `POST /api/tool/call`. The harness
 *        ships neither, so this plugin owns them (that is what makes the
 *        workstation service a drop-in stand-in for the workbench service:
 *        the omni `workbench` remote plugin speaks exactly this contract).
 *
 * Everything else (ctx.effect, service lookup via ctx.get / ctx.<svc>) is
 * already cordis-native and needs no shim.
 */

import { createServer } from 'node:http'
import { readFileSync, statSync } from 'node:fs'

export const name = 'workstation-http'

/** Cordis dependencies: the harness tool registry (required) + web (optional). */
export const inject = ['tools']

/** Global fallback map: tool name -> workbench-style handler. */
const handlers = new Map<string, (params: any) => any>()

/**
 * Parameter normalization: the harness author-facing parameter DSL IS the
 * workbench parameter map (an implicit parameter root keyed by property name,
 * with `type`/`description`/`required`). The only difference is that the
 * harness spells requiredness as `required: true` (presence-based), so a
 * `required: false` key is dropped here (and the map is cloned defensively).
 */
function normalizeParameters(parameters: any): any {
  if (!parameters || typeof parameters !== 'object' || Array.isArray(parameters)) return {}
  const out: Record<string, any> = {}
  for (const [key, raw] of Object.entries<any>(parameters)) {
    const p = raw && typeof raw === 'object' ? raw : {}
    const next: any = { ...p }
    if (next.required !== true) delete next.required
    out[key] = next
  }
  return out
}

/** Render any canonical value as a single text content block. */
function renderValue(_args: unknown, value: unknown): any[] {
  let text: string
  if (typeof value === 'string') text = value
  else if (value === undefined || value === null) text = ''
  else {
    try { text = JSON.stringify(value, null, 2) } catch { text = String(value) }
  }
  return [{ type: 'text', text }]
}

/** Convert one workbench tool definition into a harness ToolDefinition. */
function toHarnessDefinition(def: any) {
  return {
    name: def.name,
    description: def.description ?? '',
    parameters: normalizeParameters(def.parameters),
    execute: async (args: any) => def.handler(args ?? {}),
    output: {
      schema: {},
      render: renderValue,
    },
  }
}

/**
 * FILE-BACKED CREDENTIAL SOURCE (the product fix for the harness seam).
 *
 * On workbench, provider credentials are resolved by the `credentials-basic`
 * plugin's FILE backend, configured with `credentialsFile: /opt/omni/data/...`
 * (see config/workbench.yml). The harness bundle has no such plugin, so the
 * compat shim resolves credentials from the SAME operator-provided deployment
 * file - it must never invent a value.
 *
 * Search order (first existing file wins):
 *   1. $WORKSTATION_CREDENTIALS_FILE  (or $OMNI_CREDENTIALS_FILE)
 *   2. $OMNI_DIR/data/workbench/credentials.yml
 *   3. $OMNI_DIR/data/credentials/workbench/credentials.yml
 *   4. /opt/omni/data/workbench/credentials.yml
 *
 * Only the YAML subset the file actually uses is parsed (KEY: value,
 * quoted values, and `KEY: |` / `KEY: >` block scalars) - no dependency.
 */
let credentialFileCache: { path?: string; mtimeMs?: number; data: Record<string, string> } = { data: {} }

function credentialFilePaths(): string[] {
  const explicit = [process.env.WORKSTATION_CREDENTIALS_FILE, process.env.OMNI_CREDENTIALS_FILE].filter(
    (p): p is string => typeof p === 'string' && p.length > 0,
  )
  const candidates = [...explicit]
  const omni = process.env.OMNI_DIR
  if (omni) {
    candidates.push(`${omni}/data/workbench/credentials.yml`, `${omni}/data/credentials/workbench/credentials.yml`)
  }
  candidates.push('/opt/omni/data/workbench/credentials.yml')
  return candidates
}

function parseCredentialFile(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  let blockKey: string | null = null
  let block: string[] = []
  const flush = () => {
    if (blockKey) {
      out[blockKey] = block.join('\n').trim()
      blockKey = null
      block = []
    }
  }
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/\s+$/, '')
    if (blockKey !== null) {
      if (line.trim() === '' || /^\s+\S/.test(line)) {
        if (line.trim() !== '') block.push(line.trim())
        continue
      }
      flush()
    }
    if (line.trim() === '' || /^\s*#/.test(line)) continue
    const m = /^([A-Za-z0-9_.-]+)\s*:\s*(.*)$/.exec(line)
    if (!m) continue
    const key = m[1]
    const value = m[2].trim()
    if (value === '|' || value === '>' || value === '|-' || value === '>-' || value === '|+' || value === '>+') {
      blockKey = key
      continue
    }
    if (value === '') continue
    out[key] = value.replace(/^['"]/, '').replace(/['"]$/, '')
  }
  flush()
  return out
}

function credentialFileData(): Record<string, string> {
  for (const path of credentialFilePaths()) {
    try {
      const st = statSync(path)
      if (credentialFileCache.path === path && credentialFileCache.mtimeMs === st.mtimeMs) {
        return credentialFileCache.data
      }
      const data = parseCredentialFile(readFileSync(path, 'utf8'))
      credentialFileCache = { path, mtimeMs: st.mtimeMs, data }
      console.log('[workstation-http] credentials file=%s keys=%d', path, Object.keys(data).length)
      return data
    } catch {
      /* not readable here - try the next candidate */
    }
  }
  console.log('[workstation-http] credentials file=NONE (searched %d paths)', credentialFilePaths().length)
  return {}
}

function credentialFileValue(key: string): string | undefined {
  const data = credentialFileData()
  return Object.prototype.hasOwnProperty.call(data, key) ? data[key] : undefined
}

/** A minimal `credentials` service for the workbench core providers. */
function credentialsService(): any {
  const resolve = (ref: any): any => {
    const key = typeof ref === 'string' ? ref : (ref && (ref.name || ref.key || ref.id))
    if (!key) return undefined
    const fromEnv = process.env[key] ?? process.env[`OMNI_${key}`] ?? process.env[`WORKSTATION_${key}`]
    if (fromEnv !== undefined) return fromEnv
    const fromFile = credentialFileValue(key)
    if (fromFile !== undefined) return fromFile
    return undefined
  }
  return {
    resolve,
    get: resolve,
    has: (ref: any) => resolve(ref) !== undefined,
    list: () => [
      ...Object.keys(process.env).filter(k => /KEY|TOKEN|PASSWORD|SECRET|USER|ACCOUNT|SID/.test(k)),
      ...Object.keys(credentialFileData()),
    ],
  }
}

/** Read a whole request body as text. */
function readBody(req: any): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = ''
    req.on('data', (c: any) => { data += c })
    req.on('end', () => resolve(data))
    req.on('error', reject)
  })
}

function sendJson(res: any, status: number, payload: unknown) {
  const body = JSON.stringify(payload)
  if (typeof res.setHeader === 'function') res.setHeader('content-type', 'application/json')
  if (typeof res.writeHead === 'function') res.writeHead(status)
  res.end(body)
}

export function apply(ctx: any, config: any = {}) {
  const started = Date.now()

  // ── 1) workbench tool API shim ────────────────────────────────────────────
  const tools = (ctx.tools ?? (typeof ctx.get === 'function' ? ctx.get('tools') : undefined)) as any
  if (tools && typeof tools.register === 'function' && typeof tools.registerTool !== 'function') {
    tools.registerTool = (def: any) => {
      if (!def || typeof def.name !== 'string') throw new TypeError('registerTool: name is required')
      if (typeof def.handler === 'function') handlers.set(def.name, def.handler)
      else handlers.set(def.name, () => undefined)
      return tools.register(toHarnessDefinition(def))
    }
  } else if (!tools) {
    ctx.logger?.warn?.('workstation-http: no `tools` service available; tool shim skipped')
  }

  // LATE-APPLIER SHIM (the tricky case).
  // Plugins that call `ctx.tools.registerTool` INSIDE `ctx.effect(() => ...)`
  // (workbench-plugins sms-tools, totp-tools) resolve `tools` through a cordis
  // shadow/extended context that hands them a DIFFERENT facade object than the
  // one this plugin sees, so an instance/prototype patch is not enough.
  // We therefore (1) patch the instance, (2) patch its class prototype and
  // (3) as a last resort expose the shim on Object.prototype. The shim ignores
  // `this` and always forwards to the REAL registry captured in this closure.
  if (tools && typeof tools.register === 'function') {
    const registerToolShim = (def: any) => {
      if (def && def.name) handlers.set(def.name, def.handler ?? (() => undefined))
      return tools.register(toHarnessDefinition(def))
    }
    try {
      if (typeof tools.registerTool !== 'function') tools.registerTool = registerToolShim
    } catch (e) { console.log('[workstation-http] instance shim failed', e) }
    try {
      const proto = Object.getPrototypeOf(tools)
      if (proto && proto !== Object.prototype && typeof proto.registerTool !== 'function') {
        Object.defineProperty(proto, 'registerTool', {
          value: registerToolShim, writable: true, configurable: true,
        })
      }
    } catch (e) { console.log('[workstation-http] prototype shim failed', e) }
    try {
      Object.defineProperty(Object.prototype, 'registerTool', {
        value: registerToolShim, writable: true, configurable: true,
      })
      console.log('[workstation-http] DIAG registerTool shim installed on instance+prototype+Object.prototype')
    } catch (e) { console.log('[workstation-http] Object.prototype shim failed', e) }
  }

  // Late (re)appliers resolve `ctx.tools` through their own context fork; the
  // shim lives on the INSTANCE, so install it on the ToolRuntime PROTOTYPE too.
  // Without this, plugins whose `inject` only becomes ready after another
  // plugin publishes its service (sms-tools/totp-tools, waiting for the
  // capabilities-impl host) still die with
  // `TypeError: ctx.tools.registerTool is not a function`.
  try {
    const proto = tools ? Object.getPrototypeOf(tools) : undefined
    console.log(
      '[workstation-http] DIAG tools=%s hasRegisterTool=%s proto=%s protoRegisterTool=%s sameAsCtx=%s',
      typeof tools,
      tools ? typeof tools.registerTool : '-',
      proto ? Object.getOwnPropertyNames(proto).slice(0, 30).join(',') : '-',
      proto ? typeof proto.registerTool : '-',
      tools === ctx.tools,
    )
    if (tools && typeof tools.registerTool === 'function' && proto && proto !== Object.prototype) {
      Object.defineProperty(proto, 'registerTool', {
        value: tools.registerTool,
        writable: true,
        configurable: true,
      })
      console.log('[workstation-http] DIAG prototype registerTool installed')
    }
  } catch (diagErr) {
    console.log('[workstation-http] DIAG failed', diagErr)
  }

  // ── 1b) LATE CONTEXT DIAGNOSTIC (dev) ────────────────────────────────────
  // Plugins that apply LATE (after another plugin publishes a service) may see
  // a different `tools` object than the one patched above. Log what a late
  // injected context actually gets.
  try {
    ctx.inject?.(['tools', 'sms', 'totp'], (late: any) => {
      const t = late?.tools
      let protoNames = '-'
      try { protoNames = Object.getOwnPropertyNames(Object.getPrototypeOf(t)).join(',') } catch { /* ignore */ }
      let isProxy = '?'
      try { isProxy = String(require('node:util').types.isProxy(t)) } catch { /* ignore */ }
      console.log(
        '[workstation-http] DIAG-late same=%s typeof=%s isFn=%s isProxy=%s ownReg=%s protoReg=%s sms=%s totp=%s proto=%s',
        t === tools, typeof t, typeof t?.registerTool, isProxy,
        Object.prototype.hasOwnProperty.call(t ?? {}, 'registerTool'),
        (() => { try { return typeof Object.getPrototypeOf(t).registerTool } catch { return '-' } })(),
        typeof late?.sms, typeof late?.totp, protoNames.slice(0, 200),
      )
    })
  } catch (e) { console.log('[workstation-http] DIAG-late inject failed', e) }

  // ── 1c) COMPAT RE-APPLY (documented workbench<->harness API gap) ─────────
  // Some workbench plugins declare `inject: ['sms'|'totp', 'tools']` and stay
  // pending until the capability HOST publishes `sms`/`totp`. When cordis then
  // re-activates them, the context scope they receive does NOT hand them the
  // workbench `tools@1` entry point, so their apply() dies with
  //   TypeError: ctx.tools.registerTool is not a function
  // (observed for sms-tools + totp-tools; email-tools, which only injects
  // `tools`, applies early and works).
  // This adapter therefore re-applies those plugin MODULES - their own code,
  // unmodified, still loaded from the workbench-plugins source tree - inside
  // the boot scope with the shim registry. "Every capability comes from
  // plugins" stays true; only the cordis scope of the apply() call is ours.
  const applyPluginModule = async (label: string, file: string, deps: string[]) => {
    try {
      const mod: any = await import(file)
      const api = mod?.default ?? mod
      if (typeof api?.apply !== 'function') {
        console.log(`[workstation-http] compat-skip ${label}: no apply()`)
        return
      }
      const shim: any = {
        registerTool: (def: any) => (tools.registerTool ?? tools.register)(def),
        register: (def: any) => tools.register(def),
      }
      const fake: any = {
        tools: shim,
        effect: (cb: any) => {
          const d = cb()
          return typeof d === 'function' ? d : () => {}
        },
        on: () => () => {},
        logger: console,
        get: (n: string) => ctx.get?.(n),
      }
      for (const dep of [...(api.inject ?? []), ...deps]) {
        fake[dep] = ctx.get?.(dep) ?? ctx[dep]
      }
      fake.tools = shim // never let a dep overwrite the shim
      const res = api.apply(fake, {})
      if (res && typeof res.then === 'function') await res
      console.log(`[workstation-http] compat-applied ${label} (inject=[${(api.inject ?? []).join(',')}])`)
    } catch (e) {
      console.log(`[workstation-http] compat-apply ${label} FAILED`, e)
    }
  }
  const PLUGIN_ROOT = '/var/lib/workstation/sources/workbench-plugins'
  const reapplyCompat = async () => {
    await applyPluginModule('sms-tools', `${PLUGIN_ROOT}/plugins/sms-tools/index.ts`, ['sms'])
    await applyPluginModule('totp-tools', `${PLUGIN_ROOT}/plugins/totp-tools/index.ts`, ['totp'])
  }
  try {
    if (typeof ctx.inject === 'function') ctx.inject(['sms', 'totp', 'tools'], () => { void reapplyCompat() })
    else void reapplyCompat()
  } catch (e) {
    console.log('[workstation-http] compat re-apply injection failed', e)
  }

  // ── 2) credentials service (only when the harness does not provide one) ───
  // NOTE: the harness web profile ALREADY ships a real `credentials` service
  // (`@deepseek-ai/dsh-credentials-local`, registered by the base bundle).
  // Providing a stub here would win the race (this plugin is inserted first)
  // and shadow the real provider -> `service "credentials" has been
  // registered at <workstation-http>` + `credentials.readRecord is not a
  // function` for every harness plugin that needs it. So we NEVER provide it:
  // the adapter must stay a pure consumer of the harness services.
  //
  // BUT the harness provider LAYERS are not configured in the workstation
  // profile (the operator file backend lives in the workbench roster), so an
  // operator reference (`TOTP_HERMES_DISCOURSE`, `TWILIO_AUTH_TOKEN`, ...)
  // resolves to "no value" even though the adapter can read the very file that
  // holds it. We therefore AUGMENT the existing harness service instead of
  // registering a second one: a reference the harness cannot resolve falls back
  // to the operator credential file (WORKSTATION_CREDENTIALS_FILE /
  // OMNI_CREDENTIALS_FILE / $OMNI_DIR/data/workbench/credentials.yml).
  const installCredentialFileFallback = (): boolean => {
    try {
      const creds: any = ctx.get?.('credentials') ?? (ctx as any).credentials
      if (!creds || typeof creds.resolve !== 'function') return false
      if (creds.__workstationFileFallback === true) return true
      const original = creds.resolve.bind(creds)
      const keyOf = (ref: any): string | undefined => {
        if (typeof ref === 'string' && ref.length > 0) return ref
        if (ref && typeof ref === 'object') {
          for (const k of ['name', 'key', 'id', 'credential', 'ref', 'reference']) {
            const v = (ref as any)[k]
            if (typeof v === 'string' && v.length > 0) return v
          }
          try {
            const m = JSON.stringify(ref).match(/[A-Za-z][A-Z0-9_]{3,}/)
            if (m) return m[0]
          } catch {
            /* non-serialisable ref: no key */
          }
        }
        return undefined
      }
      Object.defineProperty(creds, '__workstationFileFallback', {
        value: true, enumerable: false, configurable: true, writable: true,
      })
      creds.resolve = async (ref: any, ...rest: any[]) => {
        let out: any
        try {
          out = await original(ref, ...rest)
        } catch {
          out = undefined
        }
        const value = out && typeof out === 'object' ? (out as any).value : out
        if (typeof value === 'string' && value.trim().length > 0) return out
        const key = keyOf(ref)
        const fallback = key === undefined ? undefined : credentialFileValue(key)
        if (fallback === undefined || fallback === '') return out
        console.log(`[workstation-http] credentials file fallback: ${key}`)
        return out && typeof out === 'object'
          ? { ...out, value: fallback, source: 'file' }
          : { value: fallback, source: 'file' }
      }
      console.log('[workstation-http] credentials file fallback installed')
      return true
    } catch (e) {
      console.log('[workstation-http] credentials file fallback failed', e)
      return false
    }
  }
  if (!installCredentialFileFallback()) {
    try {
      if (typeof ctx.inject === 'function') ctx.inject(['credentials'], () => { installCredentialFileFallback() })
    } catch (e) {
      console.log('[workstation-http] credentials fallback injection failed', e)
    }
    let tries = 0
    const timer = setInterval(() => {
      if (installCredentialFileFallback() || ++tries > 40) clearInterval(timer)
    }, 250)
    ;(timer as any).unref?.()
  }

  // ── 3) HTTP facade: /health + POST /api/tool/call ─────────────────────────
  const port = Number(process.env.WORKSTATION_PORT ?? config.port ?? 8080)
  const toolCallPath = String(config.tool_path ?? '/api/tool/call')

  const callTool = async (toolName: string, params: any) => {
    const handler = handlers.get(toolName)
    if (!handler) throw new Error(`unknown tool "${toolName}" (${handlers.size} registered)`)
    return await handler(params ?? {})
  }

  const server = createServer(async (req: any, res: any) => {
    try {
      const url = String(req.url ?? '/')
      if (req.method === 'GET' && (url === '/health' || url === '/healthz')) {
        return sendJson(res, 200, {
          status: 'ok',
          service: 'workstation',
          uptime_s: Math.round((Date.now() - started) / 1000),
          tools: handlers.size,
        })
      }
      if (url === '/api/tools' && req.method === 'GET') {
        return sendJson(res, 200, { status: 'ok', tools: [...handlers.keys()].sort() })
      }
      if (req.method === 'POST' && (url === toolCallPath || url === '/api/tool/call')) {
        const raw = await readBody(req)
        let body: any = {}
        try { body = raw ? JSON.parse(raw) : {} } catch { return sendJson(res, 400, { status: 'error', error: 'invalid JSON body' }) }
        const toolName = body.tool ?? body.name
        if (!toolName) return sendJson(res, 400, { status: 'error', error: 'missing "tool"' })
        try {
          const result = await callTool(toolName, body.params ?? body.arguments ?? {})
          return sendJson(res, 200, { status: 'ok', tool: toolName, result })
        } catch (err: any) {
          return sendJson(res, 200, { status: 'error', tool: toolName, error: err?.message ?? String(err) })
        }
      }
      return sendJson(res, 404, { status: 'error', error: 'not found' })
    } catch (err: any) {
      try { return sendJson(res, 500, { status: 'error', error: err?.message ?? String(err) }) } catch { return undefined }
    }
  })

  ctx.effect(() => {
    server.listen(port, '0.0.0.0', () => {
      ctx.logger?.info?.('workstation-http: facade listening on :%d (%d tool(s))', port, handlers.size)
    })
    return () => { try { server.close() } catch { /* ignore */ } }
  })
}

export default { name, inject, apply }
