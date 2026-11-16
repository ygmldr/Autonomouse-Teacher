/**
 * Runtime budget guard — logical-stream pre-dispatch reservation middleware.
 *
 * A real public Cordis plugin for the locked DSH 0.2.2-rc.2 runtime. It wraps
 * the global `llm/stream` waterfall (registered `prepend: true`) so that a
 * unique reservation is committed to the fixed-scope stdio bookkeeping broker
 * BEFORE `next()` is called or iterated: a denied/unavailable reservation never
 * enters a provider adapter. A `finally` block settles or fails each unique
 * reservation exactly once, with no settlement retry and no refund on missing
 * or ambiguous usage.
 *
 * v0.5 PR1 semantics (M0):
 *  - F1: provider-internal automatic retries are DISABLED for an admitted M0
 *    profile (`maxRetries` must be 0). Every logical stream is a new waterfall
 *    entry, so every logical stream counts as one request and one step slot in
 *    the persistent broker. The legacy `retry` boolean is attribution-only; it
 *    neither grants nor measures provider-internal retries.
 *  - F3: `requestDigest()` is POST-HOC audit only. A different digest after the
 *    stream is reported as REQUEST_INTEGRITY_UNCERTAIN: the current stream is
 *    settled at worst case and the call is failed, but this is NOT a pre-send
 *    interception and does not bound an already-dispatched provider request.
 *  - F4: model completion and accounting are separate statuses. Settlement
 *    uncertainty is machine-readable (`RBG_RESULT`), fails the call, and
 *    latches the guard fail-closed for all later dispatches.
 *  - F6: public stderr markers only carry allowlisted codes, numbers, booleans
 *    and hashed identifiers. Raw broker stderr is written only to a restricted
 *    diagnostic file when the launcher explicitly opts in.
 *
 * This plugin is bookkeeping middleware, NOT an authorization layer, Key proxy,
 * OS sandbox, provider-usage authenticator or LiveGate. It controls one
 * candidate-selected logical model stream; it does not observe or bound the
 * provider library's internal HTTP/Files retries.
 */
import { createHash, randomBytes } from 'node:crypto'
import { appendFileSync, readFileSync } from 'node:fs'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import type { Context } from '@deepseek-ai/cordis'
import { LlmError, type FinishReason, type GenerateOptions, type ResolvedRetryPolicy, type StreamChunk, type TokenUsage } from '@deepseek-ai/dsh-llm'

export const name = 'autoteacher-runtime-budget-guard'
export const inject = ['llm']

const MAX_BROKER_FRAME_BYTES = 16384
const MAX_COUNTER = 1_000_000_000
const MAX_STDERR_LINES = 64
const MAX_STDERR_BYTES = 65536
const GUARD_VERSION = 'rbg-v2'
/** F1: M0 disables provider-internal automatic retries. */
const PROVIDER_AUTO_RETRY_LIMIT = 0
const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/
const HEX64 = /^[0-9a-f]{64}$/
const SAFE_CODE = /^RBG_[A-Z0-9_]{1,80}$/
const PURPOSES = ['conversation', 'compaction', 'judge'] as const
type Purpose = (typeof PURPOSES)[number]
const ALLOWED_BLOCKS = new Set(['text', 'reasoning', 'tool-call', 'tool-addition', 'tool-removal'])
const ALLOWED_ROLES = new Set(['system', 'user', 'assistant', 'developer', 'tool'])
const ALLOWED_TOOL = 'skill_lookup'

/** F6: the only phases a failure log may report. */
type Phase = 'BEFORE_DISPATCH' | 'DISPATCHED' | 'SETTLING' | 'UNKNOWN'
/** F4: accounting status is independent from model completion status. */
type AccountingStatus = 'RESERVED' | 'SETTLED' | 'WORST_CASE_HELD' | 'SETTLEMENT_UNCERTAIN'
type ModelCompletionStatus = 'COMPLETED' | 'ERROR' | 'ABORTED' | 'BLOCKED' | 'UNKNOWN'

type Json = Record<string, unknown>

export interface BrokerPolicyConfig {
  /** Fixed absolute CPython interpreter; never assembled from client input. */
  python: string
  /** Fixed absolute Python module search path for the broker child. */
  pythonPath: string
  /** Fixed absolute, trusted read-only broker startup policy JSON path. */
  configPath: string
  /** Lowercase sha256 of the broker startup policy bytes. */
  configSha256: string
  /** Fixed absolute broker working directory. */
  cwd: string
  requestTimeoutMs: number
  startupTimeoutMs: number
}

export interface GuardPolicyConfig {
  provider: string
  model: string
  brokerScopeId: string
  maxOutputTokens: number
  maxInputTokens: number
  /** F1: must be 0 in M0; provider-internal retry is disabled. */
  maxProviderRetries: number
  purposes: Purpose[]
}

export type ReserveMode = 'reserve' | 'precheck'

export interface GuardConfig {
  policy: GuardPolicyConfig
  broker: BrokerPolicyConfig
  /** O-4 approved additive mode; default reserve preserves PR1 bytes. */
  reserveMode: ReserveMode
}

interface BrokerLimits {
  soft_usd: string
  hard_usd: string
  per_call_usd: string
  max_requests: number
  max_input_tokens: number
  max_output_tokens: number
  max_steps: number
  max_retries: number
}

/** Validated facts read from the trusted broker startup policy. */
interface FixedBrokerPolicy {
  scopeId: string
  dbPath: string
  limits: BrokerLimits
  routeId: string
  model: string
  usagePolicy: { cache_write: string; reasoning: string }
}

interface BrokerReply {
  v: number
  id: string | null
  ok: boolean
  code: string
  dispatch_allowed: boolean
  duplicate: boolean
  reservation_id?: string
  reservation?: { cost_usd?: string; input_tokens?: number; output_tokens?: number }
  settlement?: { cost_usd?: string; status?: string; estimated?: boolean; reservation_exceeded?: boolean }
}

interface Admission {
  readonly options: GenerateOptions
  readonly purpose: Purpose
  readonly sessionId: string
  readonly taskId: string
  readonly inputBound: number
  readonly outputBound: number
  readonly digest: string
}

class GuardUnavailable extends Error {
  constructor(readonly reason: string) {
    super(reason)
  }
}

function fail(message: string): never {
  throw new Error(`RBG_CONFIG_INVALID ${message}`)
}

