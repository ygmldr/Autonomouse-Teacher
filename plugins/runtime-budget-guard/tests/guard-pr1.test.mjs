// Committed v0.5 PR1 targeted guard tests (F1/F3/F4/F5/F6 + guard-side F2 bound).
// Real public Cordis LlmRuntime + real llm/stream waterfall; providers are
// explicit scripted fixtures and the broker is the committed fake NDJSON broker.
// No model, no HTTP, no Key, no production route.
//
// Run (after `npm run build`, inside the restricted container or a normal dev
// machine): `node --test tests/`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { Context } from '@deepseek-ai/cordis'

import LlmRuntime from '@deepseek-ai/dsh-llm'
import * as guard from '../lib/index.js'
import {
  baseOptions, captureStderr, collect, makeScenario, mutatePlugin, readRequests,
  scriptedPlugin, sha256, adapterState,
} from './fixtures/scripted.mjs'

const guardLib = fileURLToPath(new URL('../lib/index.js', import.meta.url))

function stderrLines(captured) {
  return captured.lines.join('').split('\n').filter((line) => line.startsWith('RBG_'))
}
function dataLines(captured, kind) {
  return stderrLines(captured).filter((line) => line.startsWith(`RBG_${kind} `))
    .map((line) => JSON.parse(line.slice(`RBG_${kind} `.length)))
}
function expectError(result, needle) {
  assert.ok(result.error !== null, `expected error containing ${needle}, got success`)
  assert.match(String(result.error.message), new RegExp(needle))
}

async function withGuard(scenario, plugins, body) {
  const ctx = new Context()
  await ctx.plugin(LlmRuntime)
  for (const plugin of plugins) await ctx.plugin(plugin)
  await ctx.plugin(guard, scenario.guardConfig)
  try {
    return await body(ctx)
  } finally {
    await ctx.fiber.dispose()
  }
}

test('F1 provider-internal automatic retry is refused (maxRetries must be 0)', async () => {
  const scenario = makeScenario('normal')
  const captured = captureStderr()
  let result
  try {
    await withGuard(scenario, [scriptedPlugin({ maxRetries: 1 })], async (ctx) => {
      result = await collect(ctx.llm.stream(baseOptions()))
    })
  } finally {
    captured.restore()
  }
  expectError(result, 'RBG_PROVIDER_RETRY_POLICY_UNSAFE')
  assert.equal(adapterState.invocations, 0)
  assert.deepEqual(readRequests(scenario.requestsPath), [])
})

test('F1 guard config rejects a nonzero maxProviderRetries (fail-closed)', async () => {
  const scenario = makeScenario('normal', { maxProviderRetries: 1 })
  const captured = captureStderr()
  let result
  try {
    await withGuard(scenario, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      result = await collect(ctx.llm.stream(baseOptions()))
    })
  } finally {
    captured.restore()
  }
  expectError(result, 'RBG_GUARD_BOOT_INVALID')
  assert.equal(adapterState.invocations, 0)
  assert.deepEqual(readRequests(scenario.requestsPath), [])
  assert.ok(dataLines(captured, 'BOOT_INVALID').length >= 1)
})

test('F1 two logical streams consume two request/step slots; retry is attribution-only', async () => {
  const scenario = makeScenario('normal')
  const captured = captureStderr()
  try {
    await withGuard(scenario, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      const first = await collect(ctx.llm.stream(baseOptions()))
      const second = await collect(ctx.llm.stream(baseOptions()))
      assert.equal(first.error, null)
      assert.equal(second.error, null)
      assert.equal(adapterState.invocations, 2)
    })
    const requests = readRequests(scenario.requestsPath)
    const reserves = requests.filter((request) => request.op === 'reserve')
    assert.equal(reserves.length, 2)
    for (const reserve of reserves) {
      assert.equal(reserve.retry, false)
      assert.match(reserve.task_id, /^rbg-[0-9a-f]{64}$/)
      for (const key of Object.keys(reserve)) assert.ok(!key.startsWith('attempt'), `unexpected attempt metadata ${key}`)
    }
    assert.equal(reserves[0].task_id, reserves[1].task_id)
    const boot = dataLines(captured, 'BOOT')[0]
    assert.equal(boot.provider_auto_retry, 'disabled')
    assert.match(boot.retry_field_semantics, /attribution-only/)
  } finally {
    captured.restore()
  }
})

