// This untrusted orchestrator must be invoked ONLY by the credential-free,
// no-network, non-root OS-isolated command documented in PLUGIN_NOTES.md.
import { cpSync, mkdirSync, readFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'

console.log(`ISOLATION ${JSON.stringify({ uid: process.getuid(), env: Object.keys(process.env).sort(), cgroupMemoryMax: readFileSync('/sys/fs/cgroup/memory.max', 'utf8').trim(), cgroupPidsMax: readFileSync('/sys/fs/cgroup/pids.max', 'utf8').trim(), cgroupCpuMax: readFileSync('/sys/fs/cgroup/cpu.max', 'utf8').trim() })}`)
const root = '/work/plugins/skill-lookup'
mkdirSync('/work/plugins', { recursive: true })
cpSync('/project/plugin', root, { recursive: true })
cpSync('/project/fixtures', '/work/fixtures', { recursive: true })
const commands = [
  ['--max-old-space-size=768', 'node_modules/typescript/bin/tsc', '-p', 'tsconfig.json'],
  ['scripts/copy-fixture.mjs'],
  ['--test', 'test/plugin.test.mjs'],
]
for (const args of commands) {
  console.log(`ISOLATED_COMMAND ${JSON.stringify([process.execPath, ...args])}`)
  const result = spawnSync(process.execPath, args, {
    cwd: root, env: { PATH: '/usr/bin', HOME: '/work' },
    encoding: 'utf8', timeout: 45_000, maxBuffer: 4 * 1024 * 1024,
  })
  process.stdout.write(result.stdout ?? '')
  process.stderr.write(result.stderr ?? '')
  console.log(`ISOLATED_EXIT ${result.status} SIGNAL ${result.signal ?? 'none'}`)
  if (result.error) console.error(String(result.error))
  if (result.status !== 0) process.exit(result.status ?? 1)
}
for (const path of ['index.js', 'index.d.ts', 'skills.json', 'fixture.sha256']) {
  const bytes = readFileSync(`${root}/lib/${path}`)
  console.log(`BUILD_ARTIFACT ${JSON.stringify({ path: `lib/${path}`, sha256: createHash('sha256').update(bytes).digest('hex'), base64: bytes.toString('base64') })}`)
}