function object(value: unknown, where: string): Json {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) fail(`${where} must be an object`)
  return value as Json
}

function exactKeys(value: Json, required: readonly string[], where: string): void {
  const keys = Object.keys(value).sort()
  const expected = [...required].sort()
  if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index])) {
    fail(`${where} must contain exactly ${expected.join(',')}`)
  }
}

function text(value: unknown, where: string, max: number): string {
  if (typeof value !== 'string' || value.length < 1 || value.length > max || [...value].some(char => char.charCodeAt(0) < 32)) fail(`${where} must be a bounded printable string`)
  return value
}

function absolutePath(value: unknown, where: string): string {
  const result = text(value, where, 1024)
  if (!result.startsWith('/') || result.includes('\0')) fail(`${where} must be an absolute path`)
  return result
}

function positiveInt(value: unknown, where: string, max: number): number {
  if (!Number.isSafeInteger(value) || (value as number) < 1 || (value as number) > max) fail(`${where} must be an integer in 1..${max}`)
  return value as number
}

function integer(value: unknown, where: string, max: number): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0 || (value as number) > max) fail(`${where} must be an integer in 0..${max}`)
  return value as number
}

function decimalString(value: unknown, where: string): string {
  const result = text(value, where, 40)
  if (!/^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,9})?$/.test(result)) fail(`${where} must be a plain nonnegative decimal string`)
  return result
}

function parseConfig(raw: unknown): { config: GuardConfig; fixed: FixedBrokerPolicy } {
  const top = object(raw, 'config')
  const topKeys = Object.keys(top).sort()
  if (topKeys.some(key => key !== 'policy' && key !== 'broker' && key !== 'reserveMode')
      || !Object.hasOwn(top, 'policy') || !Object.hasOwn(top, 'broker')) {
    fail('config must contain policy,broker and optional reserveMode')
  }
  const reserveModeRaw = top['reserveMode'] === undefined ? 'reserve' : top['reserveMode']
  if (reserveModeRaw !== 'reserve' && reserveModeRaw !== 'precheck') {
    fail('config.reserveMode must be "reserve" or "precheck"')
  }
  const reserveMode: ReserveMode = reserveModeRaw
  const policyRaw = object(top['policy'], 'config.policy')
  exactKeys(policyRaw, ['provider', 'model', 'brokerScopeId', 'maxOutputTokens', 'maxInputTokens', 'maxProviderRetries', 'purposes'], 'config.policy')
  const brokerRaw = object(top['broker'], 'config.broker')
  exactKeys(brokerRaw, ['python', 'pythonPath', 'configPath', 'configSha256', 'cwd', 'requestTimeoutMs', 'startupTimeoutMs'], 'config.broker')
  const provider = text(policyRaw['provider'], 'config.policy.provider', 96)
  if (!/^offline-test-only(?:-[A-Za-z0-9_.-]{1,64})?$/.test(provider)) fail('config.policy.provider must be an explicit offline-test-only route')
  const model = text(policyRaw['model'], 'config.policy.model', 96)
  if (!/^fixture-[A-Za-z0-9_.-]{1,64}$/.test(model)) fail('config.policy.model must be an explicit fixture-* model')
  const purposesRaw = policyRaw['purposes']
  if (!Array.isArray(purposesRaw) || purposesRaw.length < 1 || purposesRaw.length > PURPOSES.length) fail('config.policy.purposes must be a non-empty bounded list')
  const purposes = purposesRaw.map((entry, index) => {
    if (typeof entry !== 'string' || !PURPOSES.includes(entry as Purpose)) fail(`config.policy.purposes[${index}] is not a known purpose`)
    return entry as Purpose
  })
  if (new Set(purposes).size !== purposes.length) fail('config.policy.purposes contains duplicates')
  const policy: GuardPolicyConfig = {
    provider,
    model,
    brokerScopeId: text(policyRaw['brokerScopeId'], 'config.policy.brokerScopeId', 128),
    maxOutputTokens: positiveInt(policyRaw['maxOutputTokens'], 'config.policy.maxOutputTokens', 1024),
    maxInputTokens: positiveInt(policyRaw['maxInputTokens'], 'config.policy.maxInputTokens', 2_500_000),
    // F1: accept only the explicit M0 zero; a nonzero bound would imply
    // provider-internal retry aggregation this middleware cannot observe.
    maxProviderRetries: integer(policyRaw['maxProviderRetries'], 'config.policy.maxProviderRetries', PROVIDER_AUTO_RETRY_LIMIT),
    purposes,
  }
  if (policy.maxProviderRetries !== PROVIDER_AUTO_RETRY_LIMIT) fail('config.policy.maxProviderRetries must be 0 (provider auto retry disabled)')
  const broker: BrokerPolicyConfig = {
    python: absolutePath(brokerRaw['python'], 'config.broker.python'),
    pythonPath: text(brokerRaw['pythonPath'], 'config.broker.pythonPath', 1024),
    configPath: absolutePath(brokerRaw['configPath'], 'config.broker.configPath'),
    configSha256: text(brokerRaw['configSha256'], 'config.broker.configSha256', 64),
    cwd: absolutePath(brokerRaw['cwd'], 'config.broker.cwd'),
    requestTimeoutMs: positiveInt(brokerRaw['requestTimeoutMs'], 'config.broker.requestTimeoutMs', 10_000),
    startupTimeoutMs: positiveInt(brokerRaw['startupTimeoutMs'], 'config.broker.startupTimeoutMs', 15_000),
  }
  if (!HEX64.test(broker.configSha256)) fail('config.broker.configSha256 must be lowercase sha256')
  if (!broker.pythonPath.split(':').every(part => part.startsWith('/'))) fail('config.broker.pythonPath must be absolute colon-separated paths')
  const fixed = readFixedBrokerPolicy(broker.configPath, broker.configSha256, policy)
  return { config: { policy, broker, reserveMode }, fixed }
}

