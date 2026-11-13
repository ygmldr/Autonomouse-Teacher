// Real official services; no hand-written ABI, mock tools registry, or LLM.
import { Context } from '@deepseek-ai/cordis'
import { ToolRuntime } from '@deepseek-ai/dsh-tools'
import { SystemPrompt } from '@deepseek-ai/dsh-system-prompt'
import * as plugin from '../lib/index.js'

export async function boot() {
  const ctx = new Context()
  try {
    await ctx.plugin(SystemPrompt, { includeHarnessIdentity: false })
    await ctx.plugin(ToolRuntime, { mode: 'native' })
    const fiber = await ctx.plugin(plugin)
    return { ctx, fiber, close: () => ctx.fiber.dispose() }
  } catch (error) {
    await ctx.fiber.dispose()
    throw error
  }
}

let serial = 0
export function call(ctx, args) {
  return ctx.tools.execute({
    callId: `offline-${++serial}`,
    name: 'skill_lookup',
    arguments: args,
    signal: new AbortController().signal,
  })
}
