import type { Context } from '@deepseek-ai/cordis'
import { defineTool, ToolArgsError } from '@deepseek-ai/dsh-tools'
import { closeSync, constants, fstatSync, openSync, readFileSync } from 'node:fs'

export const name = 'autoteacher-skill-lookup'
export const inject = ['tools']
export const fixtureVersion = 'm0-skills-v1'

export interface SkillInfo {
  id: string
  title: string
  prerequisites: string[]
  objectives: string[]
  source_version: string
}

type FrozenSkill = Readonly<Omit<SkillInfo, 'prerequisites' | 'objectives'>> & {
  readonly prerequisites: readonly string[]
  readonly objectives: readonly string[]
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string' && item.trim().length > 0)
}

/** Read one fixed packaged snapshot at activation; no caller path or write APIs. */
function loadSkills(): ReadonlyMap<string, FrozenSkill> {
  const fd = openSync(new URL('./skills.json', import.meta.url), constants.O_RDONLY | constants.O_NOFOLLOW)
  let parsed: unknown
  try {
    const stat = fstatSync(fd)
    if (!stat.isFile() || stat.size > 65_536) throw new Error('INVALID_SKILL_FIXTURE')
    parsed = JSON.parse(readFileSync(fd, 'utf8')) as unknown
  } finally {
    closeSync(fd)
  }
  if (!record(parsed) || parsed.source_version !== fixtureVersion || !Array.isArray(parsed.skills)) {
    throw new Error('INVALID_SKILL_FIXTURE')
  }
  const skills = new Map<string, FrozenSkill>()
  for (const skill of parsed.skills as unknown[]) {
    if (!record(skill) || Object.keys(skill).sort().join(',') !== 'id,objectives,prerequisites,source_version,title'
      || typeof skill.id !== 'string' || !/^[a-z][a-z0-9_]{0,79}$/.test(skill.id)
      || typeof skill.title !== 'string' || !skill.title.trim()
      || !strings(skill.prerequisites) || !strings(skill.objectives)
      || skill.source_version !== fixtureVersion || skills.has(skill.id)) {
      throw new Error('INVALID_SKILL_FIXTURE')
    }
    skills.set(skill.id, Object.freeze({
      id: skill.id,
      title: skill.title,
      prerequisites: Object.freeze([...skill.prerequisites]),
      objectives: Object.freeze([...skill.objectives]),
      source_version: fixtureVersion,
    }))
  }
  if (skills.size === 0) throw new Error('INVALID_SKILL_FIXTURE')
  return skills
}

/**
 * Supplement to the official string/required schema, NOT a claim that the SDK
 * supports minLength/pattern. Keep arbitrary nonempty unknown IDs as not-found.
 */
export function validateSkillId(skillId: string): void {
  if (skillId.trim().length === 0) {
    throw new ToolArgsError(['$.skill_id: must contain a non-whitespace character'])
  }
}

const skillSchema = {
  type: 'object',
  additionalProperties: false,
  properties: {
    id: { type: 'string', required: true },
    title: { type: 'string', required: true },
    prerequisites: { type: 'array', items: { type: 'string' }, required: true },
    objectives: { type: 'array', items: { type: 'string' }, required: true },
    source_version: { type: 'string', required: true },
  },
} as const

export function apply(ctx: Context): void {
  const skills = loadSkills()
  // The official registry owns this effect in this plugin's Cordis fiber. Do not
  // wrap it in a fake ABI or manually remove global tools owned by another fiber.
  ctx.tools.register(defineTool({
    name: 'skill_lookup',
    description: 'Look up fixed public skill metadata by a nonempty skill id. Unknown ids return SKILL_NOT_FOUND. No filesystem paths are accepted.',
    parameters: {
      skill_id: { type: 'string', required: true, description: 'Nonempty stable skill id, e.g. binary_search; not a filesystem path.' },
    },
    output: {
      schema: {
        oneOf: [skillSchema, {
          type: 'object',
          additionalProperties: false,
          properties: {
            error: { type: 'string', const: 'SKILL_NOT_FOUND', required: true },
            skill_id: { type: 'string', required: true },
            source_version: { type: 'string', required: true },
          },
        }],
      },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
    },
    isConcurrencySafe: () => true,
    async execute(args) {
      validateSkillId(args.skill_id)
      const skill = skills.get(args.skill_id)
      if (!skill) return { error: 'SKILL_NOT_FOUND' as const, skill_id: args.skill_id, source_version: fixtureVersion }
      // Fresh canonical objects never expose the activation snapshot for mutation.
      return { ...skill, prerequisites: [...skill.prerequisites], objectives: [...skill.objectives] }
    },
  }))
}