/** Read and validate the trusted broker startup policy file; it is never client text. */
function readFixedBrokerPolicy(path: string, expectedSha256: string, policy: GuardPolicyConfig): FixedBrokerPolicy {
  let bytes: Buffer
  try {
    bytes = readFileSync(path)
  } catch (error) {
    throw new Error(`RBG_CONFIG_INVALID broker policy unreadable: ${(error as Error).message}`)
  }
  const sha256 = createHash('sha256').update(bytes).digest('hex')
  if (sha256 !== expectedSha256) throw new GuardUnavailable('RBG_BROKER_POLICY_HASH_MISMATCH')
  let raw: unknown
  try {
    raw = JSON.parse(bytes.toString('utf8'))
  } catch {
    throw new Error('RBG_CONFIG_INVALID broker policy must be JSON')
  }
  const config = object(raw, 'broker policy')
  exactKeys(config, ['v', 'synthetic', 'db_path', 'scope_id', 'max_messages', 'limits', 'routes'], 'broker policy')
  if (config['v'] !== 1 || config['synthetic'] !== true) fail('broker policy must be synthetic v1')
  const scopeId = text(config['scope_id'], 'broker policy.scope_id', 128)
  if (scopeId !== policy.brokerScopeId) fail('broker policy scope_id differs from configured fixed scope')
  const dbPath = absolutePath(config['db_path'], 'broker policy.db_path')
  // F2: align the guard-visible upper bound with the broker's hard journal cap.
  positiveInt(config['max_messages'], 'broker policy.max_messages', 100_000)
  const limitsRaw = object(config['limits'], 'broker policy.limits')
  exactKeys(limitsRaw, ['soft_usd', 'hard_usd', 'per_call_usd', 'max_requests', 'max_input_tokens', 'max_output_tokens', 'max_steps', 'max_retries'], 'broker policy.limits')
  const limits: BrokerLimits = {
    soft_usd: decimalString(limitsRaw['soft_usd'], 'limits.soft_usd'),
    hard_usd: decimalString(limitsRaw['hard_usd'], 'limits.hard_usd'),
    per_call_usd: decimalString(limitsRaw['per_call_usd'], 'limits.per_call_usd'),
    max_requests: integer(limitsRaw['max_requests'], 'limits.max_requests', MAX_COUNTER),
    max_input_tokens: integer(limitsRaw['max_input_tokens'], 'limits.max_input_tokens', MAX_COUNTER),
    max_output_tokens: integer(limitsRaw['max_output_tokens'], 'limits.max_output_tokens', MAX_COUNTER),
    max_steps: integer(limitsRaw['max_steps'], 'limits.max_steps', MAX_COUNTER),
    max_retries: integer(limitsRaw['max_retries'], 'limits.max_retries', MAX_COUNTER),
  }
  const routes = config['routes']
  if (!Array.isArray(routes) || routes.length !== 1) fail('broker policy must contain exactly one fixture route')
  const route = object(routes[0], 'broker policy.routes[0]')
  exactKeys(route, ['route_id', 'model', 'price', 'known_extra_fee_usd', 'usage_policy'], 'broker policy.routes[0]')
  const routeId = text(route['route_id'], 'routes[0].route_id', 96)
  const model = text(route['model'], 'routes[0].model', 96)
  if (routeId !== policy.provider || model !== policy.model) fail('broker policy route/model differs from guard policy')
  const usage = object(route['usage_policy'], 'routes[0].usage_policy')
  exactKeys(usage, ['cache_write', 'reasoning'], 'routes[0].usage_policy')
  const cacheWrite = text(usage['cache_write'], 'usage_policy.cache_write', 40)
  const reasoning = text(usage['reasoning'], 'usage_policy.reasoning', 40)
  if (cacheWrite !== 'input_rate') fail('broker policy cache_write rule is not the reviewed input_rate rule')
  if (reasoning !== 'included_in_output' && reasoning !== 'additional_output') fail('broker policy reasoning rule is unknown')
  decimalString(route['known_extra_fee_usd'], 'routes[0].known_extra_fee_usd')
  const price = object(route['price'], 'routes[0].price')
  exactKeys(price, ['version', 'source', 'captured_at', 'input_per_million', 'cached_input_per_million', 'output_per_million'], 'routes[0].price')
  for (const key of ['input_per_million', 'cached_input_per_million', 'output_per_million']) {
    if (decimalString(price[key], `routes[0].price.${key}`) === '0') fail(`routes[0].price.${key} must be nonzero`)
  }
  return { scopeId, dbPath, limits, routeId, model, usagePolicy: { cache_write: cacheWrite, reasoning } }
}

/** Conservative complete-request input token upper bound: UTF-8 bytes plus fixed overhead. */
function estimateInputBound(options: GenerateOptions, config: GuardConfig): number {
  let bytes = Buffer.byteLength(options.system ?? '', 'utf8')
  for (const message of options.messages) {
    bytes += 64
    for (const blockValue of message.content) {
      const block = blockValue as { type?: unknown }
      const kind = typeof block.type === 'string' ? block.type : ''
      if (kind === 'text' || kind === 'reasoning') bytes += Buffer.byteLength((blockValue as { text: string }).text, 'utf8')
      else if (kind === 'tool-call') bytes += Buffer.byteLength(`${(blockValue as { name: string }).name} ${(blockValue as { arguments: string }).arguments} ${String((blockValue as { id: string }).id)}`, 'utf8')
      else if (kind === 'tool-addition' || kind === 'tool-removal') bytes += Buffer.byteLength((blockValue as { toolName: string }).toolName, 'utf8')
      else throw new GuardUnavailable('RBG_UNSUPPORTED_CONTENT')
    }
  }
  for (const tool of options.tools ?? []) bytes += Buffer.byteLength(JSON.stringify(tool), 'utf8') + 512
  if (options.toolHistory !== undefined) bytes += Buffer.byteLength(JSON.stringify(options.toolHistory), 'utf8') + 512
  bytes += Buffer.byteLength((options.stop ?? []).join('\n'), 'utf8')
  const bound = bytes + 256
  if (bound > config.policy.maxInputTokens) throw new GuardUnavailable('RBG_INPUT_BOUND_EXCEEDED')
  return bound
}

