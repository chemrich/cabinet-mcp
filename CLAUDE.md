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
| `cabinet.py` | `CabinetConfig` with `drawer_config` list of `(height_mm, opening_type)` tuples; `carcass_joinery` field selects method; `build_multi_bay_cabinet` accepts `furniture_top=True` for "furniture top, flush bottom" overlay style |
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
- ~~**`cabinet.py` shelf pin holes wrong workplane**~~ — fixed: `make_side_panel` now uses "YZ" workplane (normal = X) so cylinders bore horizontally into the interior face. `x_start` computes correctly for both mirror/non-mirror panels.
- ~~**Shelf pin hole x-position** is identical for both panels~~ — fixed: left panel uses `side_thickness - shelf_pin_depth`, right uses `0`.
- ~~**`evaluation.py`** emits a duplicate drawer height error~~ — fixed: `check_drawer_carcass_clearances` now only flags the degenerate `box_height ≤ 0` case; the `min_drawer_height` check lives exclusively in `check_drawer_hardware_clearances`.
- ~~**Drawer dado / corner joinery on outside face**~~ — fixed: `make_drawer_side(cfg, side="left"|"right")` and `make_drawer_front_back(cfg, position="front"|"back")` now place the bottom dado and corner joinery on the inside face of each panel; `apply_drawer_joinery_to_side`/`_to_front_back` accept the same parameter. Verified by `tests/test_drawer_orientation.py` (10 intersect-volume probes, all four panels × BUTT and HALF_LAP).
- ~~**Drawer corner joinery (QQQ / HALF_LAP / DRAWER_LOCK) does not engage**~~ — fixed: introduced `DrawerJoinerySpec.engagement_x` (= `side_dado_depth_x` for non-BUTT, 0 for BUTT). Side panel now carries a uniform inside-face rabbet `engagement_x` deep in X and full `front_back_thickness` deep in Y. Sub-front / back is widened by `2 × engagement_x` and seats into that rabbet; `apply_drawer_joinery_to_front_back` is now a no-op. The QQQ ½-tongue and DRAWER_LOCK L-step are still recorded on the spec for the BOM but not modelled in 3D — this is a deliberate simplification to keep all non-BUTT joints geometrically valid (no material interference, no overhanging tongues). `tests/test_drawer_assembly.py` verifies bbox, side clearance, wall interference, bottom-dado engagement, bottom containment, and joint engagement across all four styles × three opening sizes (132 cases).

### Cutlist / BOM gaps
- ~~**`cutlist.extract_bom_parametric`** silent empty-list bug~~ — already correct in current code; fallback path returns one placeholder panel per input part when CadQuery is unavailable.
- ~~**`generate_cutlist` gaps**~~ — fixed: `columns` parameter added; dividers, drawer box parts (5/8" sides/front/back, 1/4" dado-captured bottoms), and applied false fronts (finished_wood) are now included. BOM grouped by material/thickness with uncut sheet counts. Files written to `~/.cabinet-mcp/cutlists/`.
- ~~**`consolidate_bom` merges differently-named identical panels**~~ — fixed: `name` is now part of the consolidation key, so "top" and "bottom" panels with the same dimensions stay distinct.

### Visualizer bugs
- ~~**`visualize_cabinet` pulls not rendered**~~ — fixed: `build_multi_bay_cabinet` now adds a `bay{i}_pull{j}_{k}` mesh for each pull placement; `visualize_cabinet` now forwards `drawer_pull` into per-column bay configs for multi-column layouts; the viewer tracks `bay{i}_pull{j}_{k}` nodes and animates them alongside the face when "O" is pressed.
- **`visualize_cabinet` "O" shortcut** (open drawers) does not work — investigation notes:
  - The viewer uses `<script type="module">` + importmap; must be served over HTTP (not `file://`) for Chrome — use `python3 -m http.server 8765` in `~/.cabinet-mcp/visualizations/`.
  - Root cause of O not working: `pair.box` is never populated for any of the 12 drawer pairs. The JS traversal looks up to grandparent (`p2 = obj.parent.parent`) for the `bay{i}_drawer{j}` group name, but Three.js r165 GLTFLoader appears to insert additional wrapper nodes, placing the named group deeper than 2 levels from the leaf mesh. Confirmed via console: `pair.face` is set on all pairs (face meshes are only 1 level deep) but `pair.box` is always null.
  - Next step: add temporary ancestry logging (`while (cur) { anc.push(cur.name); cur = cur.parent; }`) to a fresh render and read the actual depth, then extend the JS search loop to match that depth. Also investigate whether `gltf.scene` itself adds a wrapper level not present in the GLTF JSON node list.
- ~~**Pulls don't hide in X-ray mode**~~ — fixed: added `pullMeshes` array; pull mesh objects are pushed there during traversal alongside `pair.pulls`; `toggleXray` now iterates `[...drawerFronts, ...pullMeshes]`.

## Vertical overlay styles

`build_multi_bay_cabinet` supports two named parameters for controlling how the
top and bottom of the carcass relate to the drawer faces:

| Parameter | Effect |
|---|---|
| `face_bottom_overhang` | How far the lowest drawer face drops below the top surface of the bottom panel. Default 0 (face starts at top of bottom panel). Set to `bottom_thickness` for flush-to-carcass-exterior. |
| `face_top_overhang` | How far the highest drawer face rises above the underside of the top panel. Default 0. Set to `top_thickness` for flush-to-carcass-exterior. |
| `furniture_top` | Shorthand for "furniture top, flush bottom": automatically sets `face_bottom_overhang = bottom_thickness` so the lowest face drops to the carcass underside, and adds a `top_front_cap` strip that extends the top panel forward to the face plane. |

The `visualize_cabinet` MCP tool exposes `furniture_top` as a boolean parameter.

## Planned enhancements

- **Cutlist PDF hardware BOM** — the PDF currently shows sheet layouts and cut parts; add a hardware BOM page (slides, hinges, pulls with quantities).
