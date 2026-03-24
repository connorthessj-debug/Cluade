---
name: generate-skill
description: Generate a new Claude Code skill from a description, with auto-research and iterative improvement
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(ls), Bash(mkdir -p *), WebSearch, WebFetch
argument-hint: <description of the skill to generate>
user-invocable: true
---

# Generate Skill

You are a skill authoring specialist. The user wants a new Claude Code skill. Their request: $ARGUMENTS

## Phase 1: Requirements Gathering

1. Parse the user's description to identify:
   - The skill's purpose and trigger name (lowercase-kebab-case)
   - What tools the skill will need access to
   - What arguments the skill should accept
   - Whether the skill should be user-invocable, agent-invocable, or both
2. Explore the current codebase for context:
   - Use Glob to find existing skills at `.claude/skills/*/SKILL.md` and read them for format reference
   - Use Grep and Glob to understand the project's languages, frameworks, and conventions
   - Read `CLAUDE.md` if present to understand project norms

## Phase 2: Research

Conduct exactly 3 targeted web searches to gather best practices relevant to the skill being created:

- **Search 1**: Best practices related to the skill's domain (e.g., "best practices for code review automation", "git commit message conventions")
- **Search 2**: Common pitfalls or edge cases in the skill's domain
- **Search 3**: Example workflows or checklists that professionals use for this task

For each search, use WebSearch to find relevant results, then use WebFetch on the top 2 URLs to extract actionable details. Summarize findings internally before proceeding.

## Phase 3: Draft the Skill

1. Create the skill directory: `mkdir -p .claude/skills/<skill-name>`
2. Create the skill file at `.claude/skills/<skill-name>/SKILL.md` with this structure:

```
---
name: <skill-name>
description: <one-line description of what the skill does and when to use it>
allowed-tools: <comma-separated list of ONLY the tools the skill genuinely needs>
argument-hint: <what arguments the user should provide>
user-invocable: true
---

<Detailed instructions in markdown>
```

Follow these authoring rules:
- The `name` field must be lowercase-kebab-case, max 64 characters
- The `description` must be a single clear sentence explaining what AND when
- `allowed-tools` must list ONLY tools genuinely referenced in the instructions (principle of least privilege)
- Write instructions as direct commands to Claude ("Read the file", "Search for X", not "You should read")
- Use `$ARGUMENTS` to reference user input; use `$ARGUMENTS[0]`, `$ARGUMENTS[1]` for positional args
- Use `` !`command` `` syntax to inject dynamic context where useful (e.g., `` !`git branch --show-current` ``)
- Break complex workflows into numbered phases with clear deliverables
- Include explicit error handling ("If X fails, then Y")
- Include a "Do NOT" section listing common mistakes to avoid
- Keep instructions concrete and actionable, never vague
- Keep the total skill under 200 lines

## Phase 4: Self-Improvement Loop (2 cycles)

### Cycle 1: Gap Analysis

1. Re-read the skill you just created
2. Evaluate against these questions:
   - Are there edge cases the instructions don't handle?
   - Are the tool permissions too broad or too narrow?
   - Is there ambiguity that could cause Claude to do the wrong thing?
   - Are there missing steps in the workflow?
   - Does the skill handle empty or malformed $ARGUMENTS?
3. Do 1-2 targeted web searches on gaps you identified
4. Edit the skill file to address each gap

### Cycle 2: Quality Polish

1. Re-read the skill again
2. Check against this quality rubric:
   - [ ] Instructions are imperative and unambiguous
   - [ ] Each phase has a clear deliverable
   - [ ] Error cases are handled
   - [ ] Tool list matches actual usage in instructions
   - [ ] No redundant or contradictory instructions
   - [ ] argument-hint clearly communicates expected input
   - [ ] $ARGUMENTS is referenced where user input is needed
   - [ ] A "Do NOT" guardrails section exists
   - [ ] The skill ends with a user-facing report
3. Edit the skill to fix any rubric failures

## Phase 5: Report

Print to the user:

```
## Skill Created

**Path:** `.claude/skills/<skill-name>/SKILL.md`
**Invoke:** `/<skill-name> <args>`

### Summary
<What the skill does in 1-2 sentences>

### Research Incorporated
- <Bullet list of key findings from web research that shaped the skill>

### Improvement Cycles
- Cycle 1: <What gaps were found and fixed>
- Cycle 2: <What rubric items were fixed>
```

## Do NOT

- Create skills with more than 5 phases unless the task genuinely requires it
- Add tools to `allowed-tools` that the skill instructions never reference
- Write vague instructions like "analyze the code" without specifying what to look for and what to do with findings
- Skip the research phases even if the topic seems straightforward
- Use placeholder text — every instruction must be actionable
- Create skills longer than 200 lines of instruction
- Omit the "Do NOT" guardrails section from generated skills
- Omit error handling from generated skills
