/**
 * Container-only build for the G3-B trusted-bridge adapter.
 * Inputs: /src (spike source, ro), /npm (locked 0.2.2-rc.2 TS toolchain, ro),
 * /out (evidence stage, rw). Writes only /work (noexec tmpfs) and /out.
 */
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'

const SRC = '/src'
const NPM = '/npm'
const OUT = '/out'
const WORK = '/work/g3b-build'
if (!process.env['G3B_BUILD_IN_CONTAINER']) throw new Error('G3B_BUILD_CONTAINER_ONLY')
function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}
const dshLlm = JSON.parse(readFileSync(`${NPM}/@deepseek-ai/dsh-llm/package.json`, 'utf8'))
const typescript = JSON.parse(readFileSync(`${NPM}/typescript/package.json`, 'utf8'))
if (dshLlm.version !== '0.2.2-rc.2' || typescript.version !== '5.9.3') {
  throw new Error('G3B_BUILD_DEPENDENCY_VERSION_MISMATCH')
}
rmSync(WORK, { recursive: true, force: true })
mkdirSync(WORK, { recursive: true })
cpSync(`${SRC}/src`, `${WORK}/src`, { recursive: true })
cpSync(`${SRC}/tsconfig.json`, `${WORK}/tsconfig.json`)
cpSync(`${SRC}/package.json`, `${WORK}/package.json`)
cpSync(NPM, `${WORK}/node_modules`, { recursive: true })

const env = { PATH: '/usr/bin', HOME: '/work', TMPDIR: '/tmp', PYTHONDONTWRITEBYTECODE: '1' }
const tscVersion = spawnSync(process.execPath, [`${NPM}/typescript/bin/tsc`, '--version'], { encoding: 'utf8', env })
const built = spawnSync(process.execPath, [`${NPM}/typescript/bin/tsc`, '-p', `${WORK}/tsconfig.json`], {
  cwd: WORK, env, stdio: 'inherit',
})
if (built.status !== 0) process.exit(built.status ?? 1)

rmSync(`${OUT}/lib`, { recursive: true, force: true })
cpSync(`${WORK}/lib`, `${OUT}/lib`, { recursive: true })
const meta = {
  kind: 'g3b-trusted-bridge-build',
  createdUtc: new Date().toISOString(),
  node: process.version,
  typescript: tscVersion.stdout.trim(),
  dshLlmVersion: dshLlm.version,
  dshLlmPackageJsonSha256: sha256(`${NPM}/@deepseek-ai/dsh-llm/package.json`),
  inputSourceSha256: sha256(`${SRC}/src/index.ts`),
  builtJs: { path: 'lib/index.js', sha256: sha256(`${OUT}/lib/index.js`), bytes: readFileSync(`${OUT}/lib/index.js`).length },
  builtDts: { path: 'lib/index.d.ts', sha256: sha256(`${OUT}/lib/index.d.ts`), bytes: readFileSync(`${OUT}/lib/index.d.ts`).length },
  synthetic: true,
}
writeFileSync(`${OUT}/build-meta.json`, `${JSON.stringify(meta, null, 2)}\n`)
process.stdout.write(`G3B_BUILD_OK ${JSON.stringify(meta)}\n`)
