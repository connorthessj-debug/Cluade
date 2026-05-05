# Self-Improvement Protocol

> VERSION: 1.0 | This file may be improved by the self-improvement loop with user consent.

## Purpose

After every scan, Claude audits the process itself. Broken data sources, ambiguous thresholds, unclear steps — all are surfaced. The protocol genuinely improves over time without losing version control of what changed.

---

## The Core Loop

```
Scan executes following scan-protocol.md
        ↓
Audit block written to scanned/ file (Claude observes its own process)
        ↓
User reviews findings
        ↓
User grants consent ("apply fix N" or "apply all fixes")
        ↓
Claude edits guide/ or docs/ file (minimal, atomic change)
        ↓
Claude commits with descriptive message
        ↓
Next scan uses improved protocol
```

---

## What to Flag in the Audit Block

Flag **any** of the following during the step-by-step review:

### Data Failures
- API call returned an error (non-2xx response)
- API returned empty or null for a required field
- Script timed out or crashed
- Data was stale (e.g., FRED data older than 5 business days)

### Ambiguous Rules
- A scoring threshold felt arbitrary or produced an unintuitive result
- Two dimensions gave conflicting signals with no tiebreaker rule
- The framework doc was silent on an edge case

### Process Gaps
- A step in the protocol was unclear about what to do next
- The output format was ambiguous for a specific asset class
- A step was redundant or could be merged

### Logic Issues
- A scoring rule fired on technically correct data but produced economically nonsensical output
- The trade structure didn't fit the asset class (e.g., applying equity stop rules to forex)

---

## What NOT to Flag

- Minor style preferences
- "Would be nice to have" features that weren't in scope
- Issues with the underlying data that are outside our control (e.g., SEC filing delays)
- Things that worked correctly — only flag problems

---

## How to Write a Good Proposed Fix

Each fix must be:
1. **Specific**: reference the exact file, section, and line/paragraph to change
2. **Atomic**: one fix per issue — do not bundle multiple changes
3. **Conservative**: minimal change that resolves the specific problem
4. **Reversible**: the original text should be restorable

**Good example:**
```
Issue: Step 3 does not specify what to do when fetch_edgar.py returns a CIK not found error.
Fix: Add to guide/scan-protocol.md, Step 3, after the equity script block:
  "If fetch_edgar.py returns 'CIK not found': score Pillar 4 as 0, log as data gap."
```

**Bad example:**
```
Issue: The whole protocol could be reorganized.
Fix: Rewrite scan-protocol.md with a better structure.
```

---

## Consent Rules

Claude MUST:
- Write all findings to `scanned/` only during the scan
- NEVER edit `guide/` or `docs/` files during a scan (even if the fix seems obvious)
- Wait for explicit user consent before applying any fix
- Confirm the exact change before editing ("I will add this line to Step 3 of scan-protocol.md: ...")

Claude MUST NOT:
- Edit `docs/` files ever (they are read-only truth; only humans update those with deliberate intent)
- Batch multiple fixes into one edit without consent for each
- Apply a "similar" fix to what the user approved — apply exactly what was approved

**Exception**: `docs/` files may be edited if the user explicitly says "update the docs" or specifies a `docs/` file by name.

---

## Versioning

Every time a `guide/` file is improved, Claude must:
1. Update the `VERSION` line at the top of the file (increment patch: 1.0 → 1.1)
2. Add a one-line changelog entry below the VERSION line:
   ```
   > CHANGELOG: v1.1 — Added rule for missing CIK in Step 3 (2026-05-05)
   ```
3. Commit with message: `Improve scan protocol: {what changed} (self-improvement loop)`

---

## Audit Block Format Reference

See `guide/verdict-format.md` for the exact audit block template.

Minimum requirements for the audit block:
- A row for every step in `guide/scan-protocol.md`
- At least one "Issues Found" entry (even if "No issues found this scan")
- "AWAITING USER CONSENT" line (always present — even if no changes proposed)

---

## Escalation

If the same issue appears in 3+ consecutive scans without a fix being applied, Claude should mention it proactively in the user-facing summary (not just the audit block).
