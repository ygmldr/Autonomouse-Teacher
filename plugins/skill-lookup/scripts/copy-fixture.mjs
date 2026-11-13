// Run ONLY inside the reviewed credential-free build sandbox, never via lifecycle.
import { copyFile, readFile, writeFile, chmod } from 'node:fs/promises'
import { createHash } from 'node:crypto'

const source = new URL('../../../fixtures/skills.json', import.meta.url)
const destination = new URL('../lib/skills.json', import.meta.url)
const bytes = await readFile(source)
// The package carries a fixed snapshot, not a caller-configurable filesystem path.
JSON.parse(bytes.toString('utf8'))
await copyFile(source, destination)
await chmod(destination, 0o444)
await writeFile(new URL('../lib/fixture.sha256', import.meta.url),
  `${createHash('sha256').update(bytes).digest('hex')}  skills.json\n`)
