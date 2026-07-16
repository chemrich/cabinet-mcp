---
name: cabinet-review
description: Run Charlie's full-codebase or multi-module review-and-fix workflow for cabinet-mcp. Use for a broad correctness/security review across many modules, or when asked for a "top-to-bottom" review. Covers the parallel module-agent fan-out, verification, the fixes-as-their-own-PR convention, and merging only on explicit go.
---

# Cabinet-mcp review → fix → merge workflow

This is the established shape for a broad review of this repo (used for PR #21). It fans review out across modules in parallel, verifies findings independently, then lands fixes as a dedicated PR that Charlie merges on his explicit call.

## 1. Establish the baseline first

```bash
uv run pytest tests/ -q          # capture the actual passed/skipped counts NOW
uv run python -m evals           # evals baseline is 283 scenarios / 940 assertions (per CLAUDE.md)
```
**Record whatever numbers this run prints** — the test count grows as tests are added, so the baseline is "what the suite reports on the pre-change tree," not a fixed figure. Every later "green" is measured against these captured numbers, not a hardcoded one.

## 2. Fan out review by module cluster (parallel agents)

Launch one agent per disjoint file group so their edits never collide. A workable split:

- geometry: `cabinet.py`, `drawer.py`, `door.py`
- joinery/hardware: `joinery.py`, `hardware.py`
- evaluation/fix: `evaluation.py`, `auto_fix.py`, `proportions.py`
- cutlist: `cutlist.py`
- server/security: `server.py`
- visualizer: `visualize.py`
- data/describe: `project.py`, `presets.py`, `pulls.py`, `describe.py`, `furniture_refs.py`
- evals/CI infra: `evals/`, `conftest.py`, `pyproject.toml`, `.github/`, `.claude/`

Tell each agent to read CLAUDE.md first (it lists already-fixed issues — don't re-report those), **substantiate every finding with a concrete trace or `uv run python -c` repro**, and return severity-tagged findings (critical/major/minor/nit) with file:line, evidence, and a one-line fix.

## 3. Verify before acting

Independently reproduce the high-impact findings yourself (don't trust an agent's claim unseen). This repo's traps that make plausible findings wrong:

- **Derived-property tautologies:** several checks compare a property to its own defining formula — "it can never fire" is often real here, but confirm.
- **CadQuery vs pure-Python paths** can legitimately differ; check which path production uses.
- **Coordinate conventions** are documented in CLAUDE.md (workplane axes, GLTF node hierarchy) — verify axis/sign claims against them.

## 4. Implement fixes

If fanning out fixes across agents, keep file groups disjoint and have each: update/add tests (any test encoding old buggy behavior gets updated with a note), keep its module green, and **not** run the whole suite or commit. Then integrate:

```bash
uv run pytest tests/ -q && uv run python -m evals
```
Reconcile cross-module seams centrally (a new check in one module can trip a preset or scenario owned by another).

## 5. Land it — Charlie's conventions ([[review-fix-merge-workflow]])

- Fixes go on their **own branch / PR** (base = the branch under review if it's unmerged, else `main`).
- Write the review findings as a doc (e.g. `docs/code-review-<date>.md`) and commit it distinctly from the fixes for separate reviewability.
- Present a **merge-order recommendation and wait** — merge only on his explicit "merge it", in the order he approves. Never merge unprompted.
- End commit messages with the `Co-Authored-By` trailer; end PR bodies with the Claude Code attribution line.
- `--delete-branch` is safe only with no PR stacked on top (GitHub *closes* a PR whose base branch is deleted).

## Deferred / judgment calls

Flag data that needs shop reality (supplier SKUs, pack/pricing basis) rather than guessing — surface it for Charlie and leave the code untouched until he supplies values.
