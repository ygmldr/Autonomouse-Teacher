/**
 * G3-A experimental provider bridge.
 *
 * This is a PUBLIC Cordis provider extension (`LlmAdapter`) for the locked DSH
 * 0.2.2-rc.2 runtime. It does not implement a model: it forwards one fully
 * assembled provider-neutral request over a real OS pipe to an independent
 * Python "fake provider" process, validates the frames that process returns,
 * and yields the canonical `StreamChunk` sequence back to DSH.
 *
 * Evidence scope: synthetic fixture only. No API key, no HTTP, no network, no
 * real model. This plugin is not a production adapter and grants no Live
 * permission.
 */
import { createHash, randomUUID } from 'node:crypto'
import { appendFileSync, mkdirSync } from 'node:fs'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { createInterface } from 'node:readline'
import { dirname, join } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import { LlmAdapter, LlmError, ToolCallId } from '@deepseek-ai/dsh-llm'
import type {
  ContentBlock,
  FinishReason,
  GenerateOptions,
  ResolvedRetryPolicy,
  StreamChunk,
  TokenUsage,
} from '@deepseek-ai/dsh-llm'

export const name = 'autoteacher-g3a-provider-bridge'
export const inject = ['llm']
export const provider = 'g3a-bridge-test'
export const model = 'bridge-v1'

const ENV_OPT_IN = 'AUTOTEACHER_G3A_BRIDGE'
const FIXED_PYTHON = '/opt/python/bin/python3.11'
const MAX_STDERR_LINES = 64
const MAX_STDERR_BYTES = 16_384
const DEFAULT_TIMEOUT_MS = 15_000
const ALLOWED_BLOCKS = new Set(['text', 'reasoning', 'tool-call', 'tool-addition', 'tool-removal'])
const ALLOWED_ROLES = new Set(['system', 'user', 'assistant', 'developer', 'tool'])
const ALLOWED_TOOL = 'skill_lookup'

type Json = Record<string, unknown>
type BridgeMode = 'echo' | 'recall' | 'tool' | 'tool-final' | 'eof' | 'error' | 'slow'
type AbortKind = 'aborted' | 'timeout' | null

interface BridgeConfig {
  readonly python: string
  readonly fake: string
  readonly traceDir: string
  readonly receiptDir: string
  readonly timeoutMs: number
}

function record(value: unknown): value is Json {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

function sha256(value: string): string {
  return createHash('sha256').update(value, 'utf8').digest('hex')
}

function fail(message: string, code: 'INVALID_REQUEST' | 'SERVER' | 'INVALID_RESPONSE' | 'STREAM_CLOSED'): never {
  throw new LlmError(message, code)
}

function requireEnv(key: string): string {
  const value = process.env[key]
  if (!value) throw new Error(`G3A_BRIDGE_MISSING_ENV:${key}`)
  return value
}

/** Read only fixed, absolute container paths. No caller-supplied filesystem input reaches the child. */
function readConfig(): BridgeConfig {
  if (process.env[ENV_OPT_IN] !== '1') throw new Error('G3A_BRIDGE_EXPLICIT_OPT_IN_REQUIRED')
  const python = requireEnv('G3A_BRIDGE_PYTHON')
  const fake = requireEnv('G3A_BRIDGE_FAKE')
  const traceDir = requireEnv('G3A_BRIDGE_TRACE_DIR')
  const receiptDir = requireEnv('G3A_BRIDGE_RECEIPT_DIR')
  if (python !== FIXED_PYTHON) throw new Error('G3A_BRIDGE_PYTHON_MUST_BE_FIXED_INTERPRETER')
  if (!fake.startsWith('/probe/') || !fake.endsWith('.py') || fake.includes('..')) throw new Error('G3A_BRIDGE_FAKE_PATH_MUST_BE_FIXED_READONLY')
  for (const [label, dir] of [['TRACE', traceDir], ['RECEIPT', receiptDir]] as const) {
    if (!dir.startsWith('/work/g3a/') || dir.includes('..')) throw new Error(`G3A_BRIDGE_${label}_DIR_MUST_BE_WORK_G3A`)
  }
  const timeoutMs = Number(process.env['G3A_BRIDGE_TIMEOUT_MS'] ?? String(DEFAULT_TIMEOUT_MS))
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1000 || timeoutMs > 60_000) throw new Error('G3A_BRIDGE_TIMEOUT_INVALID')
  return { python, fake, traceDir, receiptDir, timeoutMs }
}

function trace(path: string, event: string, data: Json = {}): void {
  appendFileSync(path, `${JSON.stringify({ ts: new Date().toISOString(), event, ...data })}\n`, 'utf8')
}

