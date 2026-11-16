// O-4 additive precheck tests. Real public Cordis LlmRuntime + waterfall;
// scripted provider only; fake broker is NOT spawned in precheck mode.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { Context } from '@deepseek-ai/cordis'
import LlmRuntime from '@deepseek-ai/dsh-llm'
import * as guard from '../lib/index.js'
import { baseOptions, captureStderr, collect, makeScenario, readRequests, scriptedPlugin, adapterState } from './fixtures/scripted.mjs'

function stderrLines(captured) {
  return captured.lines.join('').split('\n').filter((line) => line.startsWith('RBG_'))
}
function dataLines(captured, kind) {
  return stderrLines(captured).filter((line) => line.startsWith(`RBG_${kind} `))
    .map((line) => JSON.parse(line.slice(`RBG_${kind} `.length)))
}
async function withGuard(config, plugins, body) {
  const ctx = new Context()
  await ctx.plugin(LlmRuntime)
  for (const plugin of plugins) await ctx.plugin(plugin)
  await ctx.plugin(guard, config)
  try { return await body(ctx) } finally { await ctx.fiber.dispose() }
}
function precheckScenario(overrides = {}) {
  const scenario = makeScenario('normal', overrides)
  return { ...scenario, guardConfig: { ...scenario.guardConfig, reserveMode: 'precheck' } }
}

test('O-4 precheck boots without broker child and delegates accounting', async () => {
  const scenario = precheckScenario()
  const captured = captureStderr()
  try {
    await withGuard(scenario.guardConfig, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      const result = await collect(ctx.llm.stream(baseOptions()))
      assert.equal(result.error, null, String(result.error))
      assert.equal(adapterState.invocations, 1)
      assert.ok(result.chunks.some((chunk) => chunk.type === 'finish'))
    })
    assert.deepEqual(readRequests(scenario.requestsPath), [], 'precheck must not spawn/speak to broker')
    const boot = dataLines(captured, 'BOOT')[0]
    assert.equal(boot.reserve_mode, 'precheck')
    assert.equal(boot.broker_child, 'disabled')
    assert.equal(boot.accounting, undefined)
    const precheck = dataLines(captured, 'PRECHECK')
    assert.equal(precheck.length, 1)
    assert.equal(precheck[0].reserve_mode, 'precheck')
    assert.equal(precheck[0].broker_child, 'disabled')
    assert.match(precheck[0].task_id, /^rbg-[0-9a-f]{64}$/)
    assert.equal(precheck[0].session_id_hash.length, 32)
    assert.equal(precheck[0].provider, 'offline-test-only')
    assert.equal(precheck[0].model, 'fixture-v1')
    const delegated = dataLines(captured, 'ACCOUNTING_DELEGATED_TO_CONTROLLER')
    assert.equal(delegated.length, 1)
    assert.equal(delegated[0].guard_reserved, false)
    assert.equal(delegated[0].guard_settled, false)
    assert.equal(dataLines(captured, 'RESERVE').length, 0)
    assert.equal(dataLines(captured, 'SETTLE').length, 0)
  } finally { captured.restore() }
})

test('O-4 precheck fails closed on disallowed tool and never dispatches', async () => {
  const scenario = precheckScenario()
  const captured = captureStderr()
  try {
    await withGuard(scenario.guardConfig, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      const options = baseOptions({ tools: [{ name: 'shell', description: 'bad', parameters: {} }] })
      const result = await collect(ctx.llm.stream(options))
      assert.match(String(result.error.message), /RBG_UNKNOWN_TOOL_SCHEMA/)
      assert.equal(adapterState.invocations, 0)
    })
    assert.deepEqual(readRequests(scenario.requestsPath), [])
    assert.equal(dataLines(captured, 'STREAM_REFUSED')[0].reserve_mode, 'precheck')
  } finally { captured.restore() }
})

test('O-4 unknown reserveMode fails boot and registers deny-all', async () => {
  const scenario = makeScenario('normal')
  scenario.guardConfig.reserveMode = 'later'
  const captured = captureStderr()
  try {
    await withGuard(scenario.guardConfig, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      const result = await collect(ctx.llm.stream(baseOptions()))
      assert.match(String(result.error.message), /RBG_GUARD_BOOT_INVALID/)
      assert.equal(adapterState.invocations, 0)
    })
    assert.ok(dataLines(captured, 'BOOT_INVALID').length >= 1)
  } finally { captured.restore() }
})

test('O-4 default reserve mode remains byte-compatible and still brokers', async () => {
  const scenario = makeScenario('normal')
  const captured = captureStderr()
  try {
    await withGuard(scenario.guardConfig, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      const result = await collect(ctx.llm.stream(baseOptions()))
      assert.equal(result.error, null, String(result.error))
    })
    const requests = readRequests(scenario.requestsPath)
    assert.deepEqual(requests.map((request) => request.op), ['reserve', 'settle'])
    const boot = dataLines(captured, 'BOOT')[0]
    assert.equal(boot.reserve_mode, undefined)
    assert.equal(boot.broker_child, undefined)
    assert.equal(dataLines(captured, 'PRECHECK').length, 0)
  } finally { captured.restore() }
})