test('F3 maxTokens mutation is post-hoc REQUEST_INTEGRITY_UNCERTAIN, not pre-send interception', async () => {
  const scenario = makeScenario('normal')
  const captured = captureStderr()
  let result
  try {
    await withGuard(scenario, [scriptedPlugin({ maxRetries: 0 }), mutatePlugin((options) => { options.maxTokens = 1 })], async (ctx) => {
      result = await collect(ctx.llm.stream(baseOptions()))
    })
    expectError(result, 'RBG_REQUEST_INTEGRITY_UNCERTAIN')
    const events = dataLines(captured, 'REQUEST_INTEGRITY_UNCERTAIN')
    assert.equal(events.length, 1)
    assert.equal(events[0].interception, 'post-hoc-only')
    assert.equal(events[0].accounting_status_after_settle, 'WORST_CASE_HELD')
    const results = dataLines(captured, 'RESULT')
    assert.equal(results.length, 1)
    assert.equal(results[0].accounting_status, 'WORST_CASE_HELD')
    assert.equal(results[0].integrity_uncertain, true)
    // The scripted provider WAS entered: this test must not claim a pre-send block.
    assert.equal(adapterState.invocations, 1)
    const requests = readRequests(scenario.requestsPath)
    assert.deepEqual(requests.map((request) => request.op), ['reserve', 'fail'])
  } finally {
    captured.restore()
  }
})

test('F3 tools mutation is also reported post-hoc as uncertain', async () => {
  const scenario = makeScenario('normal')
  const captured = captureStderr()
  let result
  try {
    await withGuard(scenario, [scriptedPlugin({ maxRetries: 0 }), mutatePlugin((options) => {
      options.tools = [{ name: 'sk-FAKE-SECRET-TOOL', description: 'mutated', parameters: {} }]
    })], async (ctx) => {
      result = await collect(ctx.llm.stream(baseOptions()))
    })
    expectError(result, 'RBG_REQUEST_INTEGRITY_UNCERTAIN')
    assert.equal(adapterState.invocations, 1)
    const results = dataLines(captured, 'RESULT')
    assert.equal(results[0].accounting_status, 'WORST_CASE_HELD')
  } finally {
    captured.restore()
  }
})

test('F3 provider mutation is reported post-hoc as uncertain (no pre-send claim)', async () => {
  const scenario = makeScenario('normal')
  const captured = captureStderr()
  let result
  try {
    await withGuard(scenario, [scriptedPlugin({ maxRetries: 0 }), mutatePlugin((options) => { options.provider = 'mutated-route' })], async (ctx) => {
      result = await collect(ctx.llm.stream(baseOptions()))
    })
    expectError(result, 'RBG_REQUEST_INTEGRITY_UNCERTAIN')
    const events = dataLines(captured, 'REQUEST_INTEGRITY_UNCERTAIN')
    assert.equal(events.length, 1)
    assert.equal(events[0].interception, 'post-hoc-only')
    const results = dataLines(captured, 'RESULT')
    assert.equal(results[0].accounting_status, 'WORST_CASE_HELD')
    // The mutated route never reaches the scripted provider; this fact is NOT
    // used to claim any pre-send interception.
    assert.equal(adapterState.invocations, 0)
  } finally {
    captured.restore()
  }
})

test('F4 settlement uncertainty is machine readable, fails the call, and latches later dispatch', async () => {
  const scenario = makeScenario('settle-die-secret')
  const captured = captureStderr()
  let first
  let second
  try {
    await withGuard(scenario, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      first = await collect(ctx.llm.stream(baseOptions()))
      second = await collect(ctx.llm.stream(baseOptions()))
    })
    expectError(first, 'RBG_SETTLEMENT_UNCERTAIN')
    assert.equal(adapterState.invocations, 1)
    const results = dataLines(captured, 'RESULT')
    assert.equal(results.length, 2)
    assert.equal(results[0].model_completion_status, 'COMPLETED')
    assert.equal(results[0].accounting_status, 'SETTLEMENT_UNCERTAIN')
    assert.equal(results[0].settlement_uncertain, true)
    // The explicit fail-closed latch refuses the following dispatch before any
    // provider entry: no second provider invocation and no second reserve grant.
    assert.ok(second.error !== null)
    assert.equal(adapterState.invocations, 1)
    const requests = readRequests(scenario.requestsPath)
    assert.equal(requests.filter((request) => request.op === 'reserve').length, 1)
    assert.ok(dataLines(captured, 'UNAVAILABLE').some((event) => event.latch === true && event.phase === 'SETTLING'))
  } finally {
    captured.restore()
  }
})

