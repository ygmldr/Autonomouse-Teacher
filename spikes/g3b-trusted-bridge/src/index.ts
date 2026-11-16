/**
 * G3-B B1: public Cordis LlmAdapter for the trusted-bridge IPC.
 *
 * The adapter is a candidate-boundary component. It does NOT spawn a process,
 * open a network socket, read a Key or trust provider-reported identity. Every
 * assembled GenerateOptions request is sent over the fixed AF_UNIX path
 * `/work/g3b/bridge.sock`; only protocol-validated StreamChunks are rebuilt
 * from the response. ack means "received", not "budget granted".
 */
import { createHash, randomBytes } from 'node:crypto'
import { createConnection, type Socket } from 'node:net'
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

export const name = 'autoteacher-g3b-trusted-bridge'
export const inject = ['llm']
export const provider = 'offline-test-only-g3b'
export const model = 'fixture-bridge-v1'

/** Frozen production UDS path. Never read from env/argv/request. */
export const BRIDGE_SOCKET = '/work/g3b/bridge.sock'

const PROTOCOL_VERSION = 1
const MAX_REQUEST_BYTES = 262_144
const MAX_RESPONSE_BYTES = 65_536
const MAX_TOTAL_RESPONSE_BYTES = 1_048_576
const MAX_CHUNKS = 256
const REQUEST_DEADLINE_MS = 30_000
const MAX_JSON_DEPTH = 32
const BLOCK_TYPES = new Set(['text', 'reasoning', 'image', 'file', 'tool-call',
  'tool-addition', 'tool-removal'])
const FINISH_KINDS = new Set(['stop', 'tool-calls', 'max-tokens', 'aborted', 'error', 'blocked'])

type Json = Record<string, unknown>

function record(value: unknown): value is Json {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function nonEmptyString(value: unknown, max = 512): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= max
}

function invalid(message: string): never {
  throw new LlmError(message, 'INVALID_REQUEST')
}

function invalidResponse(message: string): never {
  throw new LlmError(message, 'INVALID_RESPONSE')
}

