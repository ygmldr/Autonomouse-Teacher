import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createHash } from 'node:crypto'
import { readFileSync, statSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { validateJsonSchemaValue } from '@deepseek-ai/dsh-tools'
import * as plugin from '../lib/index.js'
import { boot, call } from './runtime.mjs'

const fixtureUrl = new URL('../lib/skills.json', import.meta.url)
const sourceUrl = new URL('../../../fixtures/skills.json', import.meta.url)
const digest = bytes => createHash('sha256').update(bytes).digest('hex')
const fixture = JSON.parse(readFileSync(fixtureUrl, 'utf8'))
const expected = fixture.skills.find(skill => skill.id === 'binary_search')
assert.ok(expected)

async function withRuntime(body) {
  const runtime = await boot()
  try { await body(runtime) } finally { await runtime.close() }
}

test('E2-01: real Cordis injection and model-facing official registry schema', async () => {
  await withRuntime(async ({ ctx }) => {
    assert.equal(plugin.name, 'autoteacher-skill-lookup')
    assert.deepEqual(plugin.inject, ['tools'])
    const schemas = ctx.tools.schemas()
    assert.deepEqual(schemas.map(schema => schema.name), ['skill_lookup'])
    const schema = schemas[0]
    assert.equal(schema.parameters.type, 'object')
    assert.equal(schema.parameters.properties.skill_id.type, 'string')
    assert.deepEqual(schema.parameters.required, ['skill_id'])
    assert.equal('execute' in schema, false)
    const assembly = await ctx.systemPrompt.assemble()
    assert.deepEqual(assembly.tools.map(tool => tool.name), ['skill_lookup'])
    const events = []
    ctx.on('tools/result', (execution, outcome) => {
      events.push({ name: execution.name, arguments: execution.arguments, isError: outcome.isError })
    })
    const result = await call(ctx, { skill_id: 'binary_search' })
    assert.equal(result.isError, false)
    assert.deepEqual(result.value, expected)
    assert.deepEqual(events, [{ name: 'skill_lookup', arguments: { skill_id: 'binary_search' }, isError: false }])
    assert.deepEqual(result.content, [{ type: 'text', text: JSON.stringify(expected) }])
    assert.deepEqual(result.value.prerequisites, ['ordered_search_space', 'monotonicity', 'loop_invariants'])
  })
})

test('E2-02: arbitrary nonempty unknown id is a canonical not-found, not an exception', async () => {
  await withRuntime(async ({ ctx }) => {
    for (const skill_id of ['unknown_skill', '__proto__', '../../etc/passwd', ' binary_search ']) {
      const result = await call(ctx, { skill_id })
      assert.equal(result.isError, false)
      assert.deepEqual(result.value, { error: 'SKILL_NOT_FOUND', skill_id, source_version: 'm0-skills-v1' })
    }
  })
})

test('E2-03a: official input schema rejects missing and wrong-type ids', async () => {
  await withRuntime(async ({ ctx }) => {
    const schema = ctx.tools.schemas()[0].parameters
    for (const args of [{}, { skill_id: 123 }, { skill_id: null }, { skill_id: [] }, { skill_id: {} }]) {
      assert.notEqual(validateJsonSchemaValue(schema, args).length, 0)
      const result = await call(ctx, args)
      assert.equal(result.isError, true)
      assert.equal(result.error.info.code, 'INVALID_ARGS')
      assert.equal('value' in result, false)
    }
  })
})

test('E2-03b: blank id is rejected by project semantic validation, NOT native wire schema', async () => {
  await withRuntime(async ({ ctx }) => {
    const schema = ctx.tools.schemas()[0].parameters
    for (const skill_id of ['', ' ', '\t\n']) {
      // Deliberately expose the upstream limitation: no minLength/pattern support.
      assert.deepEqual(validateJsonSchemaValue(schema, { skill_id }), [])
      const result = await call(ctx, { skill_id })
      assert.equal(result.isError, true)
      assert.equal(result.error.info.code, 'INVALID_ARGS')
      assert.match(result.error.message, /non-whitespace/)
    }
  })
})

test('E2-04a: official fiber restart preserves result without duplicate registration', async () => {
  await withRuntime(async ({ ctx, fiber }) => {
    const initial = await call(ctx, { skill_id: 'binary_search' })
    for (let attempt = 0; attempt < 3; attempt++) {
      await fiber.restart()
      assert.equal(ctx.tools.schemas().filter(tool => tool.name === 'skill_lookup').length, 1)
      assert.deepEqual(await call(ctx, { skill_id: 'binary_search' }), initial)
    }
  })
})

test('E2-04b: two fresh OS processes produce the same deterministic official registry result', () => {
  const outputs = []
  for (let attempt = 0; attempt < 2; attempt++) {
    const child = spawnSync(process.execPath, [fileURLToPath(new URL('./restart-probe.mjs', import.meta.url))], {
      env: {}, encoding: 'utf8', timeout: 10_000,
    })
    assert.equal(child.error, undefined)
    assert.equal(child.status, 0, child.stderr)
    outputs.push(JSON.parse(child.stdout))
  }
  assert.deepEqual(outputs[0], expected)
  assert.deepEqual(outputs[1], expected)
})

test('E2-05: unload unregisters, denies dispatch and clears model visibility; remount is single', async () => {
  await withRuntime(async ({ ctx, fiber }) => {
    await fiber.dispose()
    assert.equal(ctx.tools.get('skill_lookup'), undefined)
    assert.deepEqual(ctx.tools.schemas(), [])
    assert.deepEqual((await ctx.systemPrompt.assemble()).tools, [])
    const result = await call(ctx, { skill_id: 'binary_search' })
    assert.equal(result.isError, true)
    assert.equal(result.error.info.code, 'UNKNOWN_TOOL')
    const remounted = await ctx.plugin(plugin)
    assert.equal(ctx.tools.schemas().length, 1)
    assert.equal((await call(ctx, { skill_id: 'binary_search' })).isError, false)
    await remounted.dispose()
    assert.deepEqual(ctx.tools.schemas(), [])
  })
})

test('fixture is a versioned read-only copy and calls cannot mutate its bytes or snapshot', async () => {
  const before = readFileSync(fixtureUrl)
  assert.equal(digest(before), digest(readFileSync(sourceUrl)))
  assert.equal(statSync(fixtureUrl).mode & 0o222, 0)
  assert.equal(readFileSync(new URL('../lib/fixture.sha256', import.meta.url), 'utf8'), `${digest(before)}  skills.json\n`)
  await withRuntime(async ({ ctx }) => {
    const first = await call(ctx, { skill_id: 'binary_search' })
    assert.equal(Object.isFrozen(first.value), true)
    assert.throws(() => first.value.prerequisites.push('mutation'), TypeError)
    assert.deepEqual((await call(ctx, { skill_id: 'binary_search' })).value, expected)
  })
  assert.equal(digest(readFileSync(fixtureUrl)), digest(before))
})
