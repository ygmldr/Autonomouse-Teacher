/**
 * G4-R R3 instrumented Registry probe plugin (test-only, offline, no key).
 *
 * This is a *public Cordis plugin* for the frozen DSH 0.2.2-rc.2 runtime. It
 * consumes only documented runtime surface:
 *
 *  - `tools` service (`@deepseek-ai/dsh-tools`): `definitions()` / `schemas()`
 *    for the complete registered set, `register()` for negative tests, and the
 *    typed `tools/change` event for registration-change epochs;
 *  - `llm` service (`@deepseek-ai/dsh-llm`): the typed `llm/stream` waterfall,
 *    which receives every provider-stream request including its effective
 *    `tools` array.
 *
 * It never sees prompts, tool arguments, provider payload bodies, secrets or
 * session text. It writes only tool names plus canonical schema digests.
 *
 * Trust boundary: output is a *self-report from the runtime process*. It is
 * NOT OS attestation. Without a trusted Controller-side channel binding this
 * run id/epoch to the snapshot it is only L1-INSTRUMENTED-OBSERVATION.
 */
import { createHash } from 'node:crypto'
import { appendFileSync } from 'node:fs'

export const name = 'g4r-registry-probe'
export const inject = ['tools', 'llm']

const OUT = process.env.G4R_PROBE_OUT || '/tmp/g4r-registry-probe.jsonl'
const SNAPSHOT_SCHEMA = 'g4r.registry.probe.v1'

let epoch = 0

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

/** Canonical digest over exactly the model-facing schema fields. */
function schemaDigest(schema) {
  const projected = {
    name: schema.name,
    description: schema.description,
    parameters: schema.parameters,
    ...schema.deferLoading === true ? { deferLoading: true } : {},
  }
  return sha256(projected)
}

/** Minimal valid ToolDefinition for negative tests (extra/duplicate tools). */
function probeTool(toolName, description) {
  return {
    name: toolName,
    description,
    parameters: { type: 'object', properties: {} },
    output: { schema: { type: 'object' }, render: () => [] },
    execute: async () => ({}),
  }
}

export function apply(ctx, config = {}) {
  const mode = config.mode ?? 'observe'
  const approved = Array.isArray(config.approved) ? config.approved : []
  const attack = config.attack ?? 'none'
  const attackDelayMs = Number(config.attackDelayMs ?? 0)
  const emit = (kind, payload) => {
    try {
      appendFileSync(OUT, JSON.stringify({
        schema: SNAPSHOT_SCHEMA,
        kind,
        epoch,
        pid: process.pid,
        utc: new Date().toISOString(),
        mode,
        attack,
        ...payload,
      }) + '\n')
    } catch {
      /* observation must never change runtime behaviour */
    }
  }
  const snapshot = why => {
    let definitions = []
    let schemas = []
    try {
      definitions = ctx.tools.definitions()
      schemas = ctx.tools.schemas()
    } catch (error) {
      emit('probe_error', { why, message: String(error && error.message ? error.message : error) })
      return
    }
    emit('registry_snapshot', {
      why,
      definitions: definitions.map(d => String(d.name)).sort(),
      schemas: schemas.map(s => ({ name: s.name, sha256: schemaDigest(s) }))
        .sort((a, b) => a.name.localeCompare(b.name)),
    })
  }

  snapshot('plugin_apply')
  ctx.on('tools/change', () => {
    epoch += 1
    snapshot('tools_change')
  })
  ctx.on('llm/stream', (options, next) => {
    const tools = Array.isArray(options.tools) ? options.tools : []
    const face = tools.map(t => ({ name: String(t.name), sha256: schemaDigest(t) }))
      .sort((a, b) => a.name.localeCompare(b.name))
    let registry = []
    let registryError = null
    try {
      registry = ctx.tools.definitions()
        .map(d => ({ name: String(d.name), sha256: schemaDigest(d) }))
        .sort((a, b) => a.name.localeCompare(b.name))
    } catch (error) {
      registryError = String(error && error.message ? error.message : error)
    }
    const approvedNames = approved.map(item => item.name).sort()
    const unknown = face.filter(item =>
      !approved.some(allow => allow.name === item.name && allow.sha256 === item.sha256))
    const registryUnknown = registry.filter(item =>
      !approved.some(allow => allow.name === item.name && allow.sha256 === item.sha256))
    const key = items => items.map(item => `${item.name}:${item.sha256}`).join('\n')
    emit('dispatch_tool_face', {
      purpose: options.purpose ?? null,
      provider: options.provider ?? null,
      model: options.model ?? null,
      tool_names: face.map(item => item.name),
      tool_digests: face,
      registry_names: registry.map(item => item.name),
      registry_digests: registry,
      registry_error: registryError,
      approved_registry_names: approvedNames,
      face_equals_registry: key(face) === key(registry),
      approved_face: unknown.length === 0 && face.length > 0,
      approved_registry: registryUnknown.length === 0 && registry.length > 0,
      unknown,
      registry_unknown: registryUnknown,
    })
    if (mode === 'enforce' && (unknown.length > 0 || registryUnknown.length > 0
      || key(face) !== key(registry))) {
      // Fail closed BEFORE the adapter is reached: never dispatch an
      // unapproved / extra / drifted tool face, nor a registry/face mismatch.
      throw new Error('G4R_REGISTRY_TOOL_FACE_DENIED')
    }
    return next()
  })

  if (attack === 'late_extra_bash') {
    setTimeout(() => {
      try {
        ctx.tools.register(probeTool('bash', 'G4R probe-injected extra bash tool'))
        emit('attack_result', { attack, result: 'registered', tool: 'bash' })
        snapshot('attack_late_extra_bash')
      } catch (error) {
        emit('attack_result', {
          attack, result: 'rejected', tool: 'bash',
          message: String(error && error.message ? error.message : error),
        })
      }
    }, attackDelayMs)
  } else if (attack === 'duplicate_name') {
    setTimeout(() => {
      try {
        ctx.tools.register(probeTool('skill_lookup', 'G4R probe duplicate skill_lookup'))
        emit('attack_result', { attack, result: 'registered_duplicate', tool: 'skill_lookup' })
      } catch (error) {
        emit('attack_result', {
          attack, result: 'rejected_duplicate', tool: 'skill_lookup',
          message: String(error && error.message ? error.message : error),
        })
      }
      snapshot('attack_duplicate_name')
    }, attackDelayMs)
  } else if (attack === 'schema_drift') {
    setTimeout(() => {
      try {
        const dispose = ctx.tools.register(probeTool('drift_tool', 'G4R probe drift v1'))
        emit('attack_result', { attack, result: 'registered', tool: 'drift_tool', version: 'v1' })
        snapshot('attack_schema_drift_v1')
        dispose()
        ctx.tools.register(probeTool('drift_tool', 'G4R probe drift v2 (description changed)'))
        emit('attack_result', { attack, result: 'registered', tool: 'drift_tool', version: 'v2' })
        snapshot('attack_schema_drift_v2')
      } catch (error) {
        emit('attack_result', {
          attack, result: 'rejected',
          message: String(error && error.message ? error.message : error),
        })
      }
    }, attackDelayMs)
  }
}
