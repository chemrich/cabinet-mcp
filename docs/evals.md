# Eval harness

`evals/` benchmarks the MCP server against realistic cabinetry prompts. Run it after any non-trivial code change to catch regressions. The harness calls tool handlers directly via `TOOL_DISPATCH`, so the full suite finishes in under a second, and it runs in a sandboxed temp HOME so it never touches your real project store.

## Running

```bash
uv run python -m evals                               # full suite
uv run python -m evals --tag kitchen                 # one tag
uv run python -m evals --tag drawer --tag door       # multiple tags
uv run python -m evals --tag optimizer               # sheet optimiser scenarios
uv run python -m evals --difficulty advanced         # only hard scenarios
uv run python -m evals --name overflow_drawer_stack  # single scenario
uv run python -m evals --json                        # machine-readable output for CI
uv run python -m evals --list                        # print scenario catalogue
```

## Baseline

```
Scenarios:   305/305 passed
Assertions:  1139/1139 passed
Score:       100.0%
```

(2026-07-29. If you add scenarios, update this block, the counts in CLAUDE.md, and the `add-scenario` guard tests together.)

## Scenario catalogue

Scenarios carry multiple tags, so counts overlap. Domain and feature tags:

| Tag | Count | | Tag | Count |
|-----|-------|-|-----|-------|
| `drawer` | 92 | | `legs` | 8 |
| `evaluation` | 67 | | `optimizer` | 8 |
| `cutlist` | 52 | | `bathroom` | 7 |
| `door` | 43 | | `basic_cabinet` | 7 |
| `kitchen` | 33 | | `standard_height` | 5 |
| `joinery` | 32 | | `edge_band` | 4 |
| `presets` | 32 | | `entryway` | 3 |
| `describe` | 31 | | `assembly` | 2 |
| `proportions` | 29 | | `miter` | 2 |
| `workflow` | 25 | | `office` | 2 |
| `hardware` | 22 | | `face_material` | 1 |
| `multi_column` | 19 | | `sheet_size` | 1 |
| `pulls` | 19 | | `storage` | 1 |
| `auto_fix` | 18 | | `worktop` | 1 |
| `bedroom` | 18 | | `tall` | 14 |
| `project` | 16 | | `wide` | 9 |
| `workshop` | 14 | | `furniture` | 9 |
| `living_room` | 13 | | `edge_case` | 11 |
| `identify_furniture` | 12 | | `furniture_refs` | 12 |

Persona tags slice the same scenarios by who'd be asking: `homeowner` (50), `furniture_maker` (49), `cabinet_maker` (48).

## Adding a scenario

Scenarios live in `evals/scenarios.py`. Each has a natural-language `prompt`, a list of `ToolCall`s with typed `Assertion`s, and tags for filtering. (There's a project skill, `add-scenario`, that walks through the conventions — including the meta-tests every scenario must satisfy.)

```python
_s(Scenario(
    name="my_new_scenario",
    prompt="Design a 900 mm tall pantry cabinet with adjustable shelves.",
    tags=["basic_cabinet"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 900, "depth": 550},
            assertions=[
                Assertion("exterior.height_mm", Op.EQ, 900),
            ],
        ),
    ],
))
```

## Assertion path notation

Paths are dot-separated and support both dot-integer and bracket notation for list indices — use whichever feels natural:

```python
Assertion("opening_stack.0.type",   Op.EQ, "drawer")  # dot notation
Assertion("opening_stack[0].type",  Op.EQ, "drawer")  # bracket notation — identical
```

Assertion operators: `EQ`, `APPROX`, `GT`, `GTE`, `LT`, `LTE`, `IN`, `CONTAINS`, `HAS_KEY`, `LEN_EQ`, `LEN_GTE`, `IS_TRUE`, `IS_FALSE`, `NO_ERRORS`, `HAS_ERROR`, `HAS_WARNING`. `HAS_ERROR`/`HAS_WARNING` accept an expected check-name filter, so a scenario can assert *which* check fired, not just that something did.
