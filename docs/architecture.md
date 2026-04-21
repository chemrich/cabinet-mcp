# Architecture

All units are millimetres. CadQuery is optional — `evaluation.py`, `cutlist.py`, the MCP server, and the eval harness all run without it.

```
hardware.py  +  joinery.py
        │
        ▼
cabinet.py / drawer.py / door.py    ← frozen dataclasses, computed @property
        │
        ▼
evaluation.py                        ← typed Issue objects
        │
        ▼
cutlist.py                           ← BOM, guillotine optimiser, JSON, CSV
        │
        ▼
server.py                            ← 15 MCP tools over stdio or HTTP/SSE
```

`evals/` imports the server's tool handler functions directly via `TOOL_DISPATCH`, bypassing MCP transport entirely. The full suite runs in under a second.

## Modules

| Module | Responsibility |
|---|---|
| `hardware.py` | Frozen specs for Blum/Accuride/Salice slides, Blum Clip Top hinges, Richelieu/hairpin legs. `HingeSpec.hinges_for_height()` and `hinge_positions()` encode manufacturer placement rules. |
| `joinery.py` | `DrawerJoinerySpec.from_stock()` computes all cut dimensions; `DominoSpec`, `PocketScrewSpec`, `BiscuitSpec`, `DowelSpec` each provide `count_for_span()` and `positions_for_span()`. |
| `cabinet.py` | `CabinetConfig` with `drawer_config: list[(height_mm, opening_type)]`, optional `columns: list[ColumnConfig]` for multi-column carcasses, and `carcass_joinery` selection. |
| `drawer.py` | `DrawerConfig` computes box dimensions from opening + slide clearance; `joinery_style` applies corner joints; `use_standard_height` snaps to 3″–12″ stock. |
| `door.py` | Single doors and matched pairs in full/half/inset overlay; hinge cup borings via CadQuery. |
| `proportions.py` | Geometric-progression drawer heights and asymmetric column widths via named ratios. |
| `evaluation.py` | `evaluate_cabinet(cfg) -> list[Issue]`; CadQuery path adds interference checks. |
| `cutlist.py` | `consolidate_bom()`, `optimize_cutlist()` (guillotine, GuillotineBssfSas), `to_json()`, `to_csv()`; tracks grain direction. |
| `presets.py` | Pre-validated `CabinetConfig` instances; exposed as `list_presets` / `apply_preset` MCP tools. |
| `auto_fix.py` | Single-pass deterministic repair of `cumulative_heights` and `back_panel_fit` issues. |
| `describe.py` | Prose summary (metric + imperial) for the design-review step. |
| `server.py` | MCP server; `main()` entry point; `--http` flips stdio → HTTP/SSE; port auto-increments from 3749. |

## Design patterns

All configuration objects are `@dataclass(frozen=True)`. Derived values are `@property`. Mutations happen through `dataclasses.replace`. MCP tool handlers (`_tool_design_cabinet`, `_tool_evaluate_cabinet`, …) are plain async functions returning `list[types.TextContent]`.
