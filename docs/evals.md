# Eval harness

`evals/` benchmarks the MCP server against realistic cabinetry prompts. Run it after any non-trivial code change to catch regressions. The harness calls tool handlers directly via `TOOL_DISPATCH`, so the full suite finishes in under a second.

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
Scenarios:   77/77 passed
Assertions:  332/332 passed
Score:       100.0%
```

## Scenario catalogue

| Tag | Count | What it covers |
|-----|-------|----------------|
| `basic_cabinet` | 7 | Standard, narrow, tall, wide, shallow cabinets |
| `drawer` | 18 | Butt, QQQ, half-lap, drawer-lock joints + standard-height snapping |
| `standard_height` | 4 | Height snapping to 4″/6″/8″ tiers, opt-out, exact boundary match |
| `door` | 9 | Full/half/inset overlay, pairs, BLUMOTION, tall doors (3 hinges) |
| `joinery` | 12 | All drawer styles + all carcass methods + side-by-side comparisons |
| `cutlist` | 7 | JSON + CSV output, custom sheet sizes, guillotine optimiser |
| `optimizer` | 4 | Sheet optimiser: single-sheet fit, multi-sheet, oversized panels, custom kerf |
| `kitchen` | 6 | Multi-tool workflows, full kitchen design, kitchen presets |
| `presets` | 12 | Listing, filtering, overrides, mismatch warning, unknown name |
| `living_room` | 6 | Console, credenza, sideboard, media console + describe |
| `evaluation` | 9 | Designs that should produce errors (overflow, thin panels, column widths) |
| `edge_case` | 9 | Extreme dimensions, unusual configs, oversized panels, preset override edges |
| `workshop` | 2 | Tool chest preset, heavy-duty slide validation |
| `auto_fix` | 4 | Oversized repair, undersized no-op, clean pass-through, full workflow |
| `describe` | 3 | Basic prose, credenza preset summary, full workflow |
| `workflow` | 6 | End-to-end: design → evaluate → auto-fix → describe |
| `legs` | 4 | Default legs, load check, 6-leg pattern, `list_hardware` |
| `multi_column` | 3 | Drawers+door, width mismatch error, 3-column dresser |
| `hardware` | 6 | `list_hardware` for slides, hinges, and legs |
| `proportions` | 3 | Drawer height presets, column width presets, combined layout |
| `pulls` | 8 | Pull placement, pack-quantity math, style mismatch, IKEA multi-packs |

## Adding a scenario

Scenarios live in `evals/scenarios.py`. Each has a natural-language `prompt`, a list of `ToolCall`s with typed `Assertion`s, and tags for filtering.

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

Assertion operators: `EQ`, `APPROX`, `GT`, `GTE`, `LT`, `LTE`, `IN`, `CONTAINS`, `HAS_KEY`, `LEN_EQ`, `LEN_GTE`, `IS_TRUE`, `IS_FALSE`, `NO_ERRORS`, `HAS_ERROR`, `HAS_WARNING`.
