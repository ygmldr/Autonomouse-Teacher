// Test-scope fixtures for the committed PR1 guard tests.
// Real Cordis LlmRuntime + real llm/stream waterfall; providers are explicit
// scripted fixtures, the broker is the committed fake NDJSON broker. No model,
// no HTTP, no Key. Execute ONLY inside the restricted no-Key container.
import { createHash } from 'node:crypto'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { LlmAdapter, LlmError } from '@deepseek-ai/dsh-llm'

const fixtureDir = dirname(fileURLToPath(import.meta.url))
export const fakeBrokerPackage = join(fixtureDir, 'fakebrokerpkg')
export const brokerPython = process.env.RBG_TEST_PYTHON ?? '/opt/python/bin/python3.11'

export const adapterState = { invocations: 0, mode: 'success' }

export function scriptedPlugin(config = {}) {
  return {
    name: 'rbg-pr1-scripted-provider', inject: ['llm'],
    apply(ctx) {
      adapterState.mode = config.mode ?? 'success'
      adapterState.invocations = 0
      ctx.llm.registerAdapter([config.route ?? 'offline-test-only'], new Adapter(config.maxRetries ?? 0))
    },
  }
}

class Adapter extends LlmAdapter {
  constructor(maxRetries) { super(); this.maxRetries = maxRetries }
  providerRetryPolicy() {
    return { mode: 'normal', maxRetries: this.maxRetries, retryableCodes: ['SERVER'], initialDelayMs: 1, maxDelayMs: 1, jitterRatio: 0 }
  }
  async resolveModel(route, id) {
    return { provider: route, id, name: 'scripted test provider', context: { contextWindow: 16384 }, defaultMaxTokens: 256, maxTokens: 1024, inputModalities: ['text'] }
  }
  async *stream() {
    adapterState.invocations += 1
    if (adapterState.mode === 'error') throw new LlmError('scripted provider error sk-FAKE-SECRET-ERROR', 'SERVER')
    yield { type: 'block-start', index: 0, blockType: 'text' }
    yield { type: 'text-delta', index: 0, text: 'PR1_SCRIPTED_OK' }
    yield { type: 'block-end', index: 0, block: { type: 'text', text: 'PR1_SCRIPTED_OK' } }
    yield { type: 'usage', usage: { inputTokens: 7, outputTokens: 3, cacheReadTokens: 0, cacheWriteTokens: 0, reasoningTokens: 0, totalTokens: 10 } }
    yield { type: 'finish', reason: { kind: 'stop' } }
  }
}

/** Inner middleware that mutates the request AFTER the outer guard admitted it. */
export function mutatePlugin(change) {
  return {
    name: 'rbg-pr1-mutating-middleware', inject: ['llm'],
    apply(ctx) {
      ctx.on('llm/stream', async function* (options, next) { change(options); yield* next() }, { prepend: true })
    },
  }
}

export function sha256(value) {
  return createHash('sha256').update(value).digest('hex')
}

export function makeScenario(mode, overrides = {}) {
  const base = join(tmpdir(), `rbg-pr1-${process.pid}-${Math.random().toString(16).slice(2)}`, `mode-${mode}`)
  mkdirSync(base, { recursive: true })
  const policy = {
    v: 1, synthetic: true, db_path: join(base, 'ledger.sqlite3'), scope_id: overrides.scope ?? 'fixed-offline-scope',
    max_messages: overrides.max_messages ?? 4096,
    limits: { soft_usd: '3', hard_usd: '10', per_call_usd: '0.20', max_requests: 50, max_input_tokens: 2500000, max_output_tokens: 600000, max_steps: 8, max_retries: 1 },
    routes: [{
      route_id: 'offline-test-only', model: 'fixture-v1',
      price: { version: 'synthetic-v1', input_per_million: '1', output_per_million: '2', cached_input_per_million: '0.5', source: 'synthetic fixture', captured_at: '2026-11-13' },
      known_extra_fee_usd: '0.001',
      usage_policy: { cache_write: 'input_rate', reasoning: 'included_in_output' },
    }],
  }
  const policyPath = join(base, 'startup.json')
  const policyBytes = JSON.stringify(policy)
  writeFileSync(policyPath, policyBytes, 'utf8')
  const guardConfig = {
    policy: {
      provider: 'offline-test-only', model: 'fixture-v1', brokerScopeId: overrides.scope ?? 'fixed-offline-scope',
      maxOutputTokens: overrides.maxOutputTokens ?? 1024, maxInputTokens: overrides.maxInputTokens ?? 2500000,
      maxProviderRetries: overrides.maxProviderRetries ?? 0, purposes: ['conversation', 'compaction', 'judge'],
    },
    broker: {
      python: brokerPython, pythonPath: fakeBrokerPackage, configPath: policyPath, configSha256: sha256(policyBytes),
      cwd: base, requestTimeoutMs: overrides.requestTimeoutMs ?? 700, startupTimeoutMs: overrides.startupTimeoutMs ?? 3000,
    },
  }
  return { base, guardConfig, policyPath, requestsPath: policy.db_path + '.requests.log' }
}

export function readRequests(requestsPath) {
  try {
    return readFileSync(requestsPath, 'utf8').split('\n').filter((line) => line.length > 0).map((line) => JSON.parse(line))
  } catch {
    return []
  }
}

export function baseOptions(overrides = {}) {
  return {
    provider: 'offline-test-only', model: 'fixture-v1', maxTokens: 256, sessionId: 'pr1-session',
    signal: new AbortController().signal,
    messages: [
      { id: 'm-system', role: 'system', source: { kind: 'system-prompt' }, content: [{ type: 'text', text: 'system' }] },
      { id: 'm-user', role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: 'PR1_SCRIPTED_OK' }] },
    ],
    ...overrides,
  }
}

export async function collect(iterable) {
  const chunks = []
  try {
    for await (const chunk of iterable) chunks.push(chunk)
    return { chunks, error: null }
  } catch (error) {
    return { chunks, error }
  }
}

export function captureStderr() {
  const lines = []
  const original = process.stderr.write.bind(process.stderr)
  process.stderr.write = (chunk) => { lines.push(String(chunk)); return true }
  return { lines, restore: () => { process.stderr.write = original } }
}