test('F5 task id is stable, injective and process-independent', async () => {
  const ids = ['a/b', 'a_b', 'x'.repeat(200) + '-a', 'x'.repeat(200) + '-b', 'sessión/é', 'sessión/è']
  const encoded = ids.map((id) => guard.__test.encodeTaskId(id))
  assert.equal(new Set(encoded).size, ids.length)
  for (let index = 0; index < ids.length; index += 1) {
    const expected = `rbg-${sha256(Buffer.from(ids[index].normalize('NFC'), 'utf8')).slice(0, 64)}`
    assert.equal(encoded[index], expected)
    assert.match(encoded[index], /^rbg-[0-9a-f]{64}$/)
    assert.ok(encoded[index].length <= 96)
  }
  const guardUrl = pathToFileURL(guardLib).href
  const script = `import(${JSON.stringify(guardUrl)}).then(module => process.stdout.write(JSON.stringify(${JSON.stringify(ids)}.map(id => module.__test.encodeTaskId(id)))))`
  const first = execFileSync('/usr/bin/node', ['-e', script], { encoding: 'utf8' })
  const second = execFileSync('/usr/bin/node', ['-e', script], { encoding: 'utf8' })
  assert.equal(first, second)
  assert.deepEqual(JSON.parse(first), encoded)
})

test('F5 the same session id maps to the same task id across scopes', async () => {
  const left = makeScenario('normal', { scope: 'scope-left' })
  const right = makeScenario('normal', { scope: 'scope-right' })
  try {
    await withGuard(left, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      assert.equal((await collect(ctx.llm.stream(baseOptions({ sessionId: 'shared-session' })))).error, null)
    })
    await withGuard(right, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      assert.equal((await collect(ctx.llm.stream(baseOptions({ sessionId: 'shared-session' })))).error, null)
    })
    const taskId = (scenario) => readRequests(scenario.requestsPath).find((request) => request.op === 'reserve').task_id
    assert.equal(taskId(left), taskId(right))
    assert.match(taskId(left), /^rbg-[0-9a-f]{64}$/)
  } finally {
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
})

test('F6 failure logs use accurate phases and never a fixed not-dispatched boolean', async () => {
  const beforeScenario = makeScenario('reserve-die')
  const beforeCapture = captureStderr()
  let beforeResult
  try {
    await withGuard(beforeScenario, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      beforeResult = await collect(ctx.llm.stream(baseOptions()))
    })
  } finally {
    beforeCapture.restore()
  }
  expectError(beforeResult, 'RBG_')
  const beforeFailures = dataLines(beforeCapture, 'UNAVAILABLE')
  assert.equal(beforeFailures.length, 1)
  assert.equal(beforeFailures[0].phase, 'BEFORE_DISPATCH')
  assert.equal(beforeFailures[0].dispatched, false)
  assert.equal(Object.hasOwn(beforeFailures[0], 'reservations_not_dispatched'), false)

  const afterScenario = makeScenario('settle-die-secret')
  const afterCapture = captureStderr()
  let afterResult
  try {
    await withGuard(afterScenario, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      afterResult = await collect(ctx.llm.stream(baseOptions()))
    })
  } finally {
    afterCapture.restore()
  }
  expectError(afterResult, 'RBG_SETTLEMENT_UNCERTAIN')
  const afterFailures = dataLines(afterCapture, 'UNAVAILABLE')
  assert.equal(afterFailures.length, 1)
  assert.equal(afterFailures[0].phase, 'SETTLING')
  assert.equal(afterFailures[0].dispatched, true)
  assert.equal(Object.hasOwn(afterFailures[0], 'reservations_not_dispatched'), false)
})