function isPlainInt(value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): value is number {
  return Number.isSafeInteger(value) && (value as number) >= min && (value as number) <= max
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  if (record(value)) {
    const keys = Object.keys(value).sort()
    return `{${keys.map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) invalidResponse('G3B_BRIDGE_NONFINITE')
    return JSON.stringify(value)
  }
  return JSON.stringify(value)
}

function sha256Utf8(text: string): string {
  return createHash('sha256').update(text, 'utf8').digest('hex')
}

function depth(value: unknown, level = 0): number {
  if (level > MAX_JSON_DEPTH) invalid('G3B_BRIDGE_DEPTH')
  if (Array.isArray(value)) return value.reduce<number>((max: number, item: unknown) => Math.max(max, depth(item, level + 1)), level)
  if (record(value)) return Object.values(value).reduce<number>((max: number, item: unknown) => Math.max(max, depth(item, level + 1)), level)
  return level
}

function encodeEnvelope(kind: string, transportId: string, seq: number, payload: Json): string {
  const payloadBytes = Buffer.from(canonicalJson(payload), 'utf8')
  const hash = createHash('sha256').update(payloadBytes).digest('hex')
  return `${JSON.stringify({ v: PROTOCOL_VERSION, kind, transport_id: transportId, seq, payload, hash })}\n`
}

function decodeEnvelope(line: string): Json {
  if (Buffer.byteLength(line, 'utf8') > MAX_RESPONSE_BYTES) invalidResponse('G3B_BRIDGE_RESPONSE_TOO_LARGE')
  let value: unknown
  try {
    value = JSON.parse(line)
  } catch {
    invalidResponse('G3B_BRIDGE_BAD_JSON')
  }
  if (!record(value)) invalidResponse('G3B_BRIDGE_ENVELOPE_NOT_OBJECT')
  const keys = Object.keys(value)
  const allowed = new Set(['v', 'kind', 'transport_id', 'seq', 'payload', 'hash'])
  if (keys.some(key => !allowed.has(key))) invalidResponse('G3B_BRIDGE_UNKNOWN_ENVELOPE_FIELD')
  if (value['v'] !== PROTOCOL_VERSION) invalidResponse('G3B_BRIDGE_PROTOCOL_VERSION')
  if (typeof value['transport_id'] !== 'string' || !/^tr-[0-9a-f]{32}$/.test(value['transport_id'])) {
    invalidResponse('G3B_BRIDGE_TRANSPORT_ID')
  }
  if (!isPlainInt(value['seq']) || typeof value['kind'] !== 'string' || !record(value['payload'])) {
    invalidResponse('G3B_BRIDGE_ENVELOPE_FIELDS')
  }
  const recordedHash = value['hash']
  if (recordedHash !== undefined) {
    if (typeof recordedHash !== 'string' || !/^[0-9a-f]{64}$/.test(recordedHash)) {
      invalidResponse('G3B_BRIDGE_HASH_INVALID')
    }
    const expected = sha256Utf8(canonicalJson(value['payload']))
    if (recordedHash !== expected) invalidResponse('G3B_BRIDGE_HASH_MISMATCH')
  }
  return value
}

function requireUsage(value: unknown): TokenUsage {
  if (!record(value)) invalidResponse('G3B_BRIDGE_USAGE_INVALID')
  const required = ['inputTokens', 'outputTokens'] as const
  const optional = ['totalTokens', 'cacheReadTokens', 'cacheWriteTokens', 'reasoningTokens'] as const
  for (const key of required) {
    if (!isPlainInt(value[key])) invalidResponse('G3B_BRIDGE_USAGE_INVALID')
  }
  for (const key of optional) {
    if (value[key] !== undefined && !isPlainInt(value[key])) invalidResponse('G3B_BRIDGE_USAGE_INVALID')
  }
  const usage: TokenUsage = { inputTokens: value['inputTokens'] as number, outputTokens: value['outputTokens'] as number }
  for (const key of optional) {
    if (value[key] !== undefined) (usage as unknown as Json)[key] = value[key]
  }
  return usage
}

function requireFailure(value: unknown): { message: string; code: string } {
  if (!record(value) || !nonEmptyString(value['message']) || !nonEmptyString(value['code'])) {
    invalidResponse('G3B_BRIDGE_FAILURE_INVALID')
  }
  return { message: value['message'] as string, code: value['code'] as string }
}

function requireFinishReason(value: unknown): FinishReason {
  if (!record(value) || typeof value['kind'] !== 'string' || !FINISH_KINDS.has(value['kind'])) {
    invalidResponse('G3B_BRIDGE_FINISH_INVALID')
  }
  const kind = value['kind'] as string
  if (kind === 'stop' || kind === 'tool-calls' || kind === 'max-tokens') {
    if (Object.keys(value).length !== 1) invalidResponse('G3B_BRIDGE_FINISH_EXTRA')
    return { kind } as FinishReason
  }
  if (kind === 'aborted' || kind === 'error') {
    if (Object.keys(value).length !== 2) invalidResponse('G3B_BRIDGE_FINISH_EXTRA')
    return { kind, failure: requireFailure(value['failure']) } as FinishReason
  }
  if (Object.keys(value).length !== 1) invalidResponse('G3B_BRIDGE_FINISH_EXTRA')
  return { kind } as FinishReason
}

function requireIndex(value: unknown): number {
  if (!isPlainInt(value)) invalidResponse('G3B_BRIDGE_INDEX_INVALID')
  return value
}

function normalizeChunk(value: unknown): StreamChunk {
  if (!record(value) || typeof value['type'] !== 'string') invalidResponse('G3B_BRIDGE_CHUNK_INVALID')
  switch (value['type']) {
    case 'block-start': {
      if (!nonEmptyString(value['blockType'], 64) || !BLOCK_TYPES.has(value['blockType'])) {
        invalidResponse('G3B_BRIDGE_BLOCK_INVALID')
      }
      return { type: 'block-start', index: requireIndex(value['index']),
        blockType: value['blockType'] as ContentBlock['type'] }
    }
    case 'text-delta':
    case 'reasoning-delta': {
      if (typeof value['text'] !== 'string') invalidResponse('G3B_BRIDGE_DELTA_INVALID')
      return { type: value['type'], index: requireIndex(value['index']), text: value['text'] } as StreamChunk
    }
    case 'tool-call-delta': {
      if (!nonEmptyString(value['id']) || typeof value['argumentsDelta'] !== 'string') {
        invalidResponse('G3B_BRIDGE_TOOL_DELTA_INVALID')
      }
      return {
        type: 'tool-call-delta', index: requireIndex(value['index']), id: ToolCallId(value['id']),
        ...(value['name'] === undefined ? {} : { name: nonEmptyString(value['name']) ? value['name'] as string : invalidResponse('G3B_BRIDGE_TOOL_NAME') }),
        argumentsDelta: value['argumentsDelta'] as string,
      }
    }
    case 'block-end': {
      if (!record(value['block']) || typeof value['block']['type'] !== 'string'
          || !BLOCK_TYPES.has(value['block']['type'])) invalidResponse('G3B_BRIDGE_BLOCK_INVALID')
      return { type: 'block-end', index: requireIndex(value['index']), block: value['block'] as unknown as ContentBlock }
    }
    case 'usage':
      return { type: 'usage', usage: requireUsage(value['usage']) }
    default:
      invalidResponse('G3B_BRIDGE_CHUNK_UNKNOWN')
  }
}

function buildRequestPayload(options: GenerateOptions): Json {
  if (options.provider !== provider || options.model !== model) {
    invalid('G3B_BRIDGE_ROUTE_ONLY')
  }
  const sessionId = options.sessionId ?? 'g3b-no-session'
  if (!nonEmptyString(sessionId, 512)) invalid('G3B_BRIDGE_SESSION_ID')
  const messages = options.messages ?? []
  const tools = options.tools ?? []
  const maxTokens = options.maxTokens ?? 256
  if (!isPlainInt(maxTokens, 1, 1024)) invalid('G3B_BRIDGE_MAX_TOKENS')
  const purpose = options.purpose ?? null
  if (purpose !== null && purpose !== 'conversation') invalid('G3B_BRIDGE_PURPOSE')
  const payload: Json = {
    sessionId,
    provider,
    model,
    messages,
    tools,
    system: options.system ?? null,
    maxTokens,
    stream: true,
    purpose,
  }
  depth(payload)
  const bytes = Buffer.byteLength(canonicalJson(payload), 'utf8')
  if (bytes > MAX_REQUEST_BYTES) invalid('G3B_BRIDGE_REQUEST_TOO_LARGE')
  return payload
}

class FrameQueue {
  #lines: string[] = []
  #buffer = Buffer.alloc(0)
  #waiters: Array<{ resolve: (line: string | null) => void; reject: (error: Error) => void }> = []
  #closed = false
  #failure: Error | null = null

  push(data: Buffer): void {
    if (this.#closed) return
    this.#buffer = Buffer.concat([this.#buffer, data])
    for (;;) {
      const index = this.#buffer.indexOf(0x0a)
      if (index < 0) {
        if (this.#buffer.length > MAX_RESPONSE_BYTES) this.fail(new Error('G3B_BRIDGE_LINE_TOO_LARGE'))
        return
      }
      const lineBuffer = this.#buffer.subarray(0, index)
      this.#buffer = this.#buffer.subarray(index + 1)
      if (lineBuffer.length > MAX_RESPONSE_BYTES) {
        this.fail(new Error('G3B_BRIDGE_LINE_TOO_LARGE'))
        return
      }
      const line = lineBuffer.toString('utf8')
      const waiter = this.#waiters.shift()
      if (waiter) waiter.resolve(line)
      else this.#lines.push(line)
    }
  }

  end(): void {
    if (this.#closed) return
    if (this.#buffer.length > 0) return this.fail(new Error('G3B_BRIDGE_TRUNCATED'))
    this.#closed = true
    while (this.#waiters.length > 0) this.#waiters.shift()!.resolve(null)
  }

  fail(error: Error): void {
    if (this.#closed) return
    this.#closed = true
    this.#failure = error
    while (this.#waiters.length > 0) this.#waiters.shift()!.reject(error)
  }

  next(): Promise<string | null> {
    if (this.#lines.length > 0) return Promise.resolve(this.#lines.shift()!)
    if (this.#failure !== null) return Promise.reject(this.#failure)
    if (this.#closed) return Promise.resolve(null)
    return new Promise((resolve, reject) => this.#waiters.push({ resolve, reject }))
  }
}

class BridgeAbort extends Error {}

export class BridgeAdapter extends LlmAdapter {
  override providerRetryPolicy(): ResolvedRetryPolicy {
    return { mode: 'normal', maxRetries: 0, retryableCodes: [], initialDelayMs: 1, maxDelayMs: 1, jitterRatio: 0 }
  }

  override async resolveModel(route: string, id: string, _signal?: AbortSignal) {
    if (route !== provider || id !== model) invalid('G3B_BRIDGE_ROUTE_ONLY')
    return {
      provider,
      id: model,
      name: 'G3-B trusted UDS bridge fixture, NOT a model',
      context: { contextWindow: 16384 },
      defaultMaxTokens: 256,
      maxTokens: 1024,
      inputModalities: ['text' as const],
    }
  }

  override async *stream(options: GenerateOptions): AsyncGenerator<StreamChunk> {
    const signal = options.signal ?? new AbortController().signal
    signal.throwIfAborted()
    const payload = buildRequestPayload(options)
    const transportId = `tr-${randomBytes(16).toString('hex')}`
    const request = encodeEnvelope('request', transportId, 0, payload)
    if (Buffer.byteLength(request, 'utf8') > MAX_REQUEST_BYTES) invalid('G3B_BRIDGE_REQUEST_TOO_LARGE')

    const socket: Socket = createConnection({ path: BRIDGE_SOCKET })
    const queue = new FrameQueue()
    let totalBytes = 0
    let aborted = false
    let timedOut = false
    let lastServerSeq = 0
    let lastClientSeq = 0
    let usageSeen = false
    let finishSeen = false
    let chunkCount = 0

    const cleanup = (): void => {
      signal.removeEventListener('abort', onAbort)
      clearTimeout(deadline)
      socket.destroy()
    }
    const sendCancel = (reason: 'aborted' | 'timeout'): void => {
      try {
        lastClientSeq += 1
        socket.write(encodeEnvelope('cancel', transportId, lastClientSeq,
          { request_id: transportId, reason }))
      } catch { /* socket may already be gone */ }
    }
    const onAbort = (): void => {
      if (aborted) return
      aborted = true
      sendCancel('aborted')
      queue.fail(new BridgeAbort('aborted'))
      socket.destroy()
    }
    const deadline = setTimeout(() => {
      if (aborted || finishSeen) return
      timedOut = true
      sendCancel('timeout')
      queue.fail(new BridgeAbort('timeout'))
      socket.destroy()
    }, REQUEST_DEADLINE_MS)

    socket.on('data', (data: Buffer) => {
      totalBytes += data.length
      if (totalBytes > MAX_TOTAL_RESPONSE_BYTES) {
        queue.fail(new Error('G3B_BRIDGE_TOTAL_BYTES_EXCEEDED'))
        socket.destroy()
        return
      }
      queue.push(data)
    })
    socket.on('end', () => queue.end())
    socket.on('error', (error: Error) => queue.fail(error))
    signal.addEventListener('abort', onAbort, { once: true })

    const nextFrame = async (): Promise<Json | null> => {
      const line = await queue.next()
      if (line === null) return null
      const envelope = decodeEnvelope(line)
      const seq = envelope['seq'] as number
      if (seq <= lastServerSeq) invalidResponse('G3B_BRIDGE_SEQ_OUT_OF_ORDER')
      lastServerSeq = seq
      if (envelope['transport_id'] !== transportId) invalidResponse('G3B_BRIDGE_TRANSPORT_MISMATCH')
      return envelope
    }

    try {
      await new Promise<void>((resolve, reject) => {
        socket.once('connect', resolve)
        socket.once('error', reject)
      }).catch(() => {
        throw new LlmError('G3B_BRIDGE_CONNECT_FAILED', 'SERVER')
      })
      socket.write(request)
      const ack = await nextFrame().catch(error => {
        if (aborted) throw new BridgeAbort('aborted')
        if (timedOut) throw new BridgeAbort('timeout')
        throw error
      })
      if (ack === null) invalidResponse('G3B_BRIDGE_EOF_BEFORE_ACK')
      if (ack['kind'] !== 'ack') invalidResponse('G3B_BRIDGE_ACK_REQUIRED')
      const ackPayload = ack['payload'] as Json
      if (ackPayload['accepted'] !== true || ackPayload['request_id'] !== transportId
          || ackPayload['code'] !== null) invalidResponse('G3B_BRIDGE_ACK_INVALID')

      for (;;) {
        let envelope: Json | null
        try {
          envelope = await nextFrame()
        } catch (error) {
          if (aborted) throw new BridgeAbort('aborted')
          if (timedOut) throw new BridgeAbort('timeout')
          throw error
        }
        if (envelope === null) {
          if (aborted) throw new BridgeAbort('aborted')
          invalidResponse('G3B_BRIDGE_EOF_BEFORE_FINISH')
        }
        const kind = envelope['kind'] as string
        const responsePayload = envelope['payload'] as Json
        if (kind === 'chunk') {
          if (finishSeen) invalidResponse('G3B_BRIDGE_CHUNK_AFTER_FINISH')
          chunkCount += 1
          if (chunkCount > MAX_CHUNKS) invalidResponse('G3B_BRIDGE_CHUNK_LIMIT')
          const chunk = normalizeChunk(responsePayload['chunk'])
          if (chunk.type === 'usage') usageSeen = true
          yield chunk
          continue
        }
        if (kind === 'finish') {
          if (finishSeen) invalidResponse('G3B_BRIDGE_DUPLICATE_FINISH')
          const finish = requireFinishReason(responsePayload['reason'])
          finishSeen = true
          yield { type: 'finish', reason: finish }
          return
        }
        if (kind === 'error') {
          const code = responsePayload['code']
          if (typeof code !== 'string') invalidResponse('G3B_BRIDGE_ERROR_INVALID')
          throw new LlmError(`G3B_BRIDGE_${code}`, 'SERVER')
        }
        invalidResponse('G3B_BRIDGE_KIND_UNKNOWN')
      }
    } catch (error) {
      if (error instanceof BridgeAbort) {
        throw new LlmError(error.message === 'timeout' ? 'G3B_BRIDGE_TIMEOUT' : 'G3B_BRIDGE_ABORTED',
          error.message === 'timeout' ? 'TIMEOUT' : 'ABORTED')
      }
      if (error instanceof LlmError) throw error
      throw new LlmError('G3B_BRIDGE_FRAME_ERROR', 'INVALID_RESPONSE')
    } finally {
      cleanup()
    }
  }
}

export function apply(ctx: Context): void {
  const existing = ctx.llm.listProviders()
  if (existing.length > 0) {
    throw new Error('G3B_BRIDGE_EXISTING_PROVIDER_PRESENT')
  }
  ctx.llm.registerAdapter([provider], new BridgeAdapter())
  process.stderr.write(`G3B_BRIDGE_REGISTRY ${JSON.stringify({
    provider, model, transport: 'af-unix-fixed', socket: BRIDGE_SOCKET,
    synthetic: true, realModelCalls: 0, httpCalls: 0,
  })}\n`)
}
