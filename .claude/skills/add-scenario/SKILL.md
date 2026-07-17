---
name: add-scenario
description: Add a new eval scenario to cabinet-mcp's eval suite. Use when covering a new tool behavior, a bug regression, or a workflow chain in evals/scenarios.py. Covers the Scenario/ToolCall/Assertion structure, the assertion operators, context chaining between calls, and the meta-tests every scenario must satisfy.
---

# Adding an eval scenario

Scenarios are declarative data in `evals/scenarios.py`, registered by wrapping each in `_s(...)`. Each `Scenario` has a natural-language `prompt`, a list of `ToolCall`s, and `tags` / `difficulty` for filtering.

## Structure

```python
_s(Scenario(
    name="overflow_drawer_stack",          # unique across the catalogue
    prompt="A 600 mm cabinet with a 900 mm drawer stack — should flag overflow.",
    tags=["drawer", "evaluation"],          # auto-collected into ALL_TAGS; no registration needed
    difficulty="standard",                  # basic | standard | advanced
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",        # must be a real tool in TOOL_DISPATCH
            args={"width": 600, "height": 720, "depth": 550,
                  "drawer_config": [[300, "drawer"], [300, "drawer"], [300, "drawer"]]},
            label="evaluate an over-tall stack",
            assertions=[
                Assertion("summary.errors", Op.GT, 0),
                Assertion("summary.pass",   Op.IS_FALSE),
            ],
        ),
    ],
))
```

## Assertion operators (`Op`)

`EQ`, `APPROX` (abs diff < 0.15), `GT`, `GTE`, `LT`, `LTE`, `IN`, `CONTAINS`, `HAS_KEY`, `LEN_EQ`, `LEN_GTE`, `IS_TRUE`, `IS_FALSE`, `NO_ERRORS`, `HAS_ERROR`, `HAS_WARNING`.

- `path` is a dot-walk into the tool's JSON result (`"exterior.width_mm"`, `"summary.errors"`). A path that doesn't resolve **fails** (fail-closed).
- **`HAS_KEY` with a string expected** checks the dict at `path` contains that key (`Assertion("files", Op.HAS_KEY, "csv")`); with `expected=True`/`None` it just checks the path resolves. Don't pass a key name expecting mere existence — it now really checks the key.
- Prefer **falsifiable** assertions. Avoid tautologies like `GTE 0` on a count; assert a real bound.

## Context chaining (multi-call workflows)

- `save_as={"var": "result.path"}` — store a resolved value after a successful call.
- `context_args={"arg_name": "var"}` — inject a saved value into the next call's args.
- `arg_transforms={"arg_name": lambda v: ...}` — transform a resolved value before injection (e.g. heights list → `drawer_config` pairs).

A later step reading a missing saved var fails loudly, so chains can't pass vacuously.

## Meta-tests every scenario must satisfy (`tests/test_eval_harness.py`)

- `test_unique_names` — `name` must be unique.
- `test_all_scenarios_have_tool_calls` — non-empty `tool_calls`.
- `test_all_tool_calls_reference_valid_tools` — every `tool` is in `TOOL_DISPATCH`.

## Verify

```bash
uv run pytest tests/test_eval_harness.py -q      # meta-tests
uv run python -m evals --name overflow_drawer_stack --verbose   # your scenario
uv run python -m evals                            # full suite stays green
```

Baseline is 286 scenarios / 960 assertions; expect your additions to raise both counts. Remember evals run in **lite CI too** — assert on shapes available without CadQuery (e.g. the `ERROR:` result in lite for CadQuery-only tools), or gate accordingly.