function userTexts(options: GenerateOptions): string[] {
  return options.messages
    .filter(message => message.role === 'user' && 'source' in message && message.source?.kind === 'user')
    .map(message => message.content.filter(block => block.type === 'text').map(block => block.text).join(''))
}

/** Validate the complete assembled request at the public `llm/stream` boundary. */
function checkRequest(options: GenerateOptions): string[] {
  if (options.provider !== provider || options.model !== model || options.purpose !== undefined) {
    fail('G3A_BRIDGE_ROUTE_ONLY', 'INVALID_REQUEST')
  }
  if (!options.sessionId || !options.signal
    || !Number.isSafeInteger(options.maxTokens) || options.maxTokens! < 1 || options.maxTokens! > 1024) {
    fail('G3A_BRIDGE_BOUNDED_SESSION_REQUIRED', 'INVALID_REQUEST')
  }
  for (const message of options.messages) {
    if (!ALLOWED_ROLES.has(message.role)) fail('G3A_BRIDGE_ROLE_UNSUPPORTED', 'INVALID_REQUEST')
    for (const block of message.content) {
      if (!ALLOWED_BLOCKS.has(block.type)) fail('G3A_BRIDGE_CONTENT_UNSUPPORTED', 'INVALID_REQUEST')
      if (block.type === 'tool-call' && block.name !== ALLOWED_TOOL) fail('G3A_BRIDGE_TOOL_ONLY', 'INVALID_REQUEST')
      if ((block.type === 'tool-addition' || block.type === 'tool-removal') && block.toolName !== ALLOWED_TOOL) {
        fail('G3A_BRIDGE_TOOL_ONLY', 'INVALID_REQUEST')
      }
    }
  }
  if ((options.tools ?? []).some(tool => tool.name !== ALLOWED_TOOL)) fail('G3A_BRIDGE_TOOL_ONLY', 'INVALID_REQUEST')
  return userTexts(options)
}

function selectMode(options: GenerateOptions, texts: string[]): BridgeMode {
  const last = texts.at(-1) ?? ''
  if (last.startsWith('G3A_RECALL')) return 'recall'
  if (last.startsWith('G3A_TOOL')) {
    return options.messages.some(message => message.role === 'tool') ? 'tool-final' : 'tool'
  }
  if (last.startsWith('G3A_EOF')) return 'eof'
  if (last.startsWith('G3A_ERROR')) return 'error'
  if (last.startsWith('G3A_CANCEL')) return 'slow'
  return 'echo'
}

function requireIndex(value: unknown): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0) fail('G3A_BRIDGE_CHUNK_INDEX_INVALID', 'INVALID_RESPONSE')
  return value as number
}

function requireUsage(value: unknown): TokenUsage {
  if (!record(value)) fail('G3A_BRIDGE_USAGE_INVALID', 'INVALID_RESPONSE')
  const keys = ['inputTokens', 'outputTokens'] as const
  const optional = ['totalTokens', 'cacheReadTokens', 'cacheWriteTokens', 'reasoningTokens'] as const
  for (const key of keys) {
    if (!Number.isSafeInteger(value[key]) || (value[key] as number) < 0) fail('G3A_BRIDGE_USAGE_INVALID', 'INVALID_RESPONSE')
  }
  for (const key of optional) {
    if (value[key] !== undefined && (!Number.isSafeInteger(value[key]) || (value[key] as number) < 0)) {
      fail('G3A_BRIDGE_USAGE_INVALID', 'INVALID_RESPONSE')
    }
  }
  return {
    inputTokens: value['inputTokens'] as number,
    outputTokens: value['outputTokens'] as number,
    ...value['totalTokens'] === undefined ? {} : { totalTokens: value['totalTokens'] as number },
    ...value['cacheReadTokens'] === undefined ? {} : { cacheReadTokens: value['cacheReadTokens'] as number },
    ...value['cacheWriteTokens'] === undefined ? {} : { cacheWriteTokens: value['cacheWriteTokens'] as number },
    ...value['reasoningTokens'] === undefined ? {} : { reasoningTokens: value['reasoningTokens'] as number },
  }
}

function requireFinishReason(value: unknown): FinishReason {
  if (!record(value) || typeof value.kind !== 'string') fail('G3A_BRIDGE_FINISH_INVALID', 'INVALID_RESPONSE')
  if (value.kind === 'stop' || value.kind === 'tool-calls' || value.kind === 'max-tokens') {
    return { kind: value.kind }
  }
  if (value.kind === 'aborted' || value.kind === 'error') {
    const failure = value.failure
    if (!record(failure) || !nonEmptyString(failure.message) || !nonEmptyString(failure.code)) {
      fail('G3A_BRIDGE_FINISH_FAILURE_INVALID', 'INVALID_RESPONSE')
    }
    return { kind: value.kind, failure: { message: failure.message, code: failure.code } }
  }
  fail('G3A_BRIDGE_FINISH_KIND_UNKNOWN', 'INVALID_RESPONSE')
}