function admit(options: GenerateOptions, config: GuardConfig, registry: string[], retry: ResolvedRetryPolicy): Admission {
  if (registry.length !== 1 || registry[0] !== config.policy.provider) throw new GuardUnavailable('RBG_UNEXPECTED_PROVIDER_REGISTRY')
  // F1: any provider-internal retry (mode always or maxRetries > 0) is refused;
  // the M0 guard cannot observe or count retries hidden inside an adapter.
  if (retry.mode === 'always' || retry.maxRetries > PROVIDER_AUTO_RETRY_LIMIT) throw new GuardUnavailable('RBG_PROVIDER_RETRY_POLICY_UNSAFE')
  if (options.provider !== config.policy.provider) throw new GuardUnavailable('RBG_ROUTE_MISMATCH')
  if (options.model !== config.policy.model) throw new GuardUnavailable('RBG_MODEL_MISMATCH')
  if (typeof options.sessionId !== 'string' || options.sessionId.length < 1 || options.sessionId.length > 512) throw new GuardUnavailable('RBG_SESSION_ATTRIBUTION_MISSING')
  if (options.signal === undefined || !(options.signal instanceof AbortSignal)) throw new GuardUnavailable('RBG_CANCELLATION_SIGNAL_MISSING')
  if (options.signal.aborted) throw new GuardUnavailable('RBG_REQUEST_ALREADY_ABORTED')
  const purpose: Purpose = options.purpose === undefined ? 'conversation' : (options.purpose as Purpose)
  if (!config.policy.purposes.includes(purpose)) throw new GuardUnavailable('RBG_PURPOSE_NOT_ALLOWED')
  const outputBound = options.maxTokens
  if (!Number.isSafeInteger(outputBound) || (outputBound as number) < 1 || (outputBound as number) > config.policy.maxOutputTokens) throw new GuardUnavailable('RBG_OUTPUT_BOUND_INVALID')
  if (options.messages.length > 4096) throw new GuardUnavailable('RBG_TOO_MANY_MESSAGES')
  for (const message of options.messages) {
    if (!ALLOWED_ROLES.has(message.role)) throw new GuardUnavailable('RBG_UNKNOWN_ROLE')
    const source = message.source as { kind?: unknown; provider?: unknown; model?: unknown } | undefined
    if (source === undefined || typeof source.kind !== 'string') throw new GuardUnavailable('RBG_UNKNOWN_MESSAGE_SOURCE')
    if (message.role === 'assistant') {
      if (source.kind !== 'model' || source.provider !== config.policy.provider || source.model !== config.policy.model) throw new GuardUnavailable('RBG_ASSISTANT_ATTRIBUTION_MISMATCH')
    } else if (message.role === 'tool') {
      if (source.kind !== 'tool' || typeof (message as { toolCallId?: unknown }).toolCallId !== 'string') throw new GuardUnavailable('RBG_TOOL_RESULT_ATTRIBUTION_MISMATCH')
    }
    for (const blockValue of message.content) {
      const block = blockValue as { type?: unknown }
      const kind = typeof block.type === 'string' ? block.type : ''
      if (!ALLOWED_BLOCKS.has(kind)) throw new GuardUnavailable('RBG_UNSUPPORTED_CONTENT')
      if (kind === 'tool-call') {
        if ((blockValue as { name: string }).name !== ALLOWED_TOOL) throw new GuardUnavailable('RBG_UNKNOWN_TOOL_CALL')
        if (Buffer.byteLength((blockValue as { arguments: string }).arguments, 'utf8') > 4096) throw new GuardUnavailable('RBG_TOOL_ARGUMENTS_TOO_LARGE')
      }
      if ((kind === 'tool-addition' || kind === 'tool-removal') && (blockValue as { toolName: string }).toolName !== ALLOWED_TOOL) throw new GuardUnavailable('RBG_UNKNOWN_TOOL_DECLARATION')
    }
  }
  for (const toolValue of options.tools ?? []) {
    const tool = toolValue as { name?: unknown }
    if (tool.name !== ALLOWED_TOOL) throw new GuardUnavailable('RBG_UNKNOWN_TOOL_SCHEMA')
  }
  const inputBound = estimateInputBound(options, config)
  const sessionId = options.sessionId
  const taskId = encodeTaskId(sessionId)
  return { options, purpose, sessionId, taskId, inputBound, outputBound: outputBound as number, digest: requestDigest(options) }
}

function sha256Hex(value: string | Buffer): string {
  return createHash('sha256').update(value).digest('hex')
}

/** F5: stable injective task attribution: rbg- + sha256(canonical sessionId). */
function encodeTaskId(sessionId: string): string {
  const canonical = sessionId.normalize('NFC')
  return `rbg-${sha256Hex(canonical).slice(0, 64)}`
}

/** F6: public identifiers are only hashed IDs, never raw session/transport IDs. */
function hashId(value: string): string {
  return sha256Hex(value).slice(0, 32)
}

function requestDigest(options: GenerateOptions): string {
  const material = JSON.stringify({
    provider: options.provider, model: options.model,
    messages: options.messages, system: options.system ?? null,
    tools: options.tools ?? null, toolHistory: options.toolHistory ?? null,
    maxTokens: options.maxTokens ?? null, sessionId: options.sessionId ?? null,
    purpose: options.purpose ?? null, stop: options.stop ?? null,
  })
  return sha256Hex(material)
}

/** One broker usage projection; never invents counters. */
function brokerUsage(usage: TokenUsage): Json | null {
  const numbers: Record<string, number | null> = {
    inputTokens: usage.inputTokens, outputTokens: usage.outputTokens,
    cacheReadTokens: usage.cacheReadTokens ?? null, cacheWriteTokens: usage.cacheWriteTokens ?? null,
    reasoningTokens: usage.reasoningTokens ?? null, totalTokens: usage.totalTokens ?? null,
  }
  for (const value of Object.values(numbers)) {
    if (value !== null && (!Number.isSafeInteger(value) || value < 0 || value > MAX_COUNTER)) return null
  }
  return { ...numbers, actual_cost_usd: null }
}

function log(kind: string, payload: Json): void {
  process.stderr.write(`RBG_${kind} ${JSON.stringify({ guard: GUARD_VERSION, ...payload }, (_key, value: unknown) => typeof value === 'bigint' ? Number(value) : value)}\n`)
}

/** F6: only fixed RBG_* codes may reach public logs. */
function safeErrorCode(error: unknown): string {
  if (error instanceof GuardUnavailable && SAFE_CODE.test(error.reason.split(' ')[0] ?? '')) return error.reason.split(' ')[0] as string
  const message = error instanceof Error ? error.message : ''
  const match = /^RBG_[A-Z0-9_]{1,80}/.exec(message)
  return match === null ? 'RBG_STREAM_ERROR' : match[0]
}

