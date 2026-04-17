# cadquery-furniture

Parametric cabinet design, MCP server, and eval harness built on [CadQuery](https://github.com/CadQuery/cadquery).

## Overview

1. **Parametric modeling** — cabinets, drawers, doors, and shelves defined as Python dataclasses; CadQuery builds the geometry
2. **Joinery selection** — four drawer corner joints and five carcass joinery methods, all fully parametric
3. **Design evaluation** — automated checks for hardware clearances, shelf deflection, dimensional consistency, and joinery adequacy
4. **BOM & cutlist** — extract bills of materials and export optimized cutlists for sheet goods
5. **Presets** — fourteen named, pre-validated starting configurations spanning kitchen, workshop, bedroom, bathroom, storage, and living room / foyer furniture types
6. **MCP server** — expose the pipeline as tools for Claude Desktop, Gemini CLI, or any MCP-compatible host
7. **Eval harness** — 51 realistic cabinetry scenarios with typed assertions; run `python -m evals` to benchmark any code change

Evaluation, cutlist, MCP, and eval harness all work without CadQuery installed. CadQuery is only needed for 3D geometry, interference detection, and visual output.

## Architecture

```
┌───────────────────────────────────────────────┐
│  hardware.py                                  │
│  Drawer slides · Blum Clip Top hinges         │
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
│  joinery       │    │                      │    │ borings  │
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
                     │  13 tools             │    │  scenarios.py       │
                     │  stdio + HTTP/SSE     │    │  51 scenarios       │
                     │  auto port-finding    │    │  212 assertions     │
                     └───────────────────────┘    └─────────────────────┘
```

## Modules

### `hardware.py`
Drawer slide and door hinge specifications as frozen dataclasses.

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

### `drawer.py`
Parametric drawer box generator. Computes box dimensions from opening size and hardware clearances. The `joinery_style` field applies QQQ, half-lap, or drawer-lock cuts at all four corners.

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
MCP server exposing the full pipeline as thirteen tools over stdio (default) or HTTP/SSE (`--http`). See the [MCP Server](#mcp-server) section below.

### `evals/`
Eval harness for benchmarking the server against realistic cabinetry prompts. See the [Eval Harness](#eval-harness) section below.

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

## MCP Server

The toolkit ships `server.py` so Claude Desktop, Gemini CLI, or any MCP-compatible host can design cabinets conversationally.

### Tools

| Tool | What it does |
|---|---|
| `list_presets` | Browse the named preset catalogue; filter by category or tag |
| `apply_preset` | Load a preset config dict; optionally override individual fields |
| `list_hardware` | Catalogue of slides and hinges (keys, specs, clearances) |
| `list_joinery_options` | Drawer and carcass joinery styles; Domino tenon sizes |
| `design_cabinet` | Parametric layout — panel sizes, opening stack, joinery |
| `evaluate_cabinet` | Full structural/fit evaluation; returns issues by severity |
| `auto_fix_cabinet` | One-pass deterministic repair of common errors (stack height, rabbet alignment) |
| `describe_design` | Human-readable prose summary for design review before visualization |
| `design_door` | Door dimensions, hinge count, and Z-positions for an opening |
| `design_drawer` | Drawer box dimensions and joinery cut specs |
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
Scenarios:   51/51 passed
Assertions:  212/212 passed
Pass rate:   100.0%
Score:       100.0%
```

### Scenario catalogue

| Tag | Count | What it covers |
|-----|-------|----------------|
| `basic_cabinet` | 7 | Standard, narrow, tall, wide, shallow cabinets |
| `drawer` | 6 | Butt, QQQ, half-lap, drawer-lock joints |
| `door` | 8 | Full/half/inset overlay, pairs, BLUMOTION, tall doors (3 hinges) |
| `joinery` | 12 | All drawer styles + all carcass methods + side-by-side comparisons |
| `cutlist` | 2 | JSON + CSV output, custom sheet sizes |
| `kitchen` | 6 | Multi-tool workflows: drawers + doors, full kitchen design, kitchen presets |
| `presets` | 12 | list_presets filtering, apply_preset, overrides, mismatch warning, unknown name |
| `living_room` | 6 | Console table, credenza, sideboard, media console presets + describe |
| `evaluation` | 7 | Designs that should produce errors (overflow stack, thin panels, clearances) |
| `edge_case` | 8 | Extreme dimensions, unusual configs, preset override edge cases |
| `workshop` | 2 | Tool chest preset, heavy-duty slide validation |
| `auto_fix` | 4 | Oversized stack repair, undersized no-op, clean pass-through, full workflow |
| `describe` | 3 | Basic cabinet prose, credenza preset summary, full workflow |
| `workflow` | 6 | End-to-end: design → evaluate → auto-fix → describe sequences |

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
pytest tests/ -v        # 356 unit + integration tests
python -m evals         # 51 eval scenarios, 212 assertions
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
