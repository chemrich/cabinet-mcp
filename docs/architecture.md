# Architecture

All units are millimetres. CadQuery is optional — the parametric core, evaluation, cutlist/BOM, project store, assembly planner, and the MCP server all run without it (the "lite" install); CadQuery adds 3D geometry, interference checks, and the GLB/HTML viewer.

```
hardware.py + joinery.py                ← specs, placement rules, prices
        │
        ▼
cabinet.py / drawer.py / door.py        ← parametric dataclasses
        │
        ▼
project.py                              ← multi-cabinet projects, shared tokens,
        │                                  persistence (~/.cabineteer/projects/)
        ▼
evaluation.py                           ← typed Issue objects (severity, value, limit)
        │
        ▼
cutlist.py / assembly.py                ← BOM, sheet optimisers, banding plans,
        │                                  assembly plans; HTML/PDF/CSV/JSON
        ▼
server.py                               ← 30 MCP tools over stdio or HTTP/SSE
```

`evals/` imports the server's tool handler functions directly via `TOOL_DISPATCH`, bypassing MCP transport entirely. The full suite (305 scenarios / 1,139 assertions) runs in under a second.

## Modules

| Module | Responsibility |
|---|---|
| `hardware.py` | Frozen specs for Blum/Accuride/Salice slides, Blum Clip Top hinges (real SKUs + mounting plates), Richelieu/hairpin legs, 45 pulls; manufacturer placement rules; `PRICE_LIST`. |
| `joinery.py` | `DrawerJoinerySpec.from_stock()` computes all drawer-corner cut dimensions; `DominoSpec` / `PocketScrewSpec` / `BiscuitSpec` / `DowelSpec` provide `count_for_span()` / `positions_for_span()`; miter-mortise placement solver; carcass Domino size rule. |
| `cabinet.py` | `CabinetConfig` — opening stacks, multi-column layouts, materials, corner style, edge banding fields; computed `@property` dimensions. |
| `drawer.py` | `DrawerConfig` — box dimensions from opening + slide clearances; corner joinery; size-based bottom-thickness rule; standard-height snapping. |
| `door.py` | Single doors and matched pairs in full/half/inset overlay; hinge counts and cup borings. |
| `proportions.py` | Geometric-progression drawer heights and asymmetric column widths via named ratios. |
| `project.py` | `CabinetProject` — shared design tokens with per-cabinet overrides, worktop spec, JSON persistence, library ops (list/rename/delete/duplicate with lineage), delta patching. |
| `evaluation.py` | `evaluate_cabinet(cfg) -> list[Issue]` — clearances, deflection, overlay collisions, banding feasibility, miter feasibility; CadQuery path adds interference checks. |
| `cutlist.py` | `consolidate_bom()`, four sheet-layout algorithms (opcut / rectpack / strip / rips_first), part-ID assignment, hardware BOM with pack math and prices, edge-band planning, HTML/PDF/CSV/JSON output. |
| `assembly.py` | `build_assembly_plan(cfg)` — joint census, per-panel mortise maps, machine setup blocks, consumables, ordered dry-fit-first steps; HTML/PDF renderers. |
| `presets.py` | 26 pre-validated `CabinetConfig` instances; exposed as `list_presets` / `apply_preset`. |
| `auto_fix.py` | Single-pass deterministic repair of stack-height and back-panel-fit issues. |
| `describe.py` | Prose summary (metric + imperial) for the design-review step. |
| `visualize.py` | GLB export + self-contained HTML viewer generation; procedural wood-finish textures; viewer JS. |
| `paths.py` | `data_dir()` — resolves `~/.cabineteer` (with one-time migration from the pre-rename `~/.cabinet-mcp`). |
| `server.py` | MCP server; `main()` entry point; `--http` flips stdio → HTTP/SSE; port auto-increments from 3749; shared `_cutlist_pipeline()` behind both cutlist tools. |

## Design patterns

- **Dataclasses everywhere; specs are frozen, configs are not.** Hardware/joinery specs and project dataclasses are `@dataclass(frozen=True)`; the three user-facing configs (`CabinetConfig`, `DrawerConfig`, `DoorConfig`) are plain dataclasses whose `__post_init__` normalizes input. Derived values are `@property`.
- **CadQuery is optional.** `try: import cadquery` throughout; evaluation and cutlist have CadQuery-backed and pure-Python paths. Tests and evals exercise the pure-Python paths, so they run everywhere.
- **MCP tool handlers are plain async functions** returning `list[types.TextContent]` — the eval harness calls them directly with no transport.
- **Documents agree with each other.** The joint census that counts BOM tenons is the one that draws the assembly maps; the part IDs on cut sheets are the ones in the assembly steps; edge-band markers on cutlist rows are the authority for the banding doc. One source of truth per fact, rendered many ways.
