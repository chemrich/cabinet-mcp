# Pulls and knobs

Cabinet pulls, drawer pulls, and knobs are first-class hardware in the catalogue — they have their own `PullSpec` dataclass, placement policy, evaluation checks, and procurement math (pack quantities, leftovers).

See [ATTRIBUTIONS.md](../ATTRIBUTIONS.md) for per-brand datasheet and product-page sources.

## Catalogue

All entries live in `cadquery_furniture/data/pulls_catalog.json` and are loaded into `hardware.PULLS` at import time. Every pull records center-to-center spacing (`cc_mm`), overall length, projection, pack quantity, finish, style, and a stable SKU key.

| Brand | Entries | Representative keys | Notes |
|---|---|---|---|
| Top Knobs | 20 | `topknobs-hb-*`, `topknobs-ag-*`, `topknobs-blk-*` | Kinney bar pull series — Honey Bronze / Antique Gold / Black, cc 76–305 mm |
| Rockler | 7 | `rockler-wnl-*`, `rockler-okl-*`, `rockler-42250` | Ashley Norton wood pulls (walnut / oak), Mission-style white-oak pull |
| Richelieu | 12 | `richelieu-chbrz-*`, `richelieu-*` | Modern aluminum edge pulls and contemporary surface pulls |
| Hafele | 2 | `hafele-193.18.766`, `hafele-151.35.665` | Modern-wood surface pull + minimalist flush pull |
| IKEA | 4 | `ikea-bagganas-*`, `ikea-hackas-*`, `ikea-borghamn-*`, `ikea-billsbro-*` | Sold in 2-packs — pack-quantity math applies |

Use `list_hardware(category="pulls")` at runtime to discover keys. The same tool accepts `brand=` (case-insensitive substring) and `mount_style=` (`surface` / `edge` / `flush` / `knob`) filters.

## Placement policy

Placements are emitted in **face-local coordinates**: the origin `(0, 0)` is the bottom-left corner of the visible face; `+x` points right along the face width, `+z` points up along the face height. The cabinet assembly (or the MCP caller) is responsible for transforming into global coordinates.

### Dual-pull threshold

```
face_width ≤ 600 mm   → 1 pull, centred on x
face_width >  600 mm  → 2 pulls at the ⅓ and ⅔ points
```

`DUAL_PULL_THRESHOLD_MM = 600` comes from the conventional cabinet-shop rule that drawers wider than roughly 24″ feel unbalanced opening on a single pull. Knobs and flush pulls are always single — splitting a knob is never the right answer. Callers can override via `pull_count=N`.

### Vertical placement

Set on the drawer or door config via `pull_vertical`:

| Policy | z-coordinate | When to use |
|---|---|---|
| `center` | `face_height / 2` | Default; kitchen base drawers, most doors |
| `upper_third` | `2/3 · face_height` | Tall dresser drawers — pulls within arm's reach |
| `lower_third` | `1/3 · face_height` | Overhead / wall cabinets — pulls accessible without reaching |

### End margin

`END_MARGIN_MM = 40` is the minimum clearance between the pull's outer body edge and the nearest face edge. A face that violates `face_width ≥ length_mm + 2 · END_MARGIN_MM` is flagged by `pull_fits_face()` and surfaces as a `pull_fit` evaluation issue.

## Integration with configs

`DrawerConfig`, `DoorConfig`, and `CabinetConfig` all accept pull fields:

```python
DrawerConfig(opening_width=900, opening_height=180, opening_depth=500,
             pull_key="topknobs-hb-128", pull_vertical="center")

DoorConfig(opening_width=400, opening_height=700, num_doors=2,
           pull_key="rockler-wnl-160", pull_vertical="upper_third")

CabinetConfig(width=900, height=720, depth=550,
              drawer_pull="topknobs-hb-128", door_pull="topknobs-hb-128",
              drawer_config=[...])
```

On drawers, `pull_placements` returns an empty list if `applied_face=False` — there's no visible face on which to mount hardware, and the evaluator warns if `pull_key` is set anyway. On doors, `total_pull_count` accounts for `num_doors` (a `door_pair` slot gets two leaves, each with its own pull).

When the cabinet-level `drawer_pull` / `door_pull` are set, `pull_lines_for_cabinet_config()` walks the entire stack (or multi-column layout) and produces one consolidated `HardwareLine` per SKU.

## Procurement math

`HardwareLine` carries derived procurement fields so downstream consumers don't replicate the math:

| Field | Meaning |
|---|---|
| `pieces_needed` | Total count the design actually consumes |
| `pack_quantity` | Pieces per pack from the catalog (1 for most, 2 for IKEA) |
| `packs_to_order` | `ceil(pieces_needed / pack_quantity)` |
| `pieces_ordered` | `packs_to_order · pack_quantity` |
| `leftover` | `pieces_ordered − pieces_needed` |

Example: five drawers each needing one IKEA Bagganäs (pack of 2) → 5 pieces needed → 3 packs → 6 ordered → 1 leftover.

`consolidate_hardware_lines()` merges lines sharing a SKU, preserves first-seen order, and concatenates notes for traceability. Export helpers `to_hardware_csv()`, `to_hardware_json()`, and `print_hardware_bom()` handle CSV, JSON (with totals), and console output.

## Evaluation checks

Run via `evaluate_cabinet(cfg)` as part of the normal workflow. Pull-specific checks:

| Check | Severity | Trigger |
|---|---|---|
| `pull_unknown` | error | `pull_key` not in `hardware.PULLS` |
| `pull_no_face` | warning | `pull_key` set but `applied_face=False` |
| `pull_fit` | error | Face too narrow for the chosen pull + end margin |
| `pull_projection` | warning | Knob/pull projection exceeds drawer-side clearance |
| `pull_knob_wide_face` | warning | A knob placed on a face wider than 600 mm |
| `pull_style_mismatch` | warning | Cabinet mixes `drawer_pull` + `door_pull` with different `PullSpec.style` values |

Finishes aren't enforced to match — mixing e.g. Flat Black pulls with Polished Brass accent knobs is a deliberate design choice.

## MCP tools

| Tool | What it does |
|---|---|
| `list_hardware(category="pulls")` | Catalogue, plus `brand=` and `mount_style=` filters |
| `design_drawer(..., pull_key=..., pull_vertical=...)` | Adds a `pull` block with placements, face dims, fit issues, and one-line BOM |
| `design_door(..., pull_key=..., pull_vertical=...)` | Same, with per-leaf placements and `total_pulls` across pairs |
| `design_pulls(...)` | Whole-cabinet pass: per-slot placements, cabinet-level style check, consolidated hardware BOM with pack-quantity totals |

Typical workflow: call `design_cabinet` / `design_multi_column_cabinet`, confirm `evaluate_cabinet` is clean, then call `design_pulls` with `drawer_pull` / `door_pull` selected from `list_hardware` to get placements and procurement in one shot.
