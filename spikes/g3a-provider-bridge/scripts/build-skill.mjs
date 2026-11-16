/** Container-only rebuild of the reviewed skill-lookup plugin against locked DSH 0.2.2-rc.2 types. */
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'

const SRC = '/src'
const NPM = '/npm'
const FIXTURES = '/fixtures'
const OUT = '/out'
const WORK = '/work/g3a-skill-build'

if (!process.env['G3A_BUILD_IN_CONTAINER']) throw new Error('G3A_BUILD_CONTAINER_ONLY')
const dshTools = JSON.parse(readFileSync(`${NPM}/@deepseek-ai/dsh-tools/package.json`, 'utf8'))
const typescript = JSON.parse(readFileSync(`${NPM}/typescript/package.json`, 'utf8'))
if (dshTools.version !== '0.2.2-rc.2' || typescript.version !== '5.9.3') throw new Error('G3A_SKILL_BUILD_VERSION_MISMATCH')
rmSync(WORK, { recursive: true, force: true })
mkdirSync(WORK, { recursive: true })
cpSync(`${SRC}/src`, `${WORK}/src`, { recursive: true })
cpSync(`${SRC}/tsconfig.json`, `${WORK}/tsconfig.json`)
cpSync(`${SRC}/package.json`, `${WORK}/package.json`)
cpSync(NPM, `${WORK}/node_modules`, { recursive: true })
const env = { PATH: '/usr/bin', HOME: '/work', TMPDIR: '/tmp', PYTHONDONTWRITEBYTECODE: '1' }
const built = spawnSync(process.execPath, [`${NPM}/typescript/bin/tsc`, '-p', `${WORK}/tsconfig.json`], { cwd: WORK, env, stdio: 'inherit' })
if (built.status !== 0) process.exit(built.status ?? 1)
cpSync(`${FIXTURES}/skills.json`, `${WORK}/lib/skills.json`)
const fixtureBytes = readFileSync(`${FIXTURES}/skills.json`)
writeFileSync(`${WORK}/lib/fixture.sha256`, `${createHash('sha256').update(fixtureBytes).digest('hex')}  skills.json\n`)
rmSync(`${OUT}/lib`, { recursive: true, force: true })
cpSync(`${WORK}/lib`, `${OUT}/lib`, { recursive: true })
const meta = {
  kind: 'g3a-skill-build',
  createdUtc: new Date().toISOString(),
  node: process.version,
  typescript: typescript.version,
  dshToolsVersion: dshTools.version,
  sourceSha256: createHash('sha256').update(readFileSync(`${SRC}/src/index.ts`)).digest('hex'),
  builtJs: { path: 'lib/index.js', sha256: createHash('sha256').update(readFileSync(`${OUT}/lib/index.js`)).digest('hex') },
  builtSkills: { path: 'lib/skills.json', sha256: createHash('sha256').update(readFileSync(`${OUT}/lib/skills.json`)).digest('hex') },
  synthetic: true,
}
writeFileSync(`${OUT}/build-meta.json`, `${JSON.stringify(meta, null, 2)}\n`)
process.stdout.write(`G3A_SKILL_BUILD_OK ${JSON.stringify(meta)}\n`)
