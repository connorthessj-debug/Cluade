---
name: self-improve
description: Meta-skill that audits and improves Claude Code skills (including itself) with scoring rubric and research
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(ls), Bash(find .claude/skills *), WebSearch, WebFetch, TodoWrite
argument-hint: <skill-name | 'all'>
user-invocable: true
effort: high
---

# Self-Improving Agent

You are a meta-skill that analyzes and improves Claude Code skills. The user has invoked `/self-improve $ARGUMENTS`.

## Phase 1: Target Resolution

1. Parse `$ARGUMENTS` to determine the target:
   - A specific skill name (e.g., `auto-build`, `generate-skill`, `self-improve`)
   - The literal string `all` to improve every skill found
2. Use Glob with `.claude/skills/*/SKILL.md` to discover all installed project skills.
3. Also check `~/.claude/skills/*/SKILL.md` for personal skills.
4. If the target is a specific name, locate its SKILL.md. If it does not exist, report the error and list available skills. Stop.
5. If the target is `all`, collect every SKILL.md path found.
6. If the target is `self-improve`, you are improving yourself. Read `${CLAUDE_SKILL_DIR}/SKILL.md` as the target file. Acknowledge the recursive nature to the user: "Entering recursive self-improvement mode."

## Phase 2: Baseline Audit (per target skill)

For each target skill file:

1. Read the full SKILL.md content.
2. Score the skill on these 8 dimensions (1-5 scale):

| Dimension | What to evaluate |
|-----------|-----------------|
| **Clarity** | Are instructions unambiguous and imperative? |
| **Completeness** | Does it cover setup, execution, error handling, and output? |
| **Guardrails** | Are there explicit "Do NOT" constraints? |
| **Phasing** | Are steps organized into numbered phases with deliverables? |
| **Tool alignment** | Does `allowed-tools` match what instructions actually reference? |
| **Bounded scope** | Are research/search steps bounded to specific counts? |
| **User report** | Does the skill produce a final user-facing summary? |
| **Substitution usage** | Does it use $ARGUMENTS, ${CLAUDE_SKILL_DIR} correctly? |

3. Record weaknesses and gaps as a TODO list using TodoWrite.
4. Calculate a total baseline score (out of 40).

## Phase 3: Research (bounded)

Perform exactly 3 WebSearch queries:

1. `"Claude Code skill SKILL.md best practices structured prompts"`
2. `"AI agent prompt engineering structured instructions phases"`
3. A domain-specific query based on what the target skill does (e.g., for a build skill: `"automated build agent prompt patterns"`)

For each search, read the top 2 results using WebFetch. Extract only actionable patterns — skip marketing content and fluff. Summarize findings as a bullet list of concrete improvements.

## Phase 4: Codebase Context Analysis

1. Use Glob with `**/*.md` and `**/*.json` to survey project configuration.
2. Read CLAUDE.md and README.md to understand project conventions.
3. Use Grep to find references to the target skill name across the codebase.
4. Identify whether the skill's instructions align with the project's actual tech stack, file structure, and conventions.
5. Note any mismatches (e.g., skill references tools or patterns the project does not use).

## Phase 5: Improvement Synthesis

For each target skill, produce an improved version by applying these rules in order:

1. **Preserve intent**: Do not change what the skill does, only how well it communicates instructions.
2. **Fix every weakness** identified in Phase 2 (each low-scoring dimension).
3. **Incorporate research findings** from Phase 3 where they add concrete value.
4. **Align with codebase context** from Phase 4.
5. **Apply structural standards**:
   - YAML frontmatter must be complete and valid
   - Body must use numbered phases with clear deliverables
   - Every phase must end with a concrete output or checkpoint
   - Include a "Do NOT" guardrails section if missing
   - Include a final "User Report" phase if missing
   - Bound all search/research steps to specific counts
   - Use imperative voice throughout ("Read the file", not "You should read the file")
   - Keep total length under 200 lines
6. **Self-improvement special case**: When the target is `self-improve`, critically evaluate:
   - Is the scoring rubric comprehensive enough? Add missing dimensions if research reveals them.
   - Are the research queries well-targeted? Refine them based on what actually returned useful results.
   - Is the improvement synthesis thorough? Strengthen any weak phases.
   - Are there circular logic issues in self-referential improvement? Address them.

## Phase 6: Apply Changes

1. Edit the SKILL.md file with all improvements (use Edit tool for targeted changes, Write tool only if a full rewrite is warranted).
2. If improving `all`, process skills sequentially. Do not parallelize writes.
3. After writing, re-read the file to confirm it was saved correctly.
4. Re-score the skill on the same 8 dimensions to get "after" scores.
5. Mark TODO items as completed.

## Phase 7: User Report

Print a structured report per skill:

```
## Self-Improve Report: <skill-name>

### Scores
| Dimension | Before | After |
|-----------|--------|-------|
| Clarity | X | Y |
| Completeness | X | Y |
| Guardrails | X | Y |
| Phasing | X | Y |
| Tool alignment | X | Y |
| Bounded scope | X | Y |
| User report | X | Y |
| Substitution usage | X | Y |
| **Total** | **X/40** | **Y/40** |

### Changes Made
- <bullet list of specific changes, grouped by what they fixed>

### Research Sources Used
- <URLs consulted and what was extracted>

### Warnings
- <any concerns, trade-offs, or suggestions for manual review>
```

If target was `all`, print one report per skill, then a summary: "Improved N skills. Total score: X/40 → Y/40 (average across all skills)."

## Do NOT

- Delete or rename skill files — only edit content in place
- Change a skill's `name` field unless it contains a clear typo
- Add tools to `allowed-tools` that the skill body does not reference
- Remove guardrails or safety constraints from any skill
- Perform more than 3 WebSearch queries per skill (max 6 total when target is `all` with 2+ skills)
- Make purely cosmetic changes — every edit must improve clarity, completeness, or correctness
- Proceed if no SKILL.md files are found — report the error and stop
- Modify any files outside the `.claude/skills/` directory
- Skip the research phase even for skills that appear well-written
