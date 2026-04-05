# review_with_codex.md
## Codex Review Runbook

Use this after the main generation and hardening passes.

---

## Pass 1 — Review Only

Ask Codex to review the repo for:

- compile blockers
- missing includes
- type mismatches
- namespace mismatches
- broken CMake definitions
- Windows build issues
- installer script issues
- GUI wiring issues
- invented or undefined interfaces
- runtime safety edge cases

Recommended prompt:

```text
Review this repository for compile blockers and architecture inconsistencies.

Focus on:
- C++ compile errors
- missing includes
- mismatched type names
- namespace mismatches
- invalid forward declarations
- broken or inconsistent interfaces
- broken CMake definitions or target wiring
- Windows build viability with MSVC and MinGW
- installer script consistency with built output names
- GUI-to-engine integration issues
- config loading path issues
- invented or undefined interfaces
- obvious runtime safety problems

Rules:
- do not patch yet
- do not redesign the project
- do not suggest broad refactors unless necessary to compile

Output format:
1. Critical compile blockers
2. Likely Windows build blockers
3. CMake/install packaging issues
4. GUI integration issues
5. Exact file-level fixes needed
6. Anything that looks invented or undefined
```

---

## Pass 2 — Minimal Patch

After review findings are returned, ask for minimal exact fixes only.

Recommended prompt:

```text
Apply only the minimal exact fixes needed to resolve the issues you identified.

Constraints:
- preserve the existing architecture
- do not rewrite major subsystems
- do not add new external dependencies unless absolutely required
- do not change public interfaces unless necessary for correctness
- keep fixes small, localized, and compile-oriented

After patching, provide:
1. files changed
2. exact issues fixed
3. anything still unresolved
4. any remaining risk areas for Windows build or installer packaging
```

---

## Pass 3 — Re-review

Run a final verification pass.

Recommended prompt:

```text
Re-review the repository after the applied fixes.

Check again for:
- compile blockers
- missing includes
- namespace/type mismatches
- broken CMake targets
- Windows build script issues
- installer script issues
- GUI wiring issues
- undefined symbols or invented interfaces
- obvious runtime crashes from bad assumptions

Output only:
1. remaining blockers
2. remaining warnings
3. whether the repo looks ready for first Windows build attempt
```

---

## Rule

Always use:
review -> patch -> re-review

Do not skip straight to broad rewrites.
