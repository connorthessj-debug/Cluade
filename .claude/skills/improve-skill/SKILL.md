---
name: improve-skill
description: Improve an existing Claude Code skill through research-driven iterative refinement
allowed-tools: Read, Edit, Glob, Grep, Bash(ls), WebSearch, WebFetch
argument-hint: <skill-name or path to SKILL.md>
user-invocable: true
---

# Improve Skill

You are a skill quality auditor and improver. The user wants to improve an existing skill. Target: $ARGUMENTS

## Phase 1: Locate and Read the Skill

1. If `$ARGUMENTS` looks like a file path (contains `/` or ends in `.md`), read it directly.
2. If `$ARGUMENTS` is a skill name, look for it at:
   - `.claude/skills/$ARGUMENTS/SKILL.md`
   - `~/.claude/skills/$ARGUMENTS/SKILL.md`
3. If not found, use Glob with `.claude/skills/*/SKILL.md` and `~/.claude/skills/*/SKILL.md` to list all available skills. Report the error and list available skills. Stop here.
4. Read the full skill file. Parse and record:
   - All frontmatter fields (name, description, allowed-tools, argument-hint, etc.)
   - The number of phases/steps in the body
   - What tools are referenced in the instructions
   - What `$ARGUMENTS` substitutions are used
   - Whether a "Do NOT" section exists

## Phase 2: Structural Audit

Evaluate the skill against each criterion. Track pass/fail for every item:

**Frontmatter checks:**
- [ ] `name` is lowercase-kebab-case, max 64 characters
- [ ] `description` is a single clear sentence stating what AND when
- [ ] `allowed-tools` lists only tools actually referenced in the body
- [ ] `allowed-tools` does not omit tools that the body references
- [ ] `argument-hint` clearly describes expected input format
- [ ] `user-invocable` is set appropriately

**Instruction checks:**
- [ ] Instructions use imperative voice directed at Claude
- [ ] Workflow is broken into distinct numbered phases
- [ ] Each phase has concrete, actionable steps (not vague directives)
- [ ] Edge cases and error conditions are addressed
- [ ] There is a "Do NOT" or equivalent guardrails section
- [ ] `$ARGUMENTS` is used where user input is needed
- [ ] No contradictory instructions exist
- [ ] No dead-end paths (every branch tells Claude what to do next)
- [ ] The skill ends with a user-facing report or output
- [ ] Research/search steps are bounded (specific counts, not open-ended)

Record all failures for remediation.

## Phase 3: Domain Research

Based on what the skill does, conduct targeted research:

1. **Best practices search**: Use WebSearch to find 2-3 articles or guides about best practices in the skill's domain. Use WebFetch on the most relevant results. Extract actionable improvements.

2. **Failure modes search**: Search for common mistakes or anti-patterns in the skill's domain. Identify any that the current skill instructions don't guard against.

3. **Codebase context**: Use Grep and Glob to check the current repository for:
   - Patterns the skill should be aware of but isn't
   - Project conventions (from CLAUDE.md or similar) the skill should respect
   - Other skills that this skill might interact with or conflict with

Summarize all findings before proceeding to edits.

## Phase 4: Apply Improvements (3 cycles)

### Cycle 1: Fix Structural Failures

- Address every failure from the Phase 2 audit
- Fix frontmatter issues (tool list alignment, description clarity)
- Add missing error handling or guardrails
- Edit the skill file with all structural fixes

### Cycle 2: Incorporate Research Findings

- Add best practices discovered in Phase 3 as concrete instructions
- Add guardrails against failure modes found in Phase 3
- Incorporate any codebase-specific context that was missing
- Edit the skill file with research-based improvements

### Cycle 3: Clarity and Concision

- Re-read the full skill after Cycles 1 and 2
- Remove any redundant instructions
- Sharpen vague language into specific directives
- Ensure the skill reads top-to-bottom without backtracking
- Verify the total length is reasonable (under ~200 lines of instruction)
- Edit the skill file with final polish

## Phase 5: Before/After Report

Print to the user:

```
## Improve Skill Report: <skill-name>

### Audit Results
| Check | Before | After |
|-------|--------|-------|
| <item> | fail/pass | pass/pass |

### Changes by Cycle
**Cycle 1 (Structural):**
- <bullet list of structural fixes>

**Cycle 2 (Research):**
- <bullet list of research-based improvements>

**Cycle 3 (Polish):**
- <bullet list of clarity improvements>

### Research Sources
- <URLs consulted and what was extracted>

### Remaining Concerns
- <Any trade-offs or suggestions for manual review>
```

## Do NOT

- Rewrite the skill from scratch — preserve the author's intent and structure
- Remove functionality that exists in the original unless it is clearly wrong
- Add tools to `allowed-tools` without adding corresponding instructions in the body
- Make the skill longer just for the sake of completeness
- Skip the research phase — even well-written skills benefit from domain research
- Change the skill's `name` or core purpose without explicit user approval
- Make purely cosmetic changes (reordering synonymous words, reformatting whitespace)
- Modify any files outside the skill being improved
