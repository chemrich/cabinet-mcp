# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Full install — CadQuery, rectpack, and dev tools included (recommended)
uv pip install -e ".[full,dev]"

# Lite install — pure-Python only: parametric checks, cutlist BOM, MCP, evals
uv pip install -e .

# Or just sync everything via uv (default-groups = full + dev, so this is equivalent to full)
uv sync

# Run the MCP server (stdio, for Claude Desktop / Gemini CLI)
uv run cabinet-mcp

# Lite mode — skips CadQuery and rectpack
uv run --no-group full cabinet-mcp

# Run the MCP server (HTTP/SSE, port 3749 auto-incrementing)
uv run cabinet-mcp --http
uv run cabinet-mcp --http --port 4200

# Run tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_evaluation.py -v

# Run a single test by name
uv run pytest tests/test_evaluation.py -v -k "test_valid_drawer"

# Run evals (full suite)
uv run python -m evals

# Run evals with filters
uv run python -m evals --tag kitchen
uv run python -m evals --tag drawer --tag door
uv run python -m evals --difficulty advanced
uv run python -m evals --name overflow_drawer_stack
uv run python -m evals --json          # machine-readable
uv run python -m evals --list          # print scenario catalogue
```

## Architecture

The package lives in `src/cadquery_furniture/`. All units are millimetres. The data-flow is:

```
hardware.py + joinery.py
        │
        ▼
cabinet.py / drawer.py / door.py   ← parametric dataclasses (no CadQuery required)
        │
        ▼
evaluation.py   ← returns typed Issue objects (no CadQuery required)
        │
        ▼
cutlist.py      ← BOM, guillotine optimiser, JSON/CSV export (no CadQuery required)
        │
        ▼
server.py       ← MCP server (17 tools, stdio or HTTP/SSE)
```

`evals/` (harness + scenarios) imports server handler functions directly — no MCP transport involved — so the full eval suite runs in under 1 second.

### Key design patterns

- **Frozen dataclasses everywhere.** `CabinetConfig`, `DrawerConfig`, `DoorConfig`, hardware specs, and joinery specs are all `@dataclass(frozen=True)`. Computed properties (e.g. `interior_width`, `box_height`) are `@property`.
- **CadQuery is optional.** The `try: import cadquery` pattern is used throughout. `evaluation.py` and `cutlist.py` have CadQuery-backed and pure-Python code paths. The pure-Python paths run in all environments and are what the tests and evals exercise.
- **MCP tool handlers are plain async functions** (e.g. `_tool_design_cabinet`) that return `list[types.TextContent]`. The evals harness calls these directly via `TOOL_DISPATCH`, bypassing the MCP transport layer entirely.

### Module responsibilities

| Module | Responsibility |
|---|---|
| `hardware.py` | Frozen specs for Blum/Accuride/Salice drawer slides and Blum Clip Top hinges; `HingeSpec.hinges_for_height()` and `hinge_positions()` implement manufacturer placement rules |
| `joinery.py` | `DrawerJoinerySpec.from_stock()` computes all cut dimensions; `DominoSpec`, `PocketScrewSpec`, `BiscuitSpec`, `DowelSpec` each provide `count_for_span()` and `positions_for_span()` |
| `cabinet.py` | `CabinetConfig` with `drawer_config` list of `(height_mm, opening_type)` tuples; `carcass_joinery` field selects method |
| `drawer.py` | `DrawerConfig` computes box dimensions from opening + slide clearances; `joinery_style` applies corner joints |
| `door.py` | `DoorConfig` for single doors and matched pairs; full/half/inset overlay; hinge cup borings via CadQuery |
| `evaluation.py` | `evaluate_cabinet(cfg) -> list[Issue]`; `Issue` has `severity`, `measured`, `threshold`; CadQuery path adds interference checks |
| `cutlist.py` | `consolidate_bom()`, `optimize_cutlist()` (GuillotineBssfSas — every cut is a full-width table-saw cut), `to_json()`, `to_csv()`; grain direction tracked |
| `server.py` | Seventeen MCP tools; `main()` entry point; `--http` flag switches stdio → HTTP/SSE; port auto-increments from 3749 |

### Eval harness

Scenarios live in `evals/scenarios.py`. Each `Scenario` has a natural-language `prompt`, a list of `ToolCall`s with `Assertion`s, and tags/difficulty for filtering. Available assertion operators: `EQ`, `APPROX`, `GT`, `GTE`, `LT`, `LTE`, `IN`, `CONTAINS`, `HAS_KEY`, `LEN_EQ`, `LEN_GTE`, `IS_TRUE`, `IS_FALSE`, `NO_ERRORS`, `HAS_ERROR`, `HAS_WARNING`.

Baseline: 77 scenarios / 332 assertions / 100% pass rate. Run the eval suite after any non-trivial change.

## Known issues

- **`cutlist.extract_bom_parametric`** silently returns an empty list when CadQuery is absent and the parts list has more than one item (logic bug: `return extract_bom(parts)` is inside the per-part loop).
- **`cabinet.py` dado_x mirror logic** is inverted — dados are cut on the exterior face instead of the interior face.
- **Shelf pin hole x-position** is identical for both left and right panels (both branches compute `side_thickness / 2`).
- **`evaluation.py`** emits a duplicate drawer height error (same check runs in both `validate_drawer_dims` and the evaluation layer).
