/**
 * G4-F2 adapter-boundary probe (no Key, no model, no network).
 *
 * Loads the frozen candidate-built bridge adapter and asks it for one call with
 * an auxiliary `purpose` ("title") and one conversation call. The title call
 * must fail with G3B_BRIDGE_PURPOSE before any AF_UNIX connect; the conversation
 * call must get past the purpose guard and fail only at the (absent) socket.
 * Nothing here reaches a provider, a model or an external network.
 */
import { pathToFileURL } from 'node:url'

const adapterPath = process.argv[2]
if (!adapterPath) {
  console.error('usage: adapter_purpose_probe.mjs <built-lib-index.js>')
  process.exit(2)
}
const mod = await import(pathToFileURL(adapterPath).href)
const adapter = new mod.BridgeAdapter()

const base = {
  sessionId: 'g4f2-adapter-probe',
  provider: mod.provider,
  model: mod.model,
  messages: [{ role: 'user', content: [{ type: 'text', text: 'G4F2_ADAPTER_PROBE' }] }],
  tools: [],
  system: null,
  maxTokens: 64,
}

async function probe(purpose) {
  const iterator = adapter.stream({ ...base, purpose })
  try {
    const first = await iterator.next()
    return { outcome: 'yielded', first }
  } catch (error) {
    return {
      outcome: 'error',
      name: error?.name ?? null,
      message: String(error?.message ?? error),
      code: error?.code ?? null,
    }
  }
}

const report = {
  adapter: adapterPath,
  provider: mod.provider,
  model: mod.model,
  bridge_socket: mod.BRIDGE_SOCKET,
  title: await probe('title'),
  conversation: await probe('conversation'),
}
console.log(JSON.stringify(report))
