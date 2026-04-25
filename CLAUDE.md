# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Full install — CadQuery, opcut, rectpack, and dev tools (recommended)
uv pip install -e ".[full,dev]"

# Lite install — pure-Python only: parametric checks, cutlist BOM, MCP, evals
uv pip install -e .

# Or just sync everything via uv (default-groups = full + dev, so this is equivalent to full)
uv sync

# Run the MCP server (stdio, for Claude Desktop / Gemini CLI)
uv run cabinet-mcp

# Lite mode — skips CadQuery, opcut, and rectpack
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
- **opcut item IDs must be globally unique.** opcut 0.1.3 uses item IDs as a set for placement tracking; duplicate IDs cause `Exception('result is done')` mid-solve. `_optimize_with_opcut` assigns IDs via a global counter (`name__0`, `name__1`, …) to avoid collisions when multiple `CutlistPanel` objects share the same name.

### Module responsibilities

| Module | Responsibility |
|---|---|
| `hardware.py` | Frozen specs for Blum/Accuride/Salice drawer slides and Blum Clip Top hinges; `HingeSpec.hinges_for_height()` and `hinge_positions()` implement manufacturer placement rules |
| `joinery.py` | `DrawerJoinerySpec.from_stock()` computes all cut dimensions; `DominoSpec`, `PocketScrewSpec`, `BiscuitSpec`, `DowelSpec` each provide `count_for_span()` and `positions_for_span()` |
| `cabinet.py` | `CabinetConfig` with `drawer_config` list of `(height_mm, opening_type)` tuples; `carcass_joinery` field selects method |
| `drawer.py` | `DrawerConfig` computes box dimensions from opening + slide clearances; `joinery_style` applies corner joints |
| `door.py` | `DoorConfig` for single doors and matched pairs; full/half/inset overlay; hinge cup borings via CadQuery |
| `evaluation.py` | `evaluate_cabinet(cfg) -> list[Issue]`; `Issue` has `severity`, `measured`, `threshold`; CadQuery path adds interference checks |
| `cutlist.py` | `consolidate_bom()` (merges by name + dims), `optimize_cutlist(algorithm=)` — opcut FORWARD_GREEDY (primary), rectpack GuillotineBssfSas (optional, `algorithm="rectpack"`), strip-cutting (pure-Python fallback); `generate_sheet_layout_html()` produces a self-contained HTML file with per-sheet SVG layouts, numbered breakdown cut lines with dimensions, and rotated part labels; `generate_sheet_layout_pdf()` produces an A4-landscape PDF with sheet drawings, parts list, and guillotine cut sequence tables; `to_json()`, `to_csv()` |
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
- ~~**`consolidate_bom` merges differently-named identical panels**~~ — fixed: `name` is now part of the consolidation key, so "top" and "bottom" panels with the same dimensions stay distinct.

### Visualizer bugs
- ~~**`visualize_cabinet` "O" shortcut** (open drawers) does not work~~ — fixed: `pullVec` was computed in world space (via `Box3.setFromObject`) but applied to local-space `position.add()`; root node has −90° X rotation so world Z ≠ local Y. Fix: hardcode pull direction as local −Y and read depth from world Z extent.
- **`visualize_cabinet` pulls not rendered** — drawer pulls/handles from `design_pulls` are not included in the 3D model; the viewer shows bare drawer fronts.

## Planned enhancements

- **Cutlist PDF hardware BOM** — the PDF currently shows sheet layouts and cut parts; add a hardware BOM page (slides, hinges, pulls with quantities).
