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
 * This plugin is bookkeeping middleware, NOT an authorization layer, Key proxy,
 * OS sandbox, provider-usage authenticator or LiveGate. It controls one
 * candidate-selected logical model stream; it does not observe or bound the
 * provider library's internal HTTP/Files retries.
 */
import { createHash, randomBytes } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import type { Context } from '@deepseek-ai/cordis'
import { LlmError, type FinishReason, type GenerateOptions, type ResolvedRetryPolicy, type StreamChunk, type TokenUsage } from '@deepseek-ai/dsh-llm'

export const name = 'autoteacher-runtime-budget-guard'
export const inject = ['llm']

const MAX_BROKER_FRAME_BYTES = 16384
const MAX_COUNTER = 1_000_000_000
const MAX_SESSION_ID = 96
const MAX_STDERR_LINES = 64
const GUARD_VERSION = 'rbg-v1'
const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/
const HEX64 = /^[0-9a-f]{64}$/
const PURPOSES = ['conversation', 'compaction', 'judge'] as const
type Purpose = (typeof PURPOSES)[number]
const ALLOWED_BLOCKS = new Set(['text', 'reasoning', 'tool-call', 'tool-addition', 'tool-removal'])
const ALLOWED_ROLES = new Set(['system', 'user', 'assistant', 'developer', 'tool'])
const ALLOWED_TOOL = 'skill_lookup'

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
  maxProviderRetries: number
  purposes: Purpose[]
}

export interface GuardConfig {
  policy: GuardPolicyConfig
  broker: BrokerPolicyConfig
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
function type(value: unknown): string {
  if (value === null) return 'null'
  if (Array.isArray(value)) return 'array'
  return typeof value
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
  exactKeys(top, ['policy', 'broker'], 'config')
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
    maxProviderRetries: integer(policyRaw['maxProviderRetries'], 'config.policy.maxProviderRetries', 1),
    purposes,
  }
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
  return { config: { policy, broker }, fixed }
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
  positiveInt(config['max_messages'], 'broker policy.max_messages', 1_000_000)
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
  if (retry.mode === 'always' || retry.maxRetries > config.policy.maxProviderRetries) throw new GuardUnavailable('RBG_PROVIDER_RETRY_POLICY_UNSAFE')
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

/** Stable, bounded broker-safe task attribution from the session identity. */
function encodeTaskId(sessionId: string): string {
  const cleaned = sessionId.replace(/[^A-Za-z0-9_.:-]/g, '_').replace(/^[^A-Za-z0-9]+/, '')
  const payload = (cleaned || 'session').slice(0, MAX_SESSION_ID - 4)
  return `rbg-${payload}`
}

function requestDigest(options: GenerateOptions): string {
  const material = JSON.stringify({
    provider: options.provider, model: options.model,
    messages: options.messages, system: options.system ?? null,
    tools: options.tools ?? null, toolHistory: options.toolHistory ?? null,
    maxTokens: options.maxTokens ?? null, sessionId: options.sessionId ?? null,
    purpose: options.purpose ?? null, stop: options.stop ?? null,
  })
  return createHash('sha256').update(material).digest('hex')
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

/** Sequential NDJSON client for one fixed broker child process. */
class BrokerClient {
  #child: ChildProcessWithoutNullStreams | null = null
  #buffer = ''
  #stderrLines: string[] = []
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
      output_tokens: admission.outputBound, retry: false,
    }, !this.#started)
    if (reply.ok !== true || reply.dispatch_allowed !== true || reply.duplicate !== false || typeof reply.reservation_id !== 'string' || !ID.test(reply.reservation_id)) {
      throw new GuardUnavailable(`RBG_RESERVE_REJECTED_${reply.code}`)
    }
    const costUsd = typeof reply.reservation?.cost_usd === 'string' ? reply.reservation.cost_usd : 'unrecorded'
    log('RESERVE', {
      reservation_id: reply.reservation_id, task_id: admission.taskId, purpose: admission.purpose,
      input_bound: admission.inputBound, output_bound: admission.outputBound, reserved_cost_usd: costUsd,
      session_id: admission.sessionId, request_digest: admission.digest, provider: this.policy.provider, model: this.policy.model,
    })
    return { reservationId: reply.reservation_id, costUsd }
  }