/** Reconstruct only the canonical public chunk vocabulary; never forward arbitrary child JSON. */
function normalizeChunk(value: unknown): StreamChunk {
  if (!record(value) || typeof value.type !== 'string') fail('G3A_BRIDGE_CHUNK_INVALID', 'INVALID_RESPONSE')
  switch (value.type) {
    case 'block-start': {
      if (!nonEmptyString(value.blockType)) fail('G3A_BRIDGE_BLOCK_INVALID', 'INVALID_RESPONSE')
      return { type: 'block-start', index: requireIndex(value.index), blockType: value.blockType as ContentBlock['type'] }
    }
    case 'text-delta':
    case 'reasoning-delta': {
      if (typeof value.text !== 'string') fail('G3A_BRIDGE_DELTA_INVALID', 'INVALID_RESPONSE')
      return { type: value.type, index: requireIndex(value.index), text: value.text }
    }
    case 'tool-call-delta': {
      if (!nonEmptyString(value.id) || typeof value.argumentsDelta !== 'string' || !nonEmptyString(value.name)) {
        fail('G3A_BRIDGE_TOOL_DELTA_INVALID', 'INVALID_RESPONSE')
      }
      return {
        type: 'tool-call-delta',
        index: requireIndex(value.index),
        id: ToolCallId(value.id),
        name: value.name,
        argumentsDelta: value.argumentsDelta,
      }
    }
    case 'block-end': {
      if (!record(value.block) || typeof value.block.type !== 'string') fail('G3A_BRIDGE_BLOCK_INVALID', 'INVALID_RESPONSE')
      return { type: 'block-end', index: requireIndex(value.index), block: value.block as unknown as ContentBlock }
    }
    case 'usage':
      return { type: 'usage', usage: requireUsage(value.usage) }
    case 'finish':
      return { type: 'finish', reason: requireFinishReason(value.reason) }
    default:
      fail('G3A_BRIDGE_CHUNK_TYPE_UNKNOWN', 'INVALID_RESPONSE')
  }
}

function childEnv(receiptPath: string, eventsPath: string): Record<string, string> {
  return {
    PATH: '/usr/bin',
    HOME: '/work',
    TMPDIR: '/tmp',
    PYTHONDONTWRITEBYTECODE: '1',
    G3A_FAKE_RECEIPT: receiptPath,
    G3A_FAKE_EVENTS: eventsPath,
  }
}

function exited(child: ChildProcessWithoutNullStreams): boolean {
  return child.exitCode !== null || child.signalCode !== null
}

function waitExit(child: ChildProcessWithoutNullStreams, timeoutMs: number): Promise<boolean> {
  if (exited(child)) return Promise.resolve(true)
  return new Promise(resolve => {
    const timer = setTimeout(() => { child.removeListener('exit', onExit); resolve(false) }, timeoutMs)
    const onExit = (): void => { clearTimeout(timer); resolve(true) }
    child.once('exit', onExit)
  })
}

class BridgeAbort extends Error {}

/** One public LlmAdapter registration that owns the `g3a-bridge-test` route. */
export class BridgeAdapter extends LlmAdapter {
  readonly #config: BridgeConfig
  #invocations = 0

  constructor(config: BridgeConfig) {
    super()
    this.#config = config
  }

  override providerRetryPolicy(): ResolvedRetryPolicy {
    return { mode: 'normal', maxRetries: 0, retryableCodes: [], initialDelayMs: 1, maxDelayMs: 1, jitterRatio: 0 }
  }

  override async resolveModel(route: string, id: string) {
    if (route !== provider || id !== model) fail('G3A_BRIDGE_ROUTE_ONLY', 'INVALID_REQUEST')
    return {
      provider,
      id: model,
      name: 'G3-A external stdio bridge fixture, NOT a model',
      context: { contextWindow: 16384 },
      defaultMaxTokens: 256,
      maxTokens: 1024,
      inputModalities: ['text' as const],
    }
  }

