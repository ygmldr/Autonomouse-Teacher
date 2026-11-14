import type { Context } from '@deepseek-ai/cordis'
import { LlmAdapter, LlmError, ToolCallId, type GenerateOptions, type StreamChunk, type ResolvedRetryPolicy } from '@deepseek-ai/dsh-llm'
import type {} from '@deepseek-ai/dsh-tools'

export const name = 'autoteacher-offline-fixture'
export const inject = ['llm', 'tools']
export const provider = 'offline-test-only'
export const model = 'fixture-v1'
const NONCE = /^[A-Za-z0-9_-]{8,48}$/

function fail(message: string): never { throw new LlmError(message, 'INVALID_REQUEST') }

/** Check the complete real assembled history, not merely a submitted prompt. */
function checkRequest(options: GenerateOptions): void {
  if (options.provider !== provider || options.model !== model || options.purpose !== undefined) fail('OFFLINE_FIXTURE_ROUTE_ONLY')
  if (!options.sessionId || !options.signal || !Number.isSafeInteger(options.maxTokens) || options.maxTokens! < 1 || options.maxTokens! > 1024) fail('OFFLINE_FIXTURE_BOUNDED_SESSION_REQUIRED')
  for (const message of options.messages) {
    for (const block of message.content) {
      if (!['text', 'reasoning', 'tool-call', 'tool-addition', 'tool-removal'].includes(block.type)) fail('OFFLINE_FIXTURE_TEXT_ONLY')
      if (block.type === 'tool-call' && block.name !== 'skill_lookup') fail('OFFLINE_FIXTURE_SKILL_ONLY')
      if ((block.type === 'tool-addition' || block.type === 'tool-removal') && block.toolName !== 'skill_lookup') fail('OFFLINE_FIXTURE_SKILL_ONLY')
    }
  }
  if ((options.tools ?? []).some(tool => tool.name !== 'skill_lookup')) fail('OFFLINE_FIXTURE_SKILL_ONLY')
}

async function* text(value: string): AsyncGenerator<StreamChunk> {
  yield { type: 'block-start', index: 0, blockType: 'text' }
  yield { type: 'text-delta', index: 0, text: value }
  yield { type: 'block-end', index: 0, block: { type: 'text', text: value } }
  yield { type: 'usage', usage: { inputTokens: 7, outputTokens: 3, cacheReadTokens: 0, cacheWriteTokens: 0, reasoningTokens: 0, totalTokens: 10 } }
  yield { type: 'finish', reason: { kind: 'stop' } }
}

