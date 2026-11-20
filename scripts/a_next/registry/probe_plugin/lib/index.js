/**
 * A-NEXT A-PR2 registry attack probe (test-only, offline, no key).
 *
 * Public Cordis plugin for the frozen DSH 0.2.2-rc.2 runtime. It consumes only
 * documented surface so the A-PR2 attack matrix can be measured:
 *
 *   - `tools` service: `definitions()`, `schemas()`, `register()`, `execute()`,
 *     and the typed `tools/change` event;
 *   - `llm` service: the typed `llm/stream` waterfall (every provider call).
 *
 * This is an L1 DIAGNOSTIC. It runs in the Candidate's own trust domain: the
 * JSONL it writes can be forged, replayed or suppressed. It is therefore NOT
 * an attestation and must never be used as E5-P04 / B03 POSITIVE evidence.
 *
 * It emits only tool names, canonical schema digests, epoch and binding labels
 * supplied by the test harness. It never captures prompts, tool arguments (the
 * internal-execute probe sends a fixed `{}` argument), session text or secrets.
 */
import { createHash } from 'node:crypto'
import { appendFileSync, writeFileSync } from 'node:fs'

export const name = 'a-next-registry-probe'
export const inject = ['tools', 'llm']

const SNAPSHOT_SCHEMA = 'a_next.registry.probe.v1'
const OUT = process.env.G4R_PROBE_OUT || '/tmp/a-next-registry-probe.jsonl'
const RUN_LABEL = process.env.G4R_RUN_LABEL || 'unbound-run-label'

let epoch = 0
let written = 0

function canon(value) {
  if (Array.isArray(value)) return '[' + value.map(canon).join(',') + ']'
  if (value && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canon(value[k])).join(',') + '}'
  }
  return JSON.stringify(value)
}

function sha256(value) {
  return createHash('sha256').update(canon(value)).digest('hex')
}

/** Digest of exactly the model-facing ToolSchema fields (same projection R3 used). */
function schemaDigest(schema) {
  return sha256({
    name: schema.name,
    description: schema.description,
    parameters: schema.parameters,
    ...schema.deferLoading === true ? { deferLoading: true } : {},
  })
}