/** F6: broker reply codes are allowlisted; unknown codes are replaced. */
const BROKER_REPLY_CODES = new Set([
  'RESERVED', 'SETTLED', 'FAILED', 'SNAPSHOT', 'DUPLICATE_NO_DISPATCH',
  'MESSAGE_LIMIT', 'BUDGET_EXCEEDED', 'ROUTE_BLOCKED', 'UNKNOWN_RESERVATION',
  'ALREADY_SETTLED', 'INVALID_USAGE', 'INVALID_MESSAGE', 'FRAME_TOO_LARGE',
  'INCOMPLETE_FRAME', 'IDEMPOTENCY_CONFLICT', 'INTERNAL_ERROR', 'STARTUP_BLOCKED',
])
function safeBrokerCode(code: unknown): string {
  return typeof code === 'string' && BROKER_REPLY_CODES.has(code) ? code : 'UNKNOWN'
}

/** F6: raw broker stderr only goes to an explicitly configured restricted file. */
function storeRawDiagnostics(code: string, lines: readonly string[]): Json {
  const path = process.env['RBG_RAW_DIAGNOSTICS_PATH']
  const joined = lines.join('\n')
  const summary: Json = { count: lines.length, bytes: Buffer.byteLength(joined, 'utf8'), sha256: sha256Hex(joined) }
  if (path === undefined || path.length === 0 || path.length > 1024 || !path.startsWith('/')) return summary
  try {
    appendFileSync(path, `${lines.join('\n')}\n`, { encoding: 'utf8', mode: 0o600 })
    summary['restricted_file'] = true
    summary['restricted_file_hash'] = hashId(path)
  } catch {
    summary['restricted_file'] = false
  }
  return summary
}

