// Container-only B1 adapter tests. The stub Controller is intentionally
// untrusted and is NOT evidence for admission/budget/claim/Fake semantics.
// The adapter itself must not spawn a child or open a network socket; only the
// test harness starts the stub so the fixed UDS path can be exercised.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdirSync, readFileSync, rmSync, existsSync } from 'node:fs'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import { Context } from '@deepseek-ai/cordis'
import LlmRuntime from '@deepseek-ai/dsh-llm'
const bridge = await import(pathToFileURL('/probe/lib/index.js').href)

const PYTHON = '/opt/python/bin/python3.11'
const STUB = '/src/test/stub_controller.py'
const SOCKET = '/work/g3b/bridge.sock'
const BASE = '/work/g3b'

async function startStub(mode) {
  mkdirSync(BASE, { recursive: true, mode: 0o700 })
  try { rmSync(SOCKET, { force: true }) } catch {}
  const proc = spawn(PYTHON, ['-B', STUB], {
    cwd: '/work',
    env: { PATH: '/usr/bin', HOME: '/work', G3B_STUB_MODE: mode },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  for (let i = 0; i < 300; i += 1) {
    if (existsSync(SOCKET)) return proc
    if (proc.exitCode !== null) break
    await new Promise(resolve => setTimeout(resolve, 10))
  }
  proc.kill('SIGKILL')
  throw new Error(`stub did not create ${SOCKET}`)
}

async function stopStub(proc) {
  try { proc.kill('SIGKILL') } catch {}
  await new Promise(resolve => proc.once('exit', resolve))
  try { rmSync(SOCKET, { force: true }) } catch {}
}

function options(signal) {
  return {
    provider: bridge.provider,
    model: bridge.model,
    maxTokens: 256,
    sessionId: 'g3b-b1-test',
    signal,
    messages: [{ role: 'user', content: [{ type: 'text', text: 'G3B_B1_FIXTURE' }] }],
    tools: [],
  }
}

async function collect(adapter, opts) {
  const chunks = []
  for await (const chunk of adapter.stream(opts)) chunks.push(chunk)
  return chunks
}

test('adapter forwards one request and rebuilds only whitelisted chunks', async () => {
  const proc = await startStub('ok')
  try {
    const adapter = new bridge.BridgeAdapter()
    const chunks = await collect(adapter, options(new AbortController().signal))
    assert.deepEqual(chunks.map(chunk => chunk.type), [
      'block-start', 'text-delta', 'block-end', 'usage', 'finish',
    ])
    assert.deepEqual(chunks.at(-1), { type: 'finish', reason: { kind: 'stop' } })
    const lib = readFileSync('/probe/lib/index.js', 'utf8')
    assert.equal(lib.includes('child_process'), false)
  } finally {
    await stopStub(proc)
  }
})

test('adapter honors AbortSignal: sends cancel and reports ABORTED', async () => {
  const proc = await startStub('slow')
  try {
    const controller = new AbortController()
    const adapter = new bridge.BridgeAdapter()
    const iterator = adapter.stream(options(controller.signal))[Symbol.asyncIterator]()
    const first = await iterator.next()
    assert.equal(first.done, false)
    assert.equal(first.value.type, 'block-start')
    controller.abort()
    await assert.rejects(async () => {
      for (;;) {
        const next = await iterator.next()
        if (next.done) break
      }
    }, error => {
      assert.equal(error.code, 'ABORTED')
      return true
    })
  } finally {
    await stopStub(proc)
  }
})

test('adapter rejects malformed JSON frames', async () => {
  const proc = await startStub('bad_frame')
  try {
    const adapter = new bridge.BridgeAdapter()
    await assert.rejects(collect(adapter, options(new AbortController().signal)),
      error => error.code === 'INVALID_RESPONSE')
  } finally {
    await stopStub(proc)
  }
})

test('adapter rejects oversized response frames without unbounded buffering', async () => {
  const proc = await startStub('large_frame')
  try {
    const adapter = new bridge.BridgeAdapter()
    await assert.rejects(collect(adapter, options(new AbortController().signal)),
      error => error.code === 'INVALID_RESPONSE')
  } finally {
    await stopStub(proc)
  }
})

test('adapter accepts exactly one terminal finish', async () => {
  const proc = await startStub('duplicate_finish')
  try {
    const adapter = new bridge.BridgeAdapter()
    const chunks = await collect(adapter, options(new AbortController().signal))
    assert.equal(chunks.filter(chunk => chunk.type === 'finish').length, 1)
  } finally {
    await stopStub(proc)
  }
})

test('apply registers only the frozen provider tuple and refuses pre-existing providers', async () => {
  const ctx = new Context()
  try {
    await ctx.plugin(LlmRuntime)
    await ctx.plugin(bridge)
    assert.deepEqual(ctx.llm.listProviders().map(item => item.id), ['offline-test-only-g3b'])
    assert.equal(bridge.provider, 'offline-test-only-g3b')
    assert.equal(bridge.model, 'fixture-bridge-v1')
    assert.equal(bridge.BRIDGE_SOCKET, '/work/g3b/bridge.sock')
  } finally {
    await ctx.fiber.dispose()
  }
  const second = new Context()
  try {
    await second.plugin(LlmRuntime)
    await second.plugin(bridge)
    await assert.rejects(async () => { await second.plugin(bridge) })
  } finally {
    await second.fiber.dispose()
  }
})
