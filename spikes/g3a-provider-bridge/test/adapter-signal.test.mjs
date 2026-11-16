// Supplementary adapter-level cancellation evidence. This is the real public
// Cordis LlmRuntime + real llm/stream waterfall, NOT the Python SDK/runtime.
// The SDK 0.2.2-rc.2 has no cancel method, so DSH-level cancellation remains
// unverified; this test proves the adapter honors GenerateOptions.signal.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mkdirSync, readFileSync, readdirSync } from 'node:fs'
import { Context } from '@deepseek-ai/cordis'
import LlmRuntime from '@deepseek-ai/dsh-llm'
import * as bridge from '../lib/index.js'

const base = '/work/g3a/signal'
process.env.AUTOTEACHER_G3A_BRIDGE = '1'
process.env.G3A_BRIDGE_PYTHON = '/opt/python/bin/python3.11'
process.env.G3A_BRIDGE_FAKE = '/probe/bridge/fake_provider.py'
process.env.G3A_BRIDGE_TRACE_DIR = `${base}/bridge`
process.env.G3A_BRIDGE_RECEIPT_DIR = `${base}/fake`
mkdirSync(process.env.G3A_BRIDGE_TRACE_DIR, { recursive: true })
mkdirSync(process.env.G3A_BRIDGE_RECEIPT_DIR, { recursive: true })

test('adapter aborts on GenerateOptions.signal and reaps the external child', async () => {
  const ctx = new Context()
  try {
    await ctx.plugin(LlmRuntime)
    await ctx.plugin(bridge)
    const controller = new AbortController()
    const options = {
      provider: 'g3a-bridge-test',
      model: 'bridge-v1',
      maxTokens: 256,
      sessionId: 'g3a-signal-session',
      signal: controller.signal,
      messages: [{ id: 'm1', role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: 'G3A_CANCEL' }] }],
      tools: [],
    }
    const iterator = ctx.llm.stream(options)[Symbol.asyncIterator]()
    const first = await iterator.next()
    assert.equal(first.done, false)
    assert.equal(first.value.type, 'block-start')
    controller.abort()
    const chunks = [first.value]
    for (;;) {
      const next = await iterator.next()
      if (next.done) break
      chunks.push(next.value)
      if (next.value.type === 'finish') break
    }
    const finish = chunks.at(-1)
    assert.equal(finish.type, 'finish')
    assert.equal(finish.reason.kind, 'aborted')
    const trace = readdirSync(process.env.G3A_BRIDGE_TRACE_DIR).find(name => name.endsWith('.jsonl'))
    assert.ok(trace)
    const events = readFileSync(`${process.env.G3A_BRIDGE_TRACE_DIR}/${trace}`, 'utf8').trim().split('\n').map(JSON.parse)
    assert.ok(events.some(event => event.event === 'abort-signal'))
    const cleanup = events.find(event => event.event === 'cleanup')
    assert.ok(cleanup)
    assert.equal(cleanup.aborted, true)
    assert.equal(cleanup.exitCode, 0)
  } finally {
    await ctx.fiber.dispose()
  }
})