/** No filesystem, shared nonce map, random output, HTTP client or model exists here. */
export class OfflineFixtureAdapter extends LlmAdapter {
  private invocations = 0 // Instrumentation only; never used to select nonce/output.
  override providerRetryPolicy(): ResolvedRetryPolicy {
    return { mode: 'normal', maxRetries: 0, retryableCodes: ['SERVER'], initialDelayMs: 1, maxDelayMs: 1, jitterRatio: 0 }
  }
  override async resolveModel(route: string, id: string) {
    if (route !== provider || id !== model) fail('OFFLINE_FIXTURE_ROUTE_ONLY')
    return { provider, id: model, name: 'Deterministic offline test fixture, NOT a model', context: { contextWindow: 16384 }, defaultMaxTokens: 256, maxTokens: 1024, inputModalities: ['text' as const] }
  }
  override async *stream(options: GenerateOptions): AsyncGenerator<StreamChunk> {
    checkRequest(options)
    options.signal!.throwIfAborted()
    const userTexts = options.messages.filter(message => message.role === 'user' && 'source' in message && message.source?.kind === 'user').map(message =>
      message.content.filter(block => block.type === 'text').map(block => block.text).join(''))
    const command = userTexts.at(-1) ?? ''
    process.stderr.write(`FIXTURE_INVOCATION ${JSON.stringify({ ordinal: ++this.invocations, sessionId: options.sessionId, provider, model, purpose: 'conversation', synthetic: true, real_model_calls: 0, http_calls: 0, command })}\n`)
    if (command === 'FIXTURE_JSON') { yield* text('{"skill_id":"binary_search","ready":true}'); return }
    if (command === 'FIXTURE_TOOL') {
      const tail = options.messages.filter(message => !(message.role === 'user' && 'source' in message && message.source?.kind !== 'user')).at(-1)
      if (tail?.role === 'tool') {
        const rendered = tail.content.filter(block => block.type === 'text').map(block => block.text).join('')
        const value: unknown = JSON.parse(rendered)
        if (typeof value !== 'object' || value === null || !('id' in value) || value.id !== 'binary_search' || !('prerequisites' in value) || !Array.isArray(value.prerequisites)) fail('OFFLINE_FIXTURE_BAD_ACTUAL_TOOL_RESULT')
        yield* text(JSON.stringify({ tool: 'skill_lookup', id: value.id, prerequisites: value.prerequisites, synthetic: true }))
        return
      }
      const priorCalls = options.messages.flatMap(message => message.content).filter(block => block.type === 'tool-call').length
      const id = ToolCallId(`offline-skill-${priorCalls + 1}`)
      const argumentsText = '{"skill_id":"binary_search"}'
      yield { type: 'block-start', index: 0, blockType: 'tool-call' }
      yield { type: 'tool-call-delta', index: 0, id, name: 'skill_lookup', argumentsDelta: argumentsText }
      yield { type: 'block-end', index: 0, block: { type: 'tool-call', id, name: 'skill_lookup', arguments: argumentsText } }
      yield { type: 'usage', usage: { inputTokens: 7, outputTokens: 3, cacheReadTokens: 0, cacheWriteTokens: 0, reasoningTokens: 0, totalTokens: 10 } }
      yield { type: 'finish', reason: { kind: 'tool-calls' } }
      return
    }
    const remembered = /^FIXTURE_REMEMBER nonce=([A-Za-z0-9_-]+)$/.exec(command)
    if (remembered && NONCE.test(remembered[1]!)) { yield* text(`REMEMBERED:${remembered[1]}`); return }
    if (command === 'FIXTURE_RECALL') {
      // Only genuine prior USER messages may supply the nonce. Nothing from env,
      // sessionId, files, counters, or another process can reconstruct it.
      const nonces = userTexts.map(value => /^FIXTURE_(?:REMEMBER|INTERRUPT) nonce=([A-Za-z0-9_-]+)$/.exec(value)?.[1]).filter((value): value is string => value !== undefined && NONCE.test(value))
      yield* text(nonces.length ? `RECALLED:${nonces.at(-1)}` : 'NO_NONCE_IN_REAL_MESSAGES')
      return
    }
    const interrupted = /^FIXTURE_INTERRUPT nonce=([A-Za-z0-9_-]+)$/.exec(command)
    if (interrupted && NONCE.test(interrupted[1]!)) {
      yield { type: 'block-start', index: 0, blockType: 'text' }
      yield { type: 'text-delta', index: 0, text: 'INCOMPLETE_FIXTURE_STREAM' }
      process.stderr.write(`FIXTURE_INTERRUPT_READY ${options.sessionId}\n`)
      await new Promise<void>((resolve, reject) => {
        const signal = options.signal!
        const done = () => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve() }
        const timer = setTimeout(() => { signal.removeEventListener('abort', done); reject(new Error('OFFLINE_FIXTURE_FINITE_WAIT_EXPIRED')) }, 10000)
        if (signal.aborted) done(); else signal.addEventListener('abort', done, { once: true })
      })
      throw new LlmError('offline fixture interrupted', 'ABORTED')
    }
    fail('OFFLINE_FIXTURE_UNKNOWN_SCRIPT')
  }
}

export async function apply(ctx: Context): Promise<void> {
  if (process.env.AUTOTEACHER_OFFLINE_FIXTURE !== '1') throw new Error('OFFLINE_FIXTURE_EXPLICIT_OPT_IN_REQUIRED')
  if (ctx.llm.listProviders().length !== 0) throw new Error('OFFLINE_FIXTURE_REAL_PROVIDERS_MUST_BE_DISABLED')
  ctx.llm.registerAdapter([provider], new OfflineFixtureAdapter())
  ctx.on('llm/stream', async function* (options, next) {
    checkRequest(options)
    const providers = ctx.llm.listProviders().map(route => route.id).sort()
    const tools = ctx.tools.schemas().map(tool => tool.name).sort()
    if (providers.join(',') !== provider || tools.join(',') !== 'skill_lookup') fail('OFFLINE_FIXTURE_UNSAFE_ACTUAL_REGISTRY')
    process.stderr.write(`FIXTURE_REGISTRY ${JSON.stringify({ providers, tools, synthetic: true })}\n`)
    yield* next()
  }, { prepend: true })
  // Exercise the REAL public waterfall with a nonexistent, NON-real route.
  // No adapter can own this route; the explicit guard must reject it first.
  let rejected = false
  try {
    for await (const _chunk of ctx.llm.stream({ provider: 'offline-rejected-test-route', model, messages: [], maxTokens: 1, signal: new AbortController().signal })) {
      throw new Error('OFFLINE_FIXTURE_GUARD_DID_NOT_REJECT')
    }
  } catch (error) {
    rejected = error instanceof Error && error.message === 'OFFLINE_FIXTURE_ROUTE_ONLY'
  }
  if (!rejected) throw new Error('OFFLINE_FIXTURE_GUARD_SELFTEST_FAILED')
  process.stderr.write('FIXTURE_GUARD_SELFTEST {"status":"PASS","rejected_route":"offline-rejected-test-route","synthetic_adapter_invocations":0,"http_calls":0}\n')
}