  override async *stream(options: GenerateOptions): AsyncGenerator<StreamChunk> {
    const signal = options.signal!
    signal.throwIfAborted()
    const texts = checkRequest(options)
    const ordinal = ++this.#invocations
    const requestId = randomUUID()
    const mode = selectMode(options, texts)
    const tracePath = join(this.#config.traceDir, `bridge-${requestId}.jsonl`)
    const receiptPath = join(this.#config.receiptDir, `fake-${requestId}.json`)
    const eventsPath = join(this.#config.receiptDir, `fake-${requestId}.jsonl`)
    mkdirSync(dirname(tracePath), { recursive: true })
    mkdirSync(this.#config.receiptDir, { recursive: true })

    const wire = {
      v: 1,
      type: 'request',
      requestId,
      ordinal,
      provider,
      model,
      sessionId: options.sessionId,
      purpose: options.purpose ?? null,
      maxTokens: options.maxTokens,
      mode,
      messages: options.messages,
      tools: options.tools ?? [],
      system: options.system ?? null,
      receiptPath,
      eventsPath,
    }
    const rawLine = `${JSON.stringify(wire)}\n`
    const requestSha256 = sha256(rawLine)
    trace(tracePath, 'request', {
      requestId,
      ordinal,
      mode,
      sessionId: options.sessionId,
      provider,
      model,
      maxTokens: options.maxTokens,
      messageCount: options.messages.length,
      roles: options.messages.map(message => message.role),
      toolNames: (options.tools ?? []).map(tool => tool.name),
      userTexts: texts,
      realModelCalls: 0,
      httpCalls: 0,
      requestSha256,
      synthetic: true,
    })

    const child = spawn(this.#config.python, ['-B', this.#config.fake], {
      cwd: '/work',
      env: childEnv(receiptPath, eventsPath),
      shell: false,
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    const stderrLines: string[] = []
    let stderrBytes = 0
    let spawnError: Error | null = null
    child.on('error', error => { spawnError = error })
    child.stderr.setEncoding('utf8')
    child.stderr.on('data', (chunk: string) => {
      stderrBytes += Buffer.byteLength(chunk, 'utf8')
      for (const line of chunk.split('\n')) {
        if (line.length === 0) continue
        if (stderrLines.length < MAX_STDERR_LINES && stderrBytes <= MAX_STDERR_BYTES) stderrLines.push(line.slice(0, 512))
      }
    })
    trace(tracePath, 'spawn', {
      requestId,
      argv: [this.#config.python, '-B', this.#config.fake],
      cwd: '/work',
      childPid: child.pid ?? null,
      transport: 'stdio:pipe:ndjson',
      synthetic: true,
    })
    try {
      await new Promise<void>((resolve, reject) => {
        const onSpawn = (): void => { child.off('error', onError); resolve() }
        const onError = (error: Error): void => { child.off('spawn', onSpawn); reject(error) }
        child.once('spawn', onSpawn)
        child.once('error', onError)
      })
    } catch (error) {
      trace(tracePath, 'spawn-failed', { requestId, message: error instanceof Error ? error.message : String(error) })
      throw new LlmError('G3A_BRIDGE_SPAWN_FAILED', 'SERVER', { cause: error })
    }
    process.stderr.write(`G3A_BRIDGE_READY ${JSON.stringify({
      requestId, childPid: child.pid, mode, sessionId: options.sessionId, provider, model, synthetic: true,
    })}\n`)

    const rl = createInterface({ input: child.stdout, crlfDelay: Infinity })
    const frames = rl[Symbol.asyncIterator]()
    let abortKind: AbortKind = null
    let rejectAbort: ((reason?: unknown) => void) | null = null
    const abortPromise = new Promise<never>((_resolve, reject) => { rejectAbort = reject })
    const onAbort = (): void => {
      if (abortKind !== null) return
      abortKind = 'aborted'
      trace(tracePath, 'abort-signal', { requestId, phase: 'streaming' })
      rejectAbort?.(new BridgeAbort('aborted'))
      try { child.stdin.write(`${JSON.stringify({ v: 1, type: 'cancel', requestId })}\n`) } catch { /* closed */ }
      setTimeout(() => { if (!exited(child)) child.kill('SIGTERM') }, 200)
      setTimeout(() => { if (!exited(child)) child.kill('SIGKILL') }, 800)
    }
    signal.addEventListener('abort', onAbort, { once: true })
    const timeout = setTimeout(() => {
      if (abortKind !== null) return
      abortKind = 'timeout'
      trace(tracePath, 'timeout', { requestId, timeoutMs: this.#config.timeoutMs })
      rejectAbort?.(new BridgeAbort('timeout'))
      child.kill('SIGKILL')
    }, this.#config.timeoutMs)

    let finish: StreamChunk | null = null
    let sawDone = false
    let chunkSeq = 0
    try {
      child.stdin.write(rawLine)
      while (true) {
        const pending = frames.next()
        // If abort wins the race, this iterator promise may still settle later.
        pending.catch(() => {})
        let step: IteratorResult<string>
        try {
          step = await Promise.race([pending, abortPromise])
        } catch (error) {
          if (abortKind === 'aborted') throw new LlmError('G3A_BRIDGE_ABORTED_BY_DSH_SIGNAL', 'ABORTED', { cause: error })
          if (abortKind === 'timeout') throw new LlmError('G3A_BRIDGE_CHILD_TIMEOUT', 'TIMEOUT', { cause: error })
          throw error
        }
        if (step.done) break
        const line = step.value.trim()
        if (line.length === 0) continue
        let frame: unknown
        try {
          frame = JSON.parse(line)
        } catch {
          fail('G3A_BRIDGE_CHILD_INVALID_JSON', 'INVALID_RESPONSE')
        }
        if (!record(frame) || frame['v'] !== 1 || frame['requestId'] !== requestId || typeof frame['type'] !== 'string') {
          fail('G3A_BRIDGE_CHILD_FRAME_INVALID', 'INVALID_RESPONSE')
        }
        switch (frame['type']) {
          case 'ack':
            trace(tracePath, 'ack', {
              requestId,
              childPid: child.pid,
              rawRequestSha256: frame['rawRequestSha256'],
              messageCount: frame['messageCount'],
              toolNames: frame['toolNames'],
              userTexts: frame['userTexts'],
            })
            break
          case 'chunk': {
            const chunk = normalizeChunk(frame['chunk'])
            chunkSeq += 1
            trace(tracePath, 'chunk', { requestId, seq: chunkSeq, chunk })
            if (chunkSeq === 1) {
              process.stderr.write(`G3A_BRIDGE_STREAMING ${JSON.stringify({
                requestId, childPid: child.pid, mode, firstChunk: chunk.type, synthetic: true,
              })}\n`)
            }
            if (chunk.type === 'finish') {
              finish = chunk
              trace(tracePath, 'finish', { requestId, reason: chunk.reason })
              break
            }
            yield chunk
            break
          }
          case 'done':
            sawDone = true
            trace(tracePath, 'done', { requestId, exitReason: frame['exitReason'] ?? null })
            break
          case 'cancelled':
            trace(tracePath, 'cancelled', { requestId })
            break
          default:
            fail('G3A_BRIDGE_CHILD_FRAME_UNKNOWN', 'INVALID_RESPONSE')
        }
        if (finish !== null) break
      }
    } finally {
      clearTimeout(timeout)
      signal.removeEventListener('abort', onAbort)
      try { rl.close() } catch { /* closed */ }
      try { child.stdin.end() } catch { /* closed */ }
      const cleanExit = await waitExit(child, 1500)
      if (!cleanExit) {
        child.kill('SIGTERM')
        if (!await waitExit(child, 500)) child.kill('SIGKILL')
        await waitExit(child, 500)
      }
      trace(tracePath, 'cleanup', {
        requestId,
        exitCode: child.exitCode,
        signalCode: child.signalCode,
        aborted: abortKind === 'aborted',
        timedOut: abortKind === 'timeout',
        sawDone,
        stderr: stderrLines,
      })
    }

    if (finish === null) {
      if (spawnError !== null) throw new LlmError('G3A_BRIDGE_CHILD_SPAWN_ERROR', 'SERVER', { cause: spawnError })
      throw new LlmError(
        `G3A_BRIDGE_EOF_BEFORE_FINISH:${stderrLines.slice(-4).join(' | ')}`,
        'STREAM_CLOSED',
      )
    }
    process.stderr.write(`G3A_BRIDGE_COMPLETE ${JSON.stringify({
      requestId, childPid: child.pid, chunks: chunkSeq, finish: finish.type === 'finish' ? finish.reason.kind : null,
      usageSeen: chunkSeq > 0, realModelCalls: 0, httpCalls: 0, synthetic: true,
    })}\n`)
    yield finish
  }
}

export async function apply(ctx: Context): Promise<void> {
  const config = readConfig()
  if (ctx.llm.listProviders().length !== 0) throw new Error('G3A_BRIDGE_REAL_PROVIDERS_MUST_BE_DISABLED')
  ctx.llm.registerAdapter([provider], new BridgeAdapter(config))
  process.stderr.write(`G3A_BRIDGE_REGISTRY ${JSON.stringify({
    provider, model, python: config.python, fake: config.fake, transport: 'stdio-ndjson',
    synthetic: true, realModelCalls: 0, httpCalls: 0,
  })}\n`)
}
