---
name: run-evals
description: Run the cabinet-mcp eval suite and interpret results. Use whenever you finish a non-trivial change, want to check the 283-scenario / 940-assertion baseline, filter evals by tag/difficulty/name, or debug a failing scenario. The eval harness calls tool handlers directly (no MCP transport) and runs in ~1 second.
---

# Running the eval suite

The evals are the fast, transport-free integration check for this repo. They import server handler functions directly via `TOOL_DISPATCH`, so the whole suite runs in about one second. **Run them after any non-trivial change** — CLAUDE.md treats this as required.

## Commands

```bash
uv run python -m evals                 # full suite
uv run python -m evals --tag kitchen   # one tag
uv run python -m evals --tag drawer --tag door   # OR across tags (repeatable)
uv run python -m evals --difficulty basic        # basic | standard | advanced
uv run python -m evals --name overflow_drawer_stack   # one scenario (repeatable)
uv run python -m evals --json          # machine-readable (CI/scripting)
uv run python -m evals --verbose       # show passing assertions too
uv run python -m evals --list          # print the catalogue without running
```

`--tag` is validated against the auto-derived `ALL_TAGS`; a typo exits with code 2, and a filter combination that matches zero scenarios exits 1 (both were vacuous-green holes before PR #21 — do not "fix" them back).

## Baseline

Green is **288 scenarios / 983 assertions / 100%**. Exit code 0 on all-pass, 1 on any failure. If your change moves the assertion count, that's expected only when you added/removed assertions — otherwise investigate.

## Reading a failure

Each failing scenario prints `[FAIL] <name>  (passed/total)` followed by the failing assertion's `path` and operator. The `path` is a dot-walk into the tool's JSON result (e.g. `summary.errors`, `exterior.width_mm`). To reproduce a single failure in isolation:

```bash
uv run python -m evals --name <scenario_name> --verbose
```

To inspect the actual tool output the assertion walked, drive the handler directly (see the `drive-mcp-handlers` skill) with the same args from `evals/scenarios.py`.

## Where things live

- Harness + assertion operators: `evals/harness.py` (`evaluate_assertion`, `run_all`, `TOOL_DISPATCH`).
- Scenarios (declarative data): `evals/scenarios.py`.
- CLI/flags: `evals/__main__.py`.

## CI note

CI runs the eval suite in **both** the lite and full jobs, so evals must pass without CadQuery/opcut/rectpack. Local `uv run` is full-mode; **CI lite is the truth** for lite-only code paths — don't rely on a local full-mode green to clear a lite regression.