test('F6 public logs never contain the sk-FAKE-SECRET sentinel', async () => {
  const scenario = makeScenario('settle-die-secret')
  const captured = captureStderr()
  try {
    await withGuard(scenario, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      await collect(ctx.llm.stream(baseOptions({ sessionId: 'sk-FAKE-SECRET-SESSION' })))
    })
    const publicText = captured.lines.join('')
    assert.ok(!publicText.includes('sk-FAKE-SECRET'), 'public stderr leaked the key sentinel')
    assert.match(publicText, /session_id_hash/)
    const events = dataLines(captured, 'UNAVAILABLE')
    assert.ok(events.length >= 1)
    assert.ok(events[0].stderr.count >= 1)
    assert.match(events[0].stderr.sha256, /^[0-9a-f]{64}$/)
  } finally {
    captured.restore()
  }
})

test('F6 raw broker stderr only reaches the opt-in restricted diagnostics file', async () => {
  const scenario = makeScenario('reserve-die')
  const rawPath = join(scenario.base, 'raw-diagnostics.log')
  const captured = captureStderr()
  const previous = process.env.RBG_RAW_DIAGNOSTICS_PATH
  process.env.RBG_RAW_DIAGNOSTICS_PATH = rawPath
  try {
    await withGuard(scenario, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      await collect(ctx.llm.stream(baseOptions()))
    })
  } finally {
    captured.restore()
    if (previous === undefined) delete process.env.RBG_RAW_DIAGNOSTICS_PATH
    else process.env.RBG_RAW_DIAGNOSTICS_PATH = previous
  }
  const raw = readFileSync(rawPath, 'utf8')
  assert.match(raw, /sk-FAKE-SECRET-STDERR/)
  assert.equal(statSync(rawPath).mode & 0o777, 0o600)
  const events = dataLines(captured, 'UNAVAILABLE')
  assert.equal(events[0].stderr.restricted_file, true)
  assert.ok(!captured.lines.join('').includes('sk-FAKE-SECRET-STDERR'))
})

test('F2 guard rejects broker max_messages above the broker hard bound', async () => {
  const scenario = makeScenario('normal', { max_messages: 100_001 })
  const captured = captureStderr()
  let result
  try {
    await withGuard(scenario, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      result = await collect(ctx.llm.stream(baseOptions()))
    })
  } finally {
    captured.restore()
  }
  expectError(result, 'RBG_GUARD_BOOT_INVALID')
  assert.equal(adapterState.invocations, 0)
  assert.deepEqual(readRequests(scenario.requestsPath), [])
})

test('F2 guard accepts the broker hard bound 100000', async () => {
  const scenario = makeScenario('normal', { max_messages: 100_000 })
  const captured = captureStderr()
  try {
    await withGuard(scenario, [scriptedPlugin({ maxRetries: 0 })], async (ctx) => {
      assert.equal((await collect(ctx.llm.stream(baseOptions()))).error, null)
    })
    assert.ok(dataLines(captured, 'BOOT').length === 1)
  } finally {
    captured.restore()
  }
})

test('provider stream error after dispatch is not logged with raw message text', async () => {
  const scenario = makeScenario('normal')
  const captured = captureStderr()
  let result
  try {
    await withGuard(scenario, [scriptedPlugin({ maxRetries: 0, mode: 'error' })], async (ctx) => {
      result = await collect(ctx.llm.stream(baseOptions()))
    })
    // The locked runtime may surface a scripted provider failure as a thrown
    // error or as an error finish; either way the guard must report model error
    // + worst-case accounting and must not copy the raw provider message into
    // public RBG_* logs.
    const results = dataLines(captured, 'RESULT')
    assert.equal(results.length, 1)
    assert.equal(results[0].model_completion_status, 'ERROR')
    assert.equal(results[0].accounting_status, 'WORST_CASE_HELD')
    assert.ok(!captured.lines.join('').includes('sk-FAKE-SECRET-ERROR'))
    if (result.error !== null) assert.match(String(result.error.message), /scripted provider error/)
  } finally {
    captured.restore()
  }
})