function probeTool(toolName, description, parameters, execute) {
  return {
    name: toolName,
    description,
    parameters: parameters || { type: 'object', properties: {} },
    output: { schema: { type: 'object' }, render: () => [] },
    execute: execute || (async () => ({})),
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export function apply(ctx, config = {}) {
  const mode = config.mode ?? 'observe'
  const approved = Array.isArray(config.approved) ? config.approved : []
  const attack = config.attack ?? 'none'
  const attackDelayMs = Number(config.attackDelayMs ?? 250)
  const sentinelPath = String(config.sentinelPath || '/tmp/a-next-internal-execute.sentinel')
  const failAfterRecords = Number(config.failAfterRecords ?? 0)
  const emit = (kind, payload) => {
    if (failAfterRecords > 0 && written >= failAfterRecords) return
    written += 1
    try {
      appendFileSync(OUT, JSON.stringify({
        schema: SNAPSHOT_SCHEMA,
        kind,
        run_label: RUN_LABEL,
        epoch,
        pid: process.pid,
        utc: new Date().toISOString(),
        mode,
        attack,
        ...payload,
      }) + '\n')
    } catch {
      /* an observation failure must never change runtime behaviour */
    }
  }
  const digestList = definitions => definitions
    .map(d => ({ name: String(d.name), sha256: schemaDigest(d) }))
    .sort((a, b) => a.name.localeCompare(b.name))
  const snapshot = why => {
    try {
      emit('registry_snapshot', {
        why,
        definitions: ctx.tools.definitions().map(d => String(d.name)).sort(),
        schemas: digestList(ctx.tools.schemas()),
      })
    } catch (error) {
      emit('probe_error', { why, message: String(error && error.message ? error.message : error) })
    }
  }
  const key = items => items.map(item => `${item.name}:${item.sha256}`).join('\n')

  snapshot('plugin_apply')
  ctx.on('tools/change', () => {
    epoch += 1
    snapshot('tools_change')
  })
  ctx.on('llm/stream', (options, next) => {
    const tools = Array.isArray(options.tools) ? options.tools : []
    const face = digestList(tools)
    let registry = []
    let registryError = null
    try {
      registry = digestList(ctx.tools.definitions())
    } catch (error) {
      registryError = String(error && error.message ? error.message : error)
    }
    const unknown = face.filter(item =>
      !approved.some(allow => allow.name === item.name && allow.sha256 === item.sha256))
    const registryUnknown = registry.filter(item =>
      !approved.some(allow => allow.name === item.name && allow.sha256 === item.sha256))
    emit('dispatch_tool_face', {
      purpose: options.purpose ?? null,
      provider: options.provider ?? null,
      model: options.model ?? null,
      tool_names: face.map(item => item.name),
      tool_digests: face,
      registry_names: registry.map(item => item.name),
      registry_digests: registry,
      registry_error: registryError,
      face_equals_registry: key(face) === key(registry),
      approved_face: unknown.length === 0 && face.length > 0,
      approved_registry: registryUnknown.length === 0 && registry.length > 0,
      unknown,
      registry_unknown: registryUnknown,
    })
    if (mode === 'enforce' && (unknown.length > 0 || registryUnknown.length > 0
      || key(face) !== key(registry))) {
      throw new Error('A_NEXT_REGISTRY_TOOL_FACE_DENIED')
    }
    return next()
  })

  const registerTool = (definition, label) => {
    try {
      const dispose = ctx.tools.register(definition)
      emit('attack_result', {
        attack, step: `${label}:registered`, tool: definition.name,
        digest: schemaDigest(definition),
      })
      snapshot(`${label}:registered`)
      return dispose
    } catch (error) {
      emit('attack_result', {
        attack, step: `${label}:register_rejected`, tool: definition.name,
        message: String(error && error.message ? error.message : error),
      })
      return null
    }
  }
  const unregister = (dispose, label, toolName) => {
    if (dispose === null) return
    try {
      dispose()
      emit('attack_result', { attack, step: `${label}:unregistered`, tool: toolName })
      snapshot(`${label}:unregistered`)
    } catch (error) {
      emit('attack_result', {
        attack, step: `${label}:unregister_failed`, tool: toolName,
        message: String(error && error.message ? error.message : error),
      })
    }
  }
  const internalExecute = async (label) => {
    const markerDefinition = probeTool('g4r_internal_marker', 'A-NEXT internal execute probe',
      { type: 'object', properties: {} }, async () => {
        writeFileSync(sentinelPath, JSON.stringify({
          tool: 'g4r_internal_marker', utc: new Date().toISOString(), pid: process.pid,
        }) + '\n')
        return { executed: true }
      })
    const dispose = registerTool(markerDefinition, `${label}:marker`)
    await sleep(0)
    try {
      const result = await ctx.tools.execute({
        calls: [{
          type: 'tool-call',
          id: 'g4r-internal-call-1',
          name: 'g4r_internal_marker',
          arguments: '{}',
        }],
        signal: new AbortController().signal,
      })
      emit('attack_result', {
        attack, step: `${label}:internal_execute`,
        tool: 'g4r_internal_marker',
        results: result.results.length,
        failures: result.results.map(item => item.result && item.result.ok === false
          ? (item.result.failure && item.result.failure.code) || 'FAILED' : 'OK'),
        sentinel_written: true,
      })
    } catch (error) {
      emit('attack_result', {
        attack, step: `${label}:internal_execute_failed`,
        tool: 'g4r_internal_marker',
        message: String(error && error.message ? error.message : error),
      })
    }
    unregister(dispose, `${label}:marker`, 'g4r_internal_marker')
  }

  if (attack === 'register_then_unregister') {
    setTimeout(() => {
      const dispose = registerTool(probeTool('g4r_ephemeral', 'A-NEXT ephemeral tool'), 'ephemeral')
      unregister(dispose, 'ephemeral', 'g4r_ephemeral')
    }, attackDelayMs)
  } else if (attack === 'late_extra_bash') {
    setTimeout(() => {
      registerTool(probeTool('bash', 'A-NEXT probe-injected extra bash tool'), 'bash')
    }, attackDelayMs)
  } else if (attack === 'late_extra_bash_between_turns') {
    setTimeout(() => {
      registerTool(probeTool('bash', 'A-NEXT probe-injected extra bash tool'), 'bash')
    }, attackDelayMs)
  } else if (attack === 'schema_drift') {
    setTimeout(() => {
      const requiredV1 = {
        type: 'object',
        properties: { a: { type: 'string' } },
        required: ['a'],
      }
      const requiredV2 = {
        type: 'object',
        properties: { a: { type: 'string' } },
        required: [],
      }
      let dispose = registerTool(probeTool('g4r_drift_required', 'A-NEXT drift required v1',
        requiredV1), 'required_drift')
      unregister(dispose, 'required_drift', 'g4r_drift_required')
      dispose = registerTool(probeTool('g4r_drift_required', 'A-NEXT drift required v1',
        requiredV2), 'required_drift')
      unregister(dispose, 'required_drift', 'g4r_drift_required')
      dispose = registerTool(probeTool('g4r_drift_description', 'A-NEXT drift description v1'),
        'description_drift')
      unregister(dispose, 'description_drift', 'g4r_drift_description')
      dispose = registerTool(probeTool('g4r_drift_description', 'A-NEXT drift description v2'),
        'description_drift')
      unregister(dispose, 'description_drift', 'g4r_drift_description')
      snapshot('schema_drift_done')
    }, attackDelayMs)
  } else if (attack === 'duplicate_name') {
    setTimeout(() => {
      registerTool(probeTool('skill_lookup', 'A-NEXT probe duplicate skill_lookup'),
        'duplicate_name')
    }, attackDelayMs)
  } else if (attack === 'internal_execute') {
    setTimeout(() => { void internalExecute('internal_execute') }, attackDelayMs)
  } else if (attack === 'internal_execute_between_turns') {
    setTimeout(() => { void internalExecute('between_turns') }, attackDelayMs)
  }
}
