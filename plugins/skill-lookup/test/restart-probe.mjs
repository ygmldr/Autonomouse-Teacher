import assert from 'node:assert/strict'
import { boot, call } from './runtime.mjs'

const runtime = await boot()
try {
  assert.equal(runtime.ctx.tools.schemas().filter(x => x.name === 'skill_lookup').length, 1)
  const result = await call(runtime.ctx, { skill_id: 'binary_search' })
  assert.equal(result.isError, false)
  process.stdout.write(`${JSON.stringify(result.value)}\n`)
} finally {
  await runtime.close()
}