  async settle(admission: Admission, reservationId: string, usage: TokenUsage | null, finish: FinishReason | undefined, failed: boolean): Promise<void> {
    const authoritative = !failed && usage !== null && finish !== undefined && (finish.kind === 'stop' || finish.kind === 'tool-calls' || finish.kind === 'max-tokens')
    const mapped = authoritative && usage !== null ? brokerUsage(usage) : null
    const op = mapped === null ? 'fail' : 'settle'
    const reply = await this.request({
      v: 1, id: requestIdentity('s'), op, reservation_id: reservationId,
      usage: mapped,
    }, false)
    if (reply.ok !== true || (reply.code !== 'SETTLED' && reply.code !== 'FAILED')) {
      throw new GuardUnavailable(`RBG_SETTLE_REJECTED_${reply.code}`)
    }
    log('SETTLE', {
      reservation_id: reservationId, operation: op, status: reply.settlement?.status ?? null,
      cost_usd: reply.settlement?.cost_usd ?? null, estimated: reply.settlement?.estimated ?? null,
      reservation_exceeded: reply.settlement?.reservation_exceeded ?? null,
      authoritative_usage: authoritative, unmapped_usage_worst_case: mapped === null,
    })
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
    } catch (error) {
      this.#fail(`RBG_BROKER_SPAWN_FAILED ${(error as Error).message}`)
      throw new GuardUnavailable(this.#unavailable ?? 'RBG_BROKER_SPAWN_FAILED')
    }
    this.#child = child
    child.stdout.setEncoding('utf8')
    child.stderr.setEncoding('utf8')
    child.stdout.on('data', (chunk: string) => this.#onStdout(chunk))
    child.stderr.on('data', (chunk: string) => {
      for (const line of chunk.split('\n')) {
        if (line.length > 0 && this.#stderrLines.length < MAX_STDERR_LINES) this.#stderrLines.push(line.slice(0, 512))
      }
    })
    child.on('error', (error: Error) => this.#fail(`RBG_BROKER_CHILD_ERROR ${error.message}`))
    child.on('exit', (code, signal) => {
      if (!this.#shuttingDown) this.#fail(`RBG_BROKER_EXITED code=${String(code)} signal=${String(signal)}`)
    })
  }

  #onStdout(chunk: string): void {
    this.#buffer += chunk
    for (;;) {
      const index = this.#buffer.indexOf('\n')
      if (index < 0) {
        if (Buffer.byteLength(this.#buffer, 'utf8') > MAX_BROKER_FRAME_BYTES) this.#fail('RBG_BROKER_FRAME_TOO_LARGE')
        return
      }
      const line = this.#buffer.slice(0, index)
      this.#buffer = this.#buffer.slice(index + 1)
      if (Buffer.byteLength(line, 'utf8') > MAX_BROKER_FRAME_BYTES) { this.#fail('RBG_BROKER_FRAME_TOO_LARGE'); return }
      if (line.length === 0) continue
      let reply: BrokerReply
      try {
        reply = JSON.parse(line) as BrokerReply
      } catch {
        this.#fail('RBG_BROKER_INVALID_JSON')
        return
      }
      if (typeof reply !== 'object' || reply === null || reply.v !== 1 || typeof reply.code !== 'string' || typeof reply.ok !== 'boolean') {
        this.#fail('RBG_BROKER_INVALID_ENVELOPE')
        return
      }
      const pending = this.#pending
      if (pending === null || reply.id !== pending.id) {
        this.#fail('RBG_BROKER_UNMATCHED_RESPONSE')
        return
      }
      this.#pending = null
      clearTimeout(pending.timer)
      if (!reply.ok) {
        pending.reject(new GuardUnavailable(`RBG_BROKER_REJECTED_${reply.code}`))
        if (reply.code === 'STARTUP_BLOCKED' || reply.code === 'ROUTE_BLOCKED' || reply.code === 'INTERNAL_ERROR') this.#fail(`RBG_BROKER_STARTUP_${reply.code}`)
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
        this.#fail('RBG_BROKER_TIMEOUT')
        reject(new GuardUnavailable('RBG_BROKER_TIMEOUT'))
      }, timeoutMs)
      this.#pending = { id, resolve, reject, timer }
      try {
        child.stdin.write(`${JSON.stringify(message)}\n`, error => {
          if (error) {
            const pending = this.#pending
            this.#pending = null
            if (pending !== null) { clearTimeout(pending.timer); pending.reject(new GuardUnavailable('RBG_BROKER_WRITE_FAILED')) }
            this.#fail('RBG_BROKER_WRITE_FAILED')
          }
        })
      } catch {
        const pending = this.#pending
        this.#pending = null
        if (pending !== null) { clearTimeout(pending.timer); pending.reject(new GuardUnavailable('RBG_BROKER_WRITE_FAILED')) }
        this.#fail('RBG_BROKER_WRITE_FAILED')
      }
    })
  }

  #rejectPending(error: Error): void {
    const pending = this.#pending
    this.#pending = null
    if (pending !== null) { clearTimeout(pending.timer); pending.reject(error) }
  }

  #fail(reason: string): void {
    if (this.#unavailable === null) this.#unavailable = reason
    this.#rejectPending(new GuardUnavailable(reason))
    const child = this.#child
    if (child !== null && child.exitCode === null && !this.#shuttingDown) {
      try { child.kill('SIGKILL') } catch { /* already gone */ }
    }
    if (this.#stderrLines.length > 0) {
      const stderr = this.#stderrLines.splice(0, this.#stderrLines.length)
      log('BROKER_DIAGNOSTICS', { reason, stderr_lines: stderr })
    }
    log('UNAVAILABLE', { reason, reservations_not_dispatched: true })
  }
}

let requestCounter = 0
function requestIdentity(kind: string): string {
  requestCounter += 1
  return `rbg-${kind}-${requestCounter}-${randomBytes(6).toString('hex')}`
}

export function apply(ctx: Context, rawConfig: unknown): void {
  let parsed: { config: GuardConfig; fixed: FixedBrokerPolicy }
  try {
    parsed = parseConfig(rawConfig)
  } catch (error) {
    const reason = error instanceof GuardUnavailable ? error.reason : String((error as Error).message)
    log('BOOT_INVALID', { reason, fail_closed: true })
    // Even a malformed guard configuration must fail closed: every stream is refused
    // before any provider dispatch. The upstream loader continues after a throwing
    // plugin, so a registered deny-all middleware is the safe behavior.
    ctx.on('llm/stream', async function* (): AsyncIterable<StreamChunk> {
      throw new GuardUnavailable(`RBG_GUARD_BOOT_INVALID ${reason}`)
    }, { prepend: true })
    return
  }
  const { config, fixed } = parsed
  const broker = new BrokerClient(config.broker, fixed, config.policy)
  ctx.effect(() => () => broker.shutdown(), 'runtime-budget-guard: broker child shutdown')
  log('BOOT', {
    provider: config.policy.provider, model: config.policy.model,
    broker_scope: fixed.scopeId, broker_db_path: fixed.dbPath,
    broker_policy_sha256: config.broker.configSha256, broker_python: config.broker.python,
    broker_config: config.broker.configPath, cwd: config.broker.cwd,
    max_input_bound: config.policy.maxInputTokens, max_output_bound: config.policy.maxOutputTokens,
    max_provider_retries: config.policy.maxProviderRetries, purposes: config.policy.purposes,
    task22_pending: 'stdio broker only; a live provider/full-budget bridge remains task22 follow-up',
  })

  ctx.on('llm/stream', async function* (options: GenerateOptions, next: () => AsyncIterable<StreamChunk>): AsyncIterable<StreamChunk> {
    const providers = ctx.llm.listProviders().map(provider => provider.id)
    const retryPolicy = ctx.llm.providerRetryPolicy(config.policy.provider)
    const admission = admit(options, config, providers, retryPolicy)
    let reservation: { reservationId: string; costUsd: string } | null = null
    let usage: TokenUsage | null = null
    let finish: FinishReason | undefined
    let failed = false
    try {
      reservation = await broker.reserve(admission)
      const stream = next()
      for await (const chunk of stream) {
        if (chunk.type === 'usage') usage = chunk.usage
        else if (chunk.type === 'finish') finish = chunk.reason
        yield chunk
      }
      const after = requestDigest(options)
      if (after !== admission.digest) {
        failed = true
        log('IMMUTABILITY_VIOLATION', { reservation_id: reservation.reservationId, before: admission.digest, after })
      }
    } catch (error) {
      failed = true
      if (reservation === null) log('STREAM_REFUSED', { reason: error instanceof GuardUnavailable ? error.reason : String((error as Error).message) })
      throw error
    } finally {
      if (reservation !== null) {
        try {
          await broker.settle(admission, reservation.reservationId, usage, finish, failed)
        } catch (error) {
          // Never retry settlement issuance: the reservation stays conservatively
          // pending and the guard fails closed for all later streams.
          const reason = error instanceof GuardUnavailable ? error.reason : String((error as Error).message)
          log('SETTLE_UNCERTAIN', { reservation_id: reservation.reservationId, reason })
          await broker.shutdown()
        }
      }
    }
  }, { prepend: true })
}
