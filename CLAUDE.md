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

### Geometry / evaluation bugs
- **`cabinet.py` shelf pin holes wrong workplane** — `make_side_panel` creates shelf pin holes on the "XY" workplane (cylinder axis = Z, vertical), which cuts narrow vertical columns instead of horizontal bores perpendicular to the interior face. The workplane should produce X-axis cylinders so the holes are drilled into the face. Additionally, `hole_x` incorrectly reuses `shelf_pin_row_inset` (a Y-direction value) for the X position, placing holes outside the panel thickness.
- **Shelf pin hole x-position** is identical for both left and right panels (both branches compute `side_thickness / 2`).
- **`evaluation.py`** emits a duplicate drawer height error (same check runs in both `validate_drawer_dims` and the evaluation layer).

### Cutlist / BOM gaps
- ~~**`cutlist.extract_bom_parametric`** silent empty-list bug~~ — already correct in current code; fallback path returns one placeholder panel per input part when CadQuery is unavailable.
- ~~**`generate_cutlist` gaps**~~ — fixed: `columns` parameter added; dividers, drawer box parts (5/8" sides/front/back, 1/4" dado-captured bottoms), and applied false fronts (finished_wood) are now included. BOM grouped by material/thickness with uncut sheet counts. Files written to `~/.cabinet-mcp/cutlists/`.

### Visualizer bugs
- **`visualize_cabinet` "O" shortcut** (open drawers) does not work — drawers remain closed regardless of keypress.
- **`visualize_cabinet` pulls not rendered** — drawer pulls/handles from `design_pulls` are not included in the 3D model; the viewer shows bare drawer fronts.

## Planned enhancements

- **`generate_cutlist` `columns` support** — accept the same `columns` array as `design_multi_column_cabinet` so dividers, drawer boxes (at correct thicknesses), and false fronts are all included in one complete BOM.
- **Material-aware BOM summary** — output a "sheet goods to order" table grouped by thickness (3/4", 1/2", 1/4") and material type (Baltic Birch, hardwood, veneered panel), with uncut sheet counts rather than individual panel dimensions.
- **Cutlist file output** — write JSON/CSV to disk (e.g. `~/.cabinet-mcp/cutlists/`) and return the file path, consistent with how `visualize_cabinet` works.
- **Cutlist sheet-layout viewer** — generate a self-contained HTML file showing the guillotine cut layout per sheet, so the user can see exactly how panels nest on each 4×8.
- **Cutlist PDF export** — printable shop document with panel list, sheet layouts, and hardware BOM; useful at the bench without a screen.