/** Sequential NDJSON client for one fixed broker child process. */
class BrokerClient {
  #child: ChildProcessWithoutNullStreams | null = null
  #buffer = ''
  #stderrLines: string[] = []
  #stderrBytes = 0
  #pending: {
    id: string
    resolve: (reply: BrokerReply) => void
    reject: (error: Error) => void
    timer: NodeJS.Timeout
  } | null = null
  #tail: Promise<void> = Promise.resolve()
  #started = false
  #shuttingDown = false
  #unavailable: string | null = null
  #phase: Phase = 'BEFORE_DISPATCH'
  #settling = false
  #dispatchedCount = 0
  #activeReservation: string | null = null

  constructor(
    private readonly config: BrokerPolicyConfig,
    private readonly fixed: FixedBrokerPolicy,
    private readonly policy: GuardPolicyConfig,
  ) {}

  /** Send one request; requests are serialized so one broker line is in flight. */
  request(message: Json, startup: boolean): Promise<BrokerReply> {
    const run = async (): Promise<BrokerReply> => {
      if (this.#unavailable !== null) throw new GuardUnavailable(this.#unavailable)
      this.#ensureStarted()
      return this.#send(message, startup ? this.config.startupTimeoutMs : this.config.requestTimeoutMs)
    }
    const result = this.#tail.then(run, run)
    this.#tail = result.then(() => undefined, () => undefined)
    return result
  }

  async reserve(admission: Admission): Promise<{ reservationId: string; costUsd: string }> {
    const requestId = requestIdentity('r')
    const reply = await this.request({
      v: 1, id: requestId, op: 'reserve', task_id: admission.taskId,
      route_id: this.policy.provider, model: this.policy.model,
      purpose: admission.purpose, input_tokens: admission.inputBound,
      output_tokens: admission.outputBound,
      // F1: attribution-only legacy field; provider-internal retry is disabled
      // and every logical stream already consumes one request/step slot.
      retry: false,
    }, !this.#started)
    if (reply.ok !== true || reply.dispatch_allowed !== true || reply.duplicate !== false || typeof reply.reservation_id !== 'string' || !ID.test(reply.reservation_id)) {
      throw new GuardUnavailable(`RBG_RESERVE_REJECTED_${safeBrokerCode(reply.code)}`)
    }
    const costUsd = typeof reply.reservation?.cost_usd === 'string' ? reply.reservation.cost_usd : 'unrecorded'
    this.#activeReservation = reply.reservation_id
    this.#dispatchedCount += 1
    this.#phase = 'DISPATCHED'
    log('RESERVE', {
      reservation_id_hash: hashId(reply.reservation_id), task_id: admission.taskId,
      task_steps_charged: 1, retry_field: 'attribution-only',
      purpose: admission.purpose, input_bound: admission.inputBound, output_bound: admission.outputBound,
      reserved_cost_usd: costUsd, session_id_hash: hashId(admission.sessionId),
      request_digest: admission.digest, provider: this.policy.provider, model: this.policy.model,
    })
    return { reservationId: reply.reservation_id, costUsd }
  }

  /** F4: settle returns a machine-readable accounting status; uncertainty throws. */
  async settle(admission: Admission, reservationId: string, usage: TokenUsage | null, finish: FinishReason | undefined, failed: boolean): Promise<{ accountingStatus: AccountingStatus; costUsd: string | null; estimated: boolean | null }> {
    const authoritative = !failed && usage !== null && finish !== undefined && (finish.kind === 'stop' || finish.kind === 'tool-calls' || finish.kind === 'max-tokens')
    const mapped = authoritative && usage !== null ? brokerUsage(usage) : null
    const op = mapped === null ? 'fail' : 'settle'
    this.#settling = true
    this.#phase = 'SETTLING'
    try {
      const reply = await this.request({
        v: 1, id: requestIdentity('s'), op, reservation_id: reservationId,
        usage: mapped,
      }, false)
      if (reply.ok !== true || (reply.code !== 'SETTLED' && reply.code !== 'FAILED')) {
        this.#fail('RBG_SETTLE_UNCERTAIN', 'SETTLING')
        throw new GuardUnavailable('RBG_SETTLE_UNCERTAIN')
      }
      const accountingStatus: AccountingStatus = op === 'settle' ? 'SETTLED' : 'WORST_CASE_HELD'
      log('SETTLE', {
        reservation_id_hash: hashId(reservationId), operation: op, accounting_status: accountingStatus,
        settlement_status: typeof reply.settlement?.status === 'string' ? reply.settlement.status : null,
        cost_usd: typeof reply.settlement?.cost_usd === 'string' ? reply.settlement.cost_usd : null,
        estimated: typeof reply.settlement?.estimated === 'boolean' ? reply.settlement.estimated : null,
        reservation_exceeded: typeof reply.settlement?.reservation_exceeded === 'boolean' ? reply.settlement.reservation_exceeded : null,
        authoritative_usage: authoritative, unmapped_usage_worst_case: mapped === null,
      })
      return {
        accountingStatus,
        costUsd: typeof reply.settlement?.cost_usd === 'string' ? reply.settlement.cost_usd : null,
        estimated: typeof reply.settlement?.estimated === 'boolean' ? reply.settlement.estimated : null,
      }
    } catch (error) {
      if (!(error instanceof GuardUnavailable && error.reason === 'RBG_SETTLE_UNCERTAIN')) {
        this.#fail('RBG_SETTLE_UNCERTAIN', 'SETTLING')
      }
      // Never retry settlement: an unknown acknowledgement leaves the broker
      // PENDING reservation untouched and latches later dispatches off.
      throw new GuardUnavailable('RBG_SETTLE_UNCERTAIN')
    } finally {
      this.#settling = false
      if (this.#unavailable === null) {
        this.#activeReservation = null
        this.#phase = 'BEFORE_DISPATCH'
      }
    }
  }

  /** F4: explicit fail-closed latch after an uncertain settlement. */
  latchSettlementUncertain(): void {
    this.#fail('RBG_SETTLE_UNCERTAIN', 'SETTLING')
  }

  async shutdown(): Promise<void> {
    this.#shuttingDown = true
    this.#rejectPending(new GuardUnavailable('RBG_BROKER_DISPOSED'))
    const child = this.#child
    if (child === null) return
    if (child.exitCode !== null || child.signalCode !== null) return
    await new Promise<void>(resolve => {
      const timer = setTimeout(() => {
        if (child.exitCode === null) child.kill('SIGKILL')
        resolve()
      }, 1500)
      child.once('exit', () => { clearTimeout(timer); resolve() })
      try { child.stdin.end() } catch { /* already closed */ }
    })
  }

  #currentPhase(): Phase {
    if (this.#settling) return 'SETTLING'
    if (this.#activeReservation !== null || this.#phase === 'DISPATCHED') return 'DISPATCHED'
    if (this.#started && this.#dispatchedCount > 0) return 'UNKNOWN'
    return 'BEFORE_DISPATCH'
  }

  #ensureStarted(): void {
    if (this.#started) return
    if (this.#unavailable !== null) throw new GuardUnavailable(this.#unavailable)
    this.#started = true
    const env = {
      PATH: '/opt/python/bin:/usr/bin',
      HOME: '/work',
      PYTHONPATH: this.config.pythonPath,
      PYTHONDONTWRITEBYTECODE: '1',
      TMPDIR: '/tmp',
    }
    let child: ChildProcessWithoutNullStreams
    try {
      child = spawn(this.config.python, ['-B', '-m', 'autoteacher_m0.accounting.broker', '--config', this.config.configPath], {
        cwd: this.config.cwd, env, shell: false, stdio: ['pipe', 'pipe', 'pipe'],
      })
    } catch {
      this.#fail('RBG_BROKER_SPAWN_FAILED', 'BEFORE_DISPATCH')
      throw new GuardUnavailable(this.#unavailable ?? 'RBG_BROKER_SPAWN_FAILED')
    }
    this.#child = child
    child.stdout.setEncoding('utf8')
    child.stderr.setEncoding('utf8')
    child.stdout.on('data', (chunk: string) => this.#onStdout(chunk))
    child.stderr.on('data', (chunk: string) => {
      for (const line of chunk.split('\n')) {
        if (line.length === 0) continue
        this.#stderrBytes += Buffer.byteLength(line, 'utf8')
        if (this.#stderrLines.length < MAX_STDERR_LINES && this.#stderrBytes <= MAX_STDERR_BYTES) this.#stderrLines.push(line.slice(0, 512))
      }
    })
    child.on('error', () => this.#fail('RBG_BROKER_CHILD_ERROR', this.#currentPhase()))
    child.on('exit', (code, signal) => {
      if (!this.#shuttingDown) this.#fail('RBG_BROKER_EXITED', this.#currentPhase(), {
        exit_code: typeof code === 'number' ? code : null, signaled: signal !== null,
      })
    })
  }

  #onStdout(chunk: string): void {
    this.#buffer += chunk
    for (;;) {
      const index = this.#buffer.indexOf('\n')
      if (index < 0) {
        if (Buffer.byteLength(this.#buffer, 'utf8') > MAX_BROKER_FRAME_BYTES) this.#fail('RBG_BROKER_FRAME_TOO_LARGE', this.#currentPhase())
        return
      }
      const line = this.#buffer.slice(0, index)
      this.#buffer = this.#buffer.slice(index + 1)
      if (Buffer.byteLength(line, 'utf8') > MAX_BROKER_FRAME_BYTES) { this.#fail('RBG_BROKER_FRAME_TOO_LARGE', this.#currentPhase()); return }
      if (line.length === 0) continue
      let reply: BrokerReply
      try {
        reply = JSON.parse(line) as BrokerReply
      } catch {
        this.#fail('RBG_BROKER_INVALID_JSON', this.#currentPhase())
        return
      }
      if (typeof reply !== 'object' || reply === null || reply.v !== 1 || typeof reply.code !== 'string' || typeof reply.ok !== 'boolean') {
        this.#fail('RBG_BROKER_INVALID_ENVELOPE', this.#currentPhase())
        return
      }
      const pending = this.#pending
      if (pending === null || reply.id !== pending.id) {
        this.#fail('RBG_BROKER_UNMATCHED_RESPONSE', this.#currentPhase())
        return
      }
      this.#pending = null
      clearTimeout(pending.timer)
      if (!reply.ok) {
        pending.reject(new GuardUnavailable(`RBG_BROKER_REJECTED_${safeBrokerCode(reply.code)}`))
        if (reply.code === 'STARTUP_BLOCKED' || reply.code === 'ROUTE_BLOCKED' || reply.code === 'INTERNAL_ERROR') this.#fail(`RBG_BROKER_STARTUP_${safeBrokerCode(reply.code)}`, this.#currentPhase())
      } else {
        pending.resolve(reply)
      }
    }
  }

  #send(message: Json, timeoutMs: number): Promise<BrokerReply> {
    const child = this.#child
    if (child === null || this.#unavailable !== null) return Promise.reject(new GuardUnavailable(this.#unavailable ?? 'RBG_BROKER_NOT_STARTED'))
    const id = text(message['id'], 'broker request id', 96)
    return new Promise<BrokerReply>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.#pending = null
        this.#fail('RBG_BROKER_TIMEOUT', this.#currentPhase())
        reject(new GuardUnavailable('RBG_BROKER_TIMEOUT'))
      }, timeoutMs)
      this.#pending = { id, resolve, reject, timer }
      try {
        child.stdin.write(`${JSON.stringify(message)}\n`, error => {
          if (error) {
            const pending = this.#pending
            this.#pending = null
            if (pending !== null) { clearTimeout(pending.timer); pending.reject(new GuardUnavailable('RBG_BROKER_WRITE_FAILED')) }
            this.#fail('RBG_BROKER_WRITE_FAILED', this.#currentPhase())
          }
        })
      } catch {
        const pending = this.#pending
        this.#pending = null
        if (pending !== null) { clearTimeout(pending.timer); pending.reject(new GuardUnavailable('RBG_BROKER_WRITE_FAILED')) }
        this.#fail('RBG_BROKER_WRITE_FAILED', this.#currentPhase())
      }
    })
  }

  #rejectPending(error: Error): void {
    const pending = this.#pending
    this.#pending = null
    if (pending !== null) { clearTimeout(pending.timer); pending.reject(error) }
  }

  #fail(code: string, phase: Phase, extra: Json = {}): void {
    if (this.#unavailable !== null) { this.#rejectPending(new GuardUnavailable(this.#unavailable)); return }
    const safeCode = SAFE_CODE.test(code) ? code : 'RBG_BROKER_UNAVAILABLE'
    this.#unavailable = safeCode
    this.#rejectPending(new GuardUnavailable(safeCode))
    const child = this.#child
    if (child !== null && child.exitCode === null && !this.#shuttingDown) {
      try { child.kill('SIGKILL') } catch { /* already gone */ }
    }
    const stderr = this.#stderrLines.splice(0, this.#stderrLines.length)
    this.#stderrBytes = 0
    const diagnostics = storeRawDiagnostics(safeCode, stderr)
    log('UNAVAILABLE', {
      code: safeCode,
      phase,
      latch: true,
      dispatched: this.#dispatchedCount > 0,
      dispatched_count: this.#dispatchedCount,
      reservation_pending: this.#activeReservation !== null,
      reservation_id_hash: this.#activeReservation === null ? null : hashId(this.#activeReservation),
      stderr: diagnostics,
      ...extra,
    })
  }
}

let requestCounter = 0
function requestIdentity(kind: string): string {
  requestCounter += 1
  return `rbg-${kind}-${requestCounter}-${randomBytes(6).toString('hex')}`
}

function mapFinishReason(finish: FinishReason | undefined): ModelCompletionStatus {
  const kind = finish === undefined ? 'unknown' : String((finish as { kind?: unknown }).kind ?? 'unknown')
  if (kind === 'stop' || kind === 'tool-calls' || kind === 'max-tokens') return 'COMPLETED'
  if (kind === 'aborted') return 'ABORTED'
  if (kind === 'error') return 'ERROR'
  if (kind === 'blocked') return 'BLOCKED'
  return 'UNKNOWN'
}

function mapStreamError(error: unknown): ModelCompletionStatus {
  if (error instanceof Error && (error.name === 'AbortError' || /abort/i.test(error.message))) return 'ABORTED'
  return 'ERROR'
}

export function apply(ctx: Context, rawConfig: unknown): void {
  let parsed: { config: GuardConfig; fixed: FixedBrokerPolicy }
  try {
    parsed = parseConfig(rawConfig)
  } catch (error) {
    const code = safeErrorCode(error)
    log('BOOT_INVALID', { code, fail_closed: true })
    // Even a malformed guard configuration must fail closed: every stream is refused
    // before any provider dispatch. The upstream loader continues after a throwing
    // plugin, so a registered deny-all middleware is the safe behavior.
    ctx.on('llm/stream', async function* (): AsyncIterable<StreamChunk> {
      throw new GuardUnavailable('RBG_GUARD_BOOT_INVALID')
    }, { prepend: true })
    return
  }
  const { config, fixed } = parsed
  const precheck = config.reserveMode === 'precheck'
  const broker = precheck ? null : new BrokerClient(config.broker, fixed, config.policy)
  if (broker !== null) {
    const reserveBroker = broker
    ctx.effect(() => () => reserveBroker.shutdown(), 'runtime-budget-guard: broker child shutdown')
  }
  const bootBase = {
    provider: config.policy.provider, model: config.policy.model,
    broker_scope: fixed.scopeId,
    broker_policy_sha256: config.broker.configSha256,
    broker_python_hash: hashId(config.broker.python),
    broker_config_hash: hashId(config.broker.configPath),
    cwd_hash: hashId(config.broker.cwd),
    max_input_bound: config.policy.maxInputTokens, max_output_bound: config.policy.maxOutputTokens,
    max_provider_retries: config.policy.maxProviderRetries,
    provider_auto_retry: 'disabled',
    logical_stream_slots: 'every stream = one request + one step',
    retry_field_semantics: 'attribution-only; no provider-internal retry quota',
    task_id_scheme: 'rbg-' + 'sha256(NFC sessionId)[0:64]',
    public_log_contract: 'allowlisted codes/numbers/booleans/hashed IDs only',
    purposes: config.policy.purposes,
  }
  if (precheck) {
    log('BOOT', {
      provider: config.policy.provider, model: config.policy.model,
      broker_scope: fixed.scopeId,
      broker_db_path_hash: hashId(fixed.dbPath),
      broker_policy_sha256: config.broker.configSha256,
      broker_python_hash: hashId(config.broker.python),
      broker_config_hash: hashId(config.broker.configPath),
      cwd_hash: hashId(config.broker.cwd),
      max_input_bound: config.policy.maxInputTokens, max_output_bound: config.policy.maxOutputTokens,
      max_provider_retries: config.policy.maxProviderRetries,
      provider_auto_retry: 'disabled',
      logical_stream_slots: 'every stream = one request + one step',
      retry_field_semantics: 'attribution-only; no provider-internal retry quota',
      task_id_scheme: 'rbg-' + 'sha256(NFC sessionId)[0:64]',
      public_log_contract: 'allowlisted codes/numbers/booleans/hashed IDs only',
      purposes: config.policy.purposes,
      reserve_mode: 'precheck',
      broker_child: 'disabled',
    })
    ctx.on('llm/stream', async function* (options: GenerateOptions, next: () => AsyncIterable<StreamChunk>): AsyncIterable<StreamChunk> {
      const providers = ctx.llm.listProviders().map(provider => provider.id)
      const retryPolicy = ctx.llm.providerRetryPolicy(config.policy.provider)
      let admission: Admission
      try {
        admission = admit(options, config, providers, retryPolicy)
      } catch (error) {
        log('STREAM_REFUSED', { phase: 'BEFORE_DISPATCH', code: safeErrorCode(error), reserve_mode: 'precheck' })
        throw error
      }
      log('PRECHECK', {
        session_id_hash: hashId(admission.sessionId), task_id: admission.taskId,
        provider: config.policy.provider, model: config.policy.model,
        input_bound: admission.inputBound, output_bound: admission.outputBound,
        purpose: admission.purpose, reserve_mode: 'precheck',
        broker_child: 'disabled',
      })
      try {
        yield* next()
      } finally {
        log('ACCOUNTING_DELEGATED_TO_CONTROLLER', {
          session_id_hash: hashId(admission.sessionId), task_id: admission.taskId,
          reserve_mode: 'precheck', guard_reserved: false, guard_settled: false,
          authority: 'controller-broker',
        })
      }
    }, { prepend: true })
    return
  }
  const reserveBroker = broker as BrokerClient
  log('BOOT', {
    provider: config.policy.provider, model: config.policy.model,
    broker_scope: fixed.scopeId,
    broker_db_path_hash: hashId(fixed.dbPath),
    broker_policy_sha256: config.broker.configSha256,
    broker_python_hash: hashId(config.broker.python),
    broker_config_hash: hashId(config.broker.configPath),
    cwd_hash: hashId(config.broker.cwd),
    max_input_bound: config.policy.maxInputTokens, max_output_bound: config.policy.maxOutputTokens,
    max_provider_retries: config.policy.maxProviderRetries,
    provider_auto_retry: 'disabled',
    logical_stream_slots: 'every stream = one request + one step',
    retry_field_semantics: 'attribution-only; no provider-internal retry quota',
    task_id_scheme: 'rbg-' + 'sha256(NFC sessionId)[0:64]',
    public_log_contract: 'allowlisted codes/numbers/booleans/hashed IDs only',
    purposes: config.policy.purposes,
  })

  ctx.on('llm/stream', async function* (options: GenerateOptions, next: () => AsyncIterable<StreamChunk>): AsyncIterable<StreamChunk> {
    const providers = ctx.llm.listProviders().map(provider => provider.id)
    const retryPolicy = ctx.llm.providerRetryPolicy(config.policy.provider)
    const admission = admit(options, config, providers, retryPolicy)
    let reservation: { reservationId: string; costUsd: string } | null = null
    let usage: TokenUsage | null = null
    let finish: FinishReason | undefined
    let failed = false
    let integrityUncertain = false
    let modelCompletionStatus: ModelCompletionStatus = 'UNKNOWN'
    let accountingStatus: AccountingStatus = 'RESERVED'
    let settlementError: Error | null = null
    try {
      reservation = await reserveBroker.reserve(admission)
      const stream = next()
      for await (const chunk of stream) {
        if (chunk.type === 'usage') usage = chunk.usage
        else if (chunk.type === 'finish') {
          finish = chunk.reason
          if (modelCompletionStatus === 'UNKNOWN') modelCompletionStatus = mapFinishReason(chunk.reason)
        }
        yield chunk
      }
      const after = requestDigest(options)
      if (after !== admission.digest) {
        // F3: post-hoc detection only. This is NOT a pre-send interception and
        // it cannot bound a request that the downstream provider already sent.
        failed = true
        integrityUncertain = true
        log('REQUEST_INTEGRITY_UNCERTAIN', {
          reservation_id_hash: hashId(reservation.reservationId),
          before_digest: admission.digest, after_digest: after,
          interception: 'post-hoc-only',
          accounting_status_after_settle: 'WORST_CASE_HELD',
        })
      }
    } catch (error) {
      failed = true
      modelCompletionStatus = mapStreamError(error)
      // F3: re-check the digest even when the downstream throws early (for
      // example a mutated provider route is rejected by the runtime). This is
      // still post-hoc classification; it never claims a pre-send interception.
      const afterCatch = requestDigest(options)
      if (afterCatch !== admission.digest) {
        integrityUncertain = true
        log('REQUEST_INTEGRITY_UNCERTAIN', {
          reservation_id_hash: reservation === null ? null : hashId(reservation.reservationId),
          before_digest: admission.digest, after_digest: afterCatch,
          interception: 'post-hoc-only',
          accounting_status_after_settle: 'WORST_CASE_HELD',
        })
      }
      if (reservation === null) log('STREAM_REFUSED', { phase: 'BEFORE_DISPATCH', code: safeErrorCode(error) })
      throw error
    } finally {
      if (reservation !== null) {
        try {
          const result = await reserveBroker.settle(admission, reservation.reservationId, usage, finish, failed)
          accountingStatus = result.accountingStatus
        } catch {
          accountingStatus = 'SETTLEMENT_UNCERTAIN'
          reserveBroker.latchSettlementUncertain()
          settlementError = new GuardUnavailable('RBG_SETTLEMENT_UNCERTAIN')
        }
      }
      log('RESULT', {
        v: 1,
        model_completion_status: modelCompletionStatus,
        accounting_status: accountingStatus,
        dispatched: reservation !== null,
        reservation_id_hash: reservation === null ? null : hashId(reservation.reservationId),
        session_id_hash: hashId(admission.sessionId),
        task_id: admission.taskId,
        integrity_uncertain: integrityUncertain,
        settlement_uncertain: accountingStatus === 'SETTLEMENT_UNCERTAIN',
        retry_field: 'attribution-only',
      })
      if (settlementError !== null) throw settlementError
      if (integrityUncertain) throw new GuardUnavailable('RBG_REQUEST_INTEGRITY_UNCERTAIN')
    }
  }, { prepend: true })
}

/** Test-only helpers: committed targeted tests import these; not runtime API. */
export const __test = {
  encodeTaskId,
  hashId,
  requestDigest,
  safeErrorCode,
}
