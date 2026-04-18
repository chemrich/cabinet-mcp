# cadquery-furniture

Parametric cabinet design, MCP server, and eval harness built on [CadQuery](https://github.com/CadQuery/cadquery).

## Overview

1. **Parametric modeling** — cabinets, drawers, doors, and shelves defined as Python dataclasses; CadQuery builds the geometry
2. **Joinery selection** — four drawer corner joints and five carcass joinery methods, all fully parametric
3. **Design evaluation** — automated checks for hardware clearances, shelf deflection, dimensional consistency, and joinery adequacy
4. **BOM & cutlist** — extract bills of materials and export optimized cutlists for sheet goods
5. **Presets** — fourteen named, pre-validated starting configurations spanning kitchen, workshop, bedroom, bathroom, storage, and living room / foyer furniture types
6. **Standard drawer box heights** — automatic snapping to industry-standard box heights (3"–12" in 1" steps) for simplified batch ordering
7. **Multi-column cabinets** — single carcass with multiple side-by-side vertical columns separated by interior dividers
8. **Proportion system** — graduated drawer heights and proportional column widths via named presets (`equal`, `subtle`, `classic`, `golden`)
9. **Legs & feet** — catalog of furniture legs with placement, load checking, and hardware BOM integration
10. **MCP server** — expose the pipeline as tools for Claude Desktop, Gemini CLI, or any MCP-compatible host
11. **Eval harness** — 62 realistic cabinetry scenarios with typed assertions; run `python -m evals` to benchmark any code change

Evaluation, cutlist, MCP, and eval harness all work without CadQuery installed. CadQuery is only needed for 3D geometry, interference detection, and visual output.

## Architecture

```
┌───────────────────────────────────────────────┐
│  hardware.py                                  │
│  Drawer slides · Blum Clip Top hinges         │
│  Furniture legs / feet                        │
│  (specs, validation, hinge placement rules)   │
└──────────────────┬────────────────────────────┘
                   │
    ┌──────────────┴───────────────┐
    │                              │
    ▼                              ▼
┌─────────────┐         ┌──────────────────────┐
│ joinery.py  │         │ hardware.py           │
│ Drawer and  │◄────────│ (slides + hinges)     │
│ carcass     │         └──────────────────────┘
│ joint specs │
└──────┬──────┘
       │ consumed by
    ┌──┴────────────────────────────────┐
    │                                   │
    ▼                                   ▼
┌────────────────┐    ┌──────────────────────┐    ┌──────────┐
│  cabinet.py    │    │  drawer.py           │    │ door.py  │
│  Carcass with  │    │  Drawer boxes with   │    │ Door     │
│  dado/Domino/  │    │  QQQ/half-lap/lock   │    │ panels   │
│  pocket-screw  │    │  corner joints       │    │ + hinge  │
│  joinery       │    │  Standard heights    │    │ borings  │
│  Multi-column  │    │                      │    │          │
│  ColumnConfig  │    │                      │    │          │
└───────┬────────┘    └──────────┬───────────┘    └────┬─────┘
        │                        │                      │
        └────────────────────────┴──────────────────────┘
                                 │ Assembly + PartInfo
                                 ▼
                     ┌───────────────────────┐
                     │  evaluation.py        │
                     │  - Interference       │
                     │  - Hardware clear.    │
                     │  - Shelf deflection   │
                     │  - Joinery adequacy   │
                     │  - Door/hinge checks  │
                     │  Returns: [Issue]     │
                     └───────────┬───────────┘
                                 │ PartInfo
                                 ▼
                     ┌───────────────────────┐
                     │  cutlist.py           │
                     │  - BOM extraction     │
                     │  - Consolidation      │
                     │  - JSON / CSV export  │
                     └───────────────────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │  presets.py           │
                     │  14 named configs     │
                     │  list_presets /       │
                     │  apply_preset         │
                     └───────────┬───────────┘
                                 │
                     ┌───────────┴───────────┐
                     │  auto_fix.py          │
                     │  1-pass auto-repair   │
                     │  describe.py          │
                     │  prose summaries      │
                     └───────────┬───────────┘
                                 │
                     ┌───────────┴───────────┐    ┌─────────────────────┐
                     │  server.py            │    │  evals/             │
                     │  MCP server           │    │  harness.py         │
                     │  15 tools             │    │  scenarios.py       │
                     │  stdio + HTTP/SSE     │    │  62 scenarios       │
                     │  auto port-finding    │    │  250 assertions     │
                     └───────────────────────┘    └─────────────────────┘
```

## Modules

### `hardware.py`
Drawer slide, door hinge, and furniture leg specifications as frozen dataclasses.

**Drawer slides:**

| Key | Model | Type | Load | Extension |
|-----|-------|------|------|-----------|
| `blum_tandem_550h` | Blum Tandem 550H | Undermount | 30 kg | Partial |
| `blum_tandem_plus_563h` | Blum Tandem Plus 563H | Undermount | 45 kg | Full |
| `blum_movento_760h` | Blum Movento 760H | Undermount | 40 kg | Full |
| `blum_movento_769` | Blum Movento 769 | Undermount | 77 kg | Full |
| `accuride_3832` | Accuride 3832 | Side-mount | 45 kg | Full |
| `salice_futura` | Salice Futura | Undermount | 45 kg | Full |
| `salice_progressa_plus` | Salice Progressa+ | Undermount | 54 kg | Full |

Each spec knows its clearance requirements and can validate drawer dimensions.

**Door hinges — Blum Clip Top family:**

| Key | Overlay | Soft-close | Part # |
|-----|---------|-----------|--------|
| `blum_clip_top_110_full` | Full (16 mm) | No | 71B3550 |
| `blum_clip_top_blumotion_110_full` | Full (16 mm) | Yes | 71B3590 |
| `blum_clip_top_110_half` | Half (9.5 mm) | No | 71H3550 |
| `blum_clip_top_blumotion_110_half` | Half (9.5 mm) | Yes | 71H3590 |
| `blum_clip_top_110_inset` | Inset (0 mm) | No | 71N3550 |
| `blum_clip_top_blumotion_110_inset` | Inset (0 mm) | Yes | 71N3590 |
| `blum_clip_top_170_full` | Full (16 mm) | No | 71B3750 |

All Clip Top hinges use a 35 mm cup (13 mm deep, 22.5 mm from door edge). `HingeSpec` provides `hinges_for_height()` and `hinge_positions()` implementing Blum's published hinge-count and placement rules.

**Furniture legs (`LegSpec`):**

| Key | Model | Height | Adjustable | Load | Finish |
|-----|-------|--------|-----------|------|--------|
| `richelieu_176138106` | Richelieu Contemporary Square Leg | 100 mm (3-15/16") | No | 50 kg | Brushed nickel |
| `richelieu_17613b106` | Richelieu Contemporary Square Leg | 100 mm | No | 50 kg | Matte black |
| `richelieu_adjustable_40mm` | Richelieu Adjustable Leg | 40–65 mm | Yes (M8) | 60 kg | Aluminum |
| `hairpin_200mm` | Hairpin Leg 200 mm | 200 mm | No | 30 kg | Matte black |

`get_leg(key)` returns the `LegSpec`. Use the `design_legs` MCP tool for placement coordinates and load checking.

### `joinery.py`
Parametric joint specifications for drawer corners and cabinet carcasses.

**Drawer corner joints** (`DrawerJoineryStyle`):

| Style | Key | Description | Router bit? |
|-------|-----|-------------|-------------|
| Butt | `BUTT` | Plain butt joint, glue + fastener | No |
| QQQ | `QQQ` | Quarter-Quarter-Quarter locking rabbet (Phipps) | No |
| Half-lap | `HALF_LAP` | Overlapping half-depth rabbet at each corner | No |
| Drawer lock | `DRAWER_LOCK` | Stepped L-tongue/socket via router bit | Yes |

The QQQ system (Stephen Phipps, *This Is Carpentry*, 2014): dado blade set to width = height = fence-distance = ½ stock thickness. The resulting locking rabbet is stronger than a dovetail in shear. Requires true-thickness stock.

`DrawerJoinerySpec.from_stock(style, side_thickness, front_back_thickness)` computes all cut dimensions from stock sizes.

**Carcass joinery** (`CarcassJoinery`):

| Method | Key | Notes |
|--------|-----|-------|
| Dado & rabbet | `DADO_RABBET` | Default; already modelled in `cabinet.py` |
| Floating tenon | `FLOATING_TENON` | Festool Domino system |
| Pocket screw | `POCKET_SCREW` | Kreg-style angled pocket |
| Biscuit | `BISCUIT` | #0 / #10 / #20; primarily for alignment |
| Dowel | `DOWEL` | 8 mm / 10 mm; compatible with 32 mm grid |

**Festool Domino sizes** (DF 500 and DF 700 machines):

| Key | Tenon | Machine |
|-----|-------|---------|
| `4x17` | 4 × 17 mm | DF 500 |
| `5x19` | 5 × 19 mm | DF 500 |
| `5x30` | 5 × 30 mm | DF 500 |
| `6x40` | 6 × 40 mm | DF 500 |
| `8x40` | 8 × 40 mm | DF 500 |
| `8x50` | 8 × 50 mm | DF 500 |
| `10x24` | 10 × 24 mm | DF 700 |
| `10x50` | 10 × 50 mm | DF 700 |
| `14x28` | 14 × 28 mm | DF 700 |
| `14x56` | 14 × 56 mm | DF 700 |

`DominoSpec`, `PocketScrewSpec`, `BiscuitSpec`, and `DownelSpec` each provide `count_for_span()` and `positions_for_span()` for automatic fastener layout.

### `cabinet.py`
Parametric base cabinet with dado/rabbet joinery, optional shelf pin holes, and a configurable opening stack (`"drawer"`, `"door"`, `"door_pair"`, `"shelf"`, `"open"`). The `carcass_joinery` field selects the joinery method; companion spec fields configure the layout.

`CabinetConfig` also supports multi-column layouts via the `columns: list[ColumnConfig]` field. When set, the cabinet interior is divided into side-by-side vertical sections by interior vertical dividers, each with its own slot stack. Column widths (interior) must sum to `interior_width`; the evaluator enforces this.

`CabinetConfig` carries `leg_key`, `leg_count`, and `leg_inset` so the visualizer and `design_legs` tool share the same hardware choice.

### `proportions.py`
Furniture proportion utilities for drawer heights and column widths. See [Proportion System](#proportion-system) for a full explanation of the design principles and available presets.

**`graduated_drawer_heights(total_mm, num_drawers, ratio)`** — returns a list of opening heights ordered bottom-to-top that sum exactly to `total_mm`. Heights follow a geometric progression: each drawer is `1/ratio` the height of the drawer below it, so the bottom drawer is always the tallest. Any rounding residual is absorbed by the bottom drawer.

**`column_widths(total_mm, num_columns, wide_index, ratio)`** — distributes `total_mm` across `num_columns` columns. The column at `wide_index` is `ratio` times the width of each of the remaining equal-width columns. Pass `wide_index=None` for equal widths.

**`describe_proportions(total_mm, num_drawers, ratio)`** — returns a summary dict (preset name, ratio, heights list, bottom-to-top ratio) useful for presenting options before committing to a layout.

Both functions accept a float ratio or a named preset string — see the [Proportion System](#proportion-system) section for values and guidance on when to use each.

### `drawer.py`
Parametric drawer box generator. Computes box dimensions from opening size and hardware clearances. The `joinery_style` field applies QQQ, half-lap, or drawer-lock cuts at all four corners.

When `use_standard_height=True` (the default), `box_height` snaps down to the nearest value in `STANDARD_BOX_HEIGHTS` (3"–12" in 1" increments) so drawer boxes can be batch-ordered from common stock. Set `use_standard_height=False` to use the full clearance-adjusted height instead. The `standard_box_height` property always returns the snapped value for reference regardless of the flag.

### `door.py`
Parametric door generator supporting single doors and matched pairs in full, half, and inset overlay. Door width, height, and hinge positions are computed from `HingeSpec` and opening dimensions. CadQuery builds hinge cup borings (35 mm × 13 mm) into the door back face.

### `evaluation.py`
Design verification with checks for cumulative heights, hardware clearances, shelf deflection, back panel fit, dado alignment, door/hinge adequacy, drawer joinery geometry, Domino/pocket-screw/dowel panel thickness, and (with CadQuery) interference and drawer-in-opening fit. Returns typed `Issue` objects with severity, measured value, and threshold.

### `cutlist.py`
BOM extraction, panel consolidation, and export to JSON (cut-optimizer-2d format), CSV, or formatted console table. Grain direction is tracked as an optimization constraint.

### `presets.py`
Nine named, pre-validated `CabinetConfig` instances covering common cabinet types across five categories. Each preset has opening-stack heights pre-calculated to fill `interior_height` exactly, so they pass evaluation out of the box. Exposed via the `list_presets` and `apply_preset` MCP tools.

| Name | Category | Dimensions | Notes |
|------|----------|-----------|-------|
| `kitchen_base_3_drawer` | kitchen | 600×720×550 | 300/192/192 mm drawer stack, Blum Tandem 550H |
| `kitchen_base_door_2_drawer` | kitchen | 600×720×550 | Deep door at bottom, two drawers above |
| `kitchen_base_door_pair_wide` | kitchen | 900×720×550 | Door pair + 2 drawers, half-overlay hinges |
| `kitchen_tall_pantry` | kitchen | 600×2100×550 | Two door pairs + shelf section, BLUMOTION |
| `workshop_tool_chest` | workshop | 600×900×550 | 6×144 mm drawers, Movento 769 (77 kg), pocket-screw |
| `workshop_wall_cabinet` | workshop | 600×720×300 | Door pair + adjustable shelves, shallow depth |
| `bedroom_dresser` | bedroom | 900×1100×550 | 6-drawer, Tandem+ full-extension |
| `bathroom_vanity` | bathroom | 600×850×480 | Door + 2 drawers, BLUMOTION soft-close |
| `storage_wall_cabinet` | storage | 600×720×300 | Door pair + adjustable shelves, shallow depth |
| `foyer_console_2_drawer` | living_room | 1200×800×350 | Open shelf + 2 drawers, shallow 350 mm depth |
| `foyer_console_narrow` | living_room | 900×850×300 | Single drawer + open shelf, tight-entryway depth |
| `living_room_credenza` | living_room | 1600×800×450 | Door pair + 2 frieze drawers, Tandem+ / BLUMOTION |
| `living_room_sideboard` | living_room | 1800×900×500 | Door pair + 2 drawers, wider/taller than credenza |
| `media_console` | living_room | 1800×600×450 | Low-profile: door pair + open display shelf |

### `auto_fix.py`
Single-pass deterministic fixer for common configuration errors. Currently handles `cumulative_heights` (rebalances an opening stack that overshoots or undershoots interior height) and `back_panel_fit` (aligns rabbet depth with back thickness). Returns an `AutoFixResult` with the modified config, a list of human-readable changes, and before/after issue lists.

### `describe.py`
Generates human-readable prose summaries of a `CabinetConfig` — dimensions in metric + imperial, opening layout, hardware names, joinery method, materials — for presenting to the user during the review step of the design workflow.

### `server.py`
MCP server exposing the full pipeline as fifteen tools over stdio (default) or HTTP/SSE (`--http`). See the [MCP Server](#mcp-server) section below.

### `evals/`
Eval harness for benchmarking the server against realistic cabinetry prompts. See the [Eval Harness](#eval-harness) section below.

## Proportion System

Cabinet furniture has a long tradition of graduated proportions — drawers that get shorter as they rise, columns that widen toward a visual anchor — documented in woodworking literature going back to the 18th century. The `proportions.py` module encodes the most cited systems as named presets so users can describe a layout in plain English ("classic graduation, golden column widths") and get mathematically correct dimensions back.

### Drawer height graduation

A **graduated drawer stack** is one where each drawer is shorter than the drawer below it by a consistent ratio. The result reads as visually stable: heavy storage at the base, lighter items near eye level. The math is a geometric progression:

```
bottom height = H
next up       = H / r
next up       = H / r²
  ⋮
top drawer    = H / r^(n-1)
```

where `r` is the graduation ratio and `H` is chosen so all heights sum to the target interior height.

**Named presets:**

| Preset | Ratio | Character | Best for |
|--------|-------|-----------|----------|
| `"equal"` | 1.0 | Uniform — all drawers identical | Tool chests, utilitarian storage |
| `"subtle"` | 1.2× | Gentle — barely noticeable on 3 drawers, clear on 5+ | Modern minimalist furniture |
| `"classic"` | 1.4× | Traditional — the standard cabinet-maker's graduation; reads clearly at 3–5 drawers | Dressers, sideboards, kitchen bases |
| `"golden"` | 1.618× (φ) | Dramatic — approximates the Fibonacci sequence; strong visual hierarchy | Showpiece furniture, 3–4 drawers only |

**Example — 5-drawer sideboard, 864 mm interior height:**

| Preset | Bottom → Top (mm) | Top drawer |
|--------|-------------------|------------|
| `equal` | 173 / 173 / 173 / 173 / 173 | 173 mm (6¾") |
| `subtle` | 241 / 201 / 167 / 139 / 116 | 116 mm (4½") |
| `classic` | 303 / 217 / 155 / 110 / 79 | 79 mm (3⅛") |
| `golden` | ✗ too steep — top drawer falls below 75 mm minimum | — |

The golden ratio is impractical past 4 drawers in a typical cabinet height because the top drawer shrinks below a usable size. `graduated_drawer_heights()` raises a `ValueError` in that case rather than returning an unusable layout.

**As a proportion shortcut in the MCP tools:**

```
design_cabinet(width=600, height=900, depth=457,
               num_drawers=5, drawer_proportion="classic")
```

The tool computes `interior_height = height − top_thickness − bottom_thickness`, calls `graduated_drawer_heights`, and inserts the results as `drawer_config` automatically. The response includes a `proportions_used` field confirming which preset was applied.

---

### Column width proportions

A **proportional column layout** places one accent column that is `ratio` times the width of each flanking column. The flanking columns are always equal to each other; only one column is wider.

**Named presets (same names, applied to width):**

| Preset | Ratio | What it looks like (3 columns, 1184 mm interior) |
|--------|-------|---------------------------------------------------|
| `"equal"` | 1.0 | 395 / 395 / 395 mm |
| `"subtle"` | 1.2× | 370 / 444 / 370 mm — a modest centre emphasis |
| `"classic"` | 1.4× | 348 / 488 / 348 mm — clearly wider centre |
| `"golden"` | 1.618× (φ) | 327 / 530 / 327 mm — strong focal centre |

`wide_index` controls *which* column is the accent:
- `wide_index=1` (centre) — the conventional sideboard and dresser layout
- `wide_index=0` (left) or `wide_index=2` (right) — asymmetric compositions

**As a proportion shortcut in the MCP tools:**

```
design_multi_column_cabinet(
    width=1220, height=900, depth=457,
    num_columns=3, wide_index=1, column_proportion="golden",
    num_drawers=5,             drawer_proportion="classic",
)
```

This produces a complete 3-column, 15-drawer layout from six parameters — no manual arithmetic required. The response lists the resolved column widths and drawer heights alongside the `proportions_used` dict so the caller can inspect or override any value.

---

### Mixing explicit and proportional specs

The proportion shortcuts are additive, not exclusive:

- Supply an explicit `columns` array with `width_mm` values but no `drawer_config` → column widths are yours, drawer heights are computed from `drawer_proportion`
- Supply a full `columns` array (widths + drawer configs) and omit proportion parameters → existing behavior, no auto-computation
- Supply `num_columns` + proportion parameters but no `columns` array → full auto-layout

## Installation

```bash
# With CadQuery (full functionality)
pip install cadquery
pip install -e .

# Without CadQuery (parametric checks + cutlist + MCP + evals)
pip install -e .
```

## Quick Start

### From a preset

```python
from cadquery_furniture.presets import get_preset
from cadquery_furniture.evaluation import evaluate_cabinet, print_report

# Load a pre-validated starting point and tweak it
preset = get_preset("kitchen_base_3_drawer")
cfg = preset.config

# Override a field — presets are frozen, so replace via dataclasses.replace
from dataclasses import replace
cfg = replace(cfg, width=750, drawer_slide="blum_movento_760h")

issues = evaluate_cabinet(cfg)
print_report(issues)
```

### From scratch

```python
from cadquery_furniture.cabinet import CabinetConfig
from cadquery_furniture.joinery import CarcassJoinery, DominoSpec
from cadquery_furniture.evaluation import evaluate_cabinet, print_report

# 600 mm base cabinet: two QQQ drawers + full-height door
# Carcass joined with Festool Domino 8×40 at 150 mm spacing
cfg = CabinetConfig(
    width=600,
    height=900,
    depth=550,
    drawer_config=[
        (150, "drawer"),
        (200, "drawer"),
        (550, "door"),
    ],
    door_hinge="blum_clip_top_blumotion_110_full",
    carcass_joinery=CarcassJoinery.FLOATING_TENON,
    domino_spec=DominoSpec(size_key="8x40", max_spacing=150.0),
)

issues = evaluate_cabinet(cfg)
print_report(issues)
```

### Using proportions

```python
from cadquery_furniture.proportions import (
    graduated_drawer_heights,
    column_widths,
    describe_proportions,
)

# 5-drawer stack filling 864 mm of interior height, classic 1.4× graduation
heights = graduated_drawer_heights(864, num_drawers=5, ratio="classic")
# → [303.3, 216.6, 154.7, 110.5, 78.9]  (bottom → top, sums to 864)

# 3 columns across 1184 mm interior, golden-ratio centre column
widths = column_widths(1184, num_columns=3, wide_index=1, ratio="golden")
# → [326.7, 530.6, 326.7]  (left / centre / right)

# Human-readable summary of a proposed layout
print(describe_proportions(864, num_drawers=4, ratio="golden"))
# {
#   "preset": "golden", "ratio": 1.618,
#   "heights_bottom_to_top_mm": [386.1, 238.6, 147.5, 91.2],
#   "bottom_to_top_ratio": 4.234
# }
```

## MCP Server

The toolkit ships `server.py` so Claude Desktop, Gemini CLI, or any MCP-compatible host can design cabinets conversationally.

### Tools

| Tool | What it does |
|---|---|
| `list_presets` | Browse the named preset catalogue; filter by category or tag |
| `apply_preset` | Load a preset config dict; optionally override individual fields |
| `list_hardware` | Catalogue of slides, hinges, and legs (keys, specs, clearances) |
| `list_joinery_options` | Drawer and carcass joinery styles; Domino tenon sizes |
| `design_cabinet` | Parametric layout — panel sizes, opening stack, joinery; accepts `num_drawers` + `drawer_proportion` to auto-compute graduated heights |
| `design_multi_column_cabinet` | Cabinet with multiple columns; accepts `num_columns` + `column_proportion` + `wide_index` and `num_drawers` + `drawer_proportion` for fully proportional auto-layout |
| `evaluate_cabinet` | Full structural/fit evaluation; returns issues by severity |
| `auto_fix_cabinet` | One-pass deterministic repair of common errors (stack height, rabbet alignment) |
| `describe_design` | Human-readable prose summary for design review before visualization |
| `design_door` | Door dimensions, hinge count, and Z-positions for an opening |
| `design_drawer` | Drawer box dimensions, joinery cut specs, and standard height snapping |
| `design_legs` | Leg placement coordinates, load-per-leg check, and hardware BOM |
| `generate_cutlist` | BOM as JSON (cut-optimizer-2d compatible) and CSV |
| `compare_joinery` | Side-by-side drawer joinery cut dimensions for a stock thickness |
| `visualize_cabinet` | 3D assembly → GLB + HTML viewer with x-ray (X) and open-drawer (O) toggles |

The recommended workflow is: `list_presets` → `apply_preset` → `evaluate_cabinet` → (if errors) `auto_fix_cabinet` → `evaluate_cabinet` → `describe_design` → **user review** → `visualize_cabinet`. Tool descriptions enforce this sequence — the LLM is instructed never to skip evaluation or visualize before the user has approved the described design.

### Configure with Claude Code (recommended)

One-liner from any terminal — registers the server at user scope so it's available in every Claude Code session:

```bash
claude mcp add cabinet -- uv --directory /absolute/path/to/cabinet-mcp run cabinet-mcp
```

Verify:

```bash
claude mcp list      # should show "cabinet" connected
```

Inside a Claude Code session, `/mcp` lists connected servers and their tools. To remove or replace:

```bash
claude mcp remove cabinet
```

### Configure with Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "cabinet-mcp": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/cabinet-mcp", "run", "cabinet-mcp"]
    }
  }
}
```

Restart Claude Desktop — the ten tools appear automatically.

### Configure with Gemini CLI

Add to `~/.gemini/settings.json`:

```json
{
  "mcp": {
    "servers": {
      "cabinet-mcp": {
        "command": "uv",
        "args": ["--directory", "/absolute/path/to/cabinet-mcp", "run", "cabinet-mcp"]
      }
    }
  }
}
```

Or in HTTP mode, point at the SSE endpoint directly:

```json
{
  "mcp": {
    "servers": {
      "cabinet-mcp": { "url": "http://127.0.0.1:3749/sse" }
    }
  }
}
```

### Port management (HTTP/SSE mode)

The server defaults to stdio. Pass `--http` to run a persistent HTTP/SSE process instead. The default starting port is **3749**; it auto-increments if that port is occupied, so running multiple MCP servers simultaneously never collides.

```bash
cabinet-mcp --http                          # port 3749 (or next free)
cabinet-mcp --http --port 4200              # start search at 4200
cabinet-mcp --http --port 4200 --max-port-attempts 40
cabinet-mcp --http --host 0.0.0.0           # bind all interfaces
```

The chosen port is printed to stderr and written to `/tmp/cabinet-mcp.port` for easy discovery by scripts:

```bash
PORT=$(cat /tmp/cabinet-mcp.port)
curl "http://127.0.0.1:${PORT}/sse"
```

## Eval Harness

`evals/` provides a benchmark suite for measuring how well the server handles realistic cabinetry requests. Run it after any significant code change to catch regressions.

### Running

```bash
python -m evals                          # full suite
python -m evals --tag kitchen            # only kitchen scenarios
python -m evals --tag drawer --tag door  # multiple tags
python -m evals --difficulty advanced    # only hard scenarios
python -m evals --name overflow_drawer_stack  # one scenario by name
python -m evals --json                   # machine-readable output for CI
python -m evals --list                   # print scenario catalogue
```

### Baseline results

```
Scenarios:   62/62 passed
Assertions:  250/250 passed
Pass rate:   100.0%
Score:       100.0%
```

### Scenario catalogue

| Tag | Count | What it covers |
|-----|-------|----------------|
| `basic_cabinet` | 7 | Standard, narrow, tall, wide, shallow cabinets |
| `drawer` | 16 | Butt, QQQ, half-lap, drawer-lock joints + standard height snapping |
| `standard_height` | 4 | Height snapping to 4"/6"/8" tiers, opt-out, exact boundary match |
| `door` | 8 | Full/half/inset overlay, pairs, BLUMOTION, tall doors (3 hinges) |
| `joinery` | 12 | All drawer styles + all carcass methods + side-by-side comparisons |
| `cutlist` | 2 | JSON + CSV output, custom sheet sizes |
| `kitchen` | 6 | Multi-tool workflows: drawers + doors, full kitchen design, kitchen presets |
| `presets` | 12 | list_presets filtering, apply_preset, overrides, mismatch warning, unknown name |
| `living_room` | 6 | Console table, credenza, sideboard, media console presets + describe |
| `evaluation` | 8 | Designs that should produce errors (overflow stack, thin panels, column widths) |
| `edge_case` | 8 | Extreme dimensions, unusual configs, preset override edge cases |
| `workshop` | 2 | Tool chest preset, heavy-duty slide validation |
| `auto_fix` | 4 | Oversized stack repair, undersized no-op, clean pass-through, full workflow |
| `describe` | 3 | Basic cabinet prose, credenza preset summary, full workflow |
| `workflow` | 6 | End-to-end: design → evaluate → auto-fix → describe sequences |
| `legs` | 4 | Default Richelieu legs, load check, 6-leg pattern, list_hardware |
| `multi_column` | 3 | Drawers+door, width mismatch error, 3-column dresser |
| `hardware` | 6 | list_hardware for slides, hinges, and legs |

### Adding a scenario

Scenarios live in `evals/scenarios.py`. Each one has a natural-language `prompt` (what a user would say), a list of `ToolCall`s with typed `Assertion`s, and tags for filtering.

```python
_s(Scenario(
    name="my_new_scenario",
    prompt="Design a 900 mm tall pantry cabinet with adjustable shelves.",
    tags=["basic_cabinet"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 900, "depth": 550, "adj_shelf_holes": True},
            assertions=[
                Assertion("exterior.height_mm", Op.EQ, 900),
                Assertion("adj_shelf_holes",    Op.IS_TRUE),
            ],
        ),
    ],
))
```

Available assertion operators: `EQ`, `APPROX`, `GT`, `GTE`, `LT`, `LTE`, `IN`, `CONTAINS`, `HAS_KEY`, `LEN_EQ`, `LEN_GTE`, `IS_TRUE`, `IS_FALSE`, `NO_ERRORS`, `HAS_ERROR`, `HAS_WARNING`.

## Running Tests

```bash
pytest tests/ -v        # unit + integration tests
python -m evals         # 62 eval scenarios, 250 assertions
```

No CadQuery required for either suite.

## Hardware sources

All hardware dimensions are sourced from official manufacturer datasheets and confirmed distributor catalog listings. Part numbers and specs should be verified against the current revision of the relevant datasheet before purchasing. See the docstrings in `hardware.py` and `joinery.py` for per-item citations.

## Future Work

- **cut-optimizer-2d** Rust crate integration via subprocess for sheet nesting
- **Drawer travel swept-volume check** — verify drawers can open without collision
- **Edge banding calculator** — linear footage needed per edge
- **Shop drawing generation** — annotated SVG views from CadQuery geometry
- **Joinery BOM line items** — Domino tenon counts, pocket-screw pack quantities in cutlist output
- **FeatureScript-like constraint solver** for assembly mates

---

## Attributions

Hardware dimensions, placement rules, and part numbers in this project are derived from the following primary and secondary sources. All specs should be verified against current manufacturer documentation before purchasing.

### Drawer slides

- **Blum Tandem 550H** — Blum Inc. 550H official datasheet; distributor cross-reference via [mcfaddens.com](https://mcfaddens.com) and [interfitco.com](https://interfitco.com); CabinetParts.com SKU confirmations (450 mm = 550H4500B, 550 mm = 550H5500B).
- **Blum Tandem Plus 563H** — Blum 563H official datasheet © 2016; catalog index via cabinetdoor.store and d2.blum.com; CabinetParts.com confirmed SKUs (18" = 563H4570B, 21" = 563H5330B).
- **Blum Movento 760H** — Blum Movento brochure "The Evolution of Motion" (2016/2024); distributor SKU tables via [mcfaddens.com](https://mcfaddens.com) and [hwt-pro.com](https://hwt-pro.com); Amazon listings.
- **Blum Movento 769** — Blum 769 catalog page © 2019; CabinetParts and Indian River Cabinet Supply SKU listings; [rokhardware.com](https://rokhardware.com) spec page. Confirmed SKUs: 769.4570S (18"), 769.5330S (21"), 769.6100S (24").
- **Accuride 3832** — [Accuride International](https://www.accuride.com) product page and distributor listings.
- **Salice Futura** — Salice Futura catalog D0CASG010ENG; [wwhardware.com](https://wwhardware.com) specs. Confirmed SKUs via CabinetParts and woodworkerexpress.
- **Salice Progressa+** — Salice PROGRESSA catalog D0CASAA36USA; [cabinetparts.com](https://cabinetparts.com) SKU SHG5U6S533XXF6 (21" confirmed).

### Door hinges

- **Blum Clip Top 110° / 170° family** — Blum CLIP top official datasheet ([d2.blum.com/en/HingeDataSheet_cliptop.pdf](https://d2.blum.com/en/HingeDataSheet_cliptop.pdf)); Blum catalog "Kitchen & Bedroom" © 2023; confirmed SKUs via [hafele.com](https://hafele.com) and [hardware.com](https://hardware.com). BLUMOTION variants: 71B3590 (full), 71H3590 (half), 71N3590 (inset).
- Hinge count and placement rules (100 mm from top/bottom; spacing thresholds at 1 200 mm and 1 800 mm) from Blum published door-height/weight tables.

### Furniture legs

- **Richelieu 176138106** (100 mm brushed nickel contemporary square leg) — [thebuilderssupply.com](https://thebuilderssupply.com/richelieu-contemporary-furniture-leg-1761-176138106); [dspoutlet.com](https://dspoutlet.com/products/richelieu-3-15-16-100-mm-contemporary-furniture-leg-brushed-nickel-2-pack). Height confirmed as 3-15/16" (100 mm), not 4".
- **Richelieu adjustable leg** — [woodcraft.com](https://www.woodcraft.com/products/richelieu-1-9-16-40-mm-adjustable-contemporary-furniture-leg-dark-brown); [Richelieu Hardware catalog](https://www.richelieu.com/us/en/category/furniture-equipment/furniture-legs/adjustable-furniture-legs/1003965).

### Drawer box height standards

- Industry standard box heights (½" and 1" increment series, 3"–12") — [Cabinet Doors 'N' More](https://cabinetdoorsnmore.com/pages/how-to-drawer-boxes); [Eagle Woodworking](https://www.eaglewoodworking.com/dovetail-drawers/drawer-wood-types/maple-drawer-boxes).
- Kitchen drawer sizing conventions — [Sawmill Creek Woodworking Community](https://sawmillcreek.org/threads/kitchen-cabinet-top-drawer-sizing.316059/); [Kreg Tool — Demystifying Drawer Sizing](https://learn.kregtool.com/learn/demystifying-drawer-sizing/); [PALET Cabinetry Drawer Height Guide](https://paletcabinets.com/pages/drawer-height-specifications).

### Joinery

- **QQQ locking rabbet** — Stephen Phipps, *This Is Carpentry* (2014): "The Quarter-Quarter-Quarter Method." All cuts set to material thickness ÷ 2.
- **Festool Domino tenon dimensions** — Festool DF 500 and DF 700 official datasheets; confirmed mortise and tenon dimensions from Festool USA product pages.
- **Kreg pocket-screw geometry** — Kreg Tool Company pocket-screw jig documentation; [kregtool.com](https://www.kregtool.com).
- **Biscuit sizes** (#0, #10, #20) — industry-standard dimensions as catalogued by major manufacturers (Lamello, DeWalt, Porter-Cable).
