# Hardware catalogue

Drawer slide, door hinge, furniture leg, and pull specifications are frozen dataclasses in `hardware.py`. Every spec knows its clearance requirements and can validate a proposed drawer or door. Part numbers are real, orderable SKUs — the hinge SKUs in particular were verified against Blum's current numbering at order time.

Pulls and knobs — 45 catalog entries across Top Knobs, Rockler, Richelieu, Häfele, and IKEA — live on a dedicated page: [docs/pulls.md](pulls.md).

See [ATTRIBUTIONS.md](../ATTRIBUTIONS.md) for the datasheet and distributor sources behind each entry.

## Drawer slides

| Key | Model | Type | Load | Extension | Lengths (mm) |
|-----|-------|------|------|-----------|--------------|
| `blum_tandem_550h` | Blum Tandem 550H | Undermount | 30 kg | ¾ | 270–600 |
| `blum_tandem_plus_563h` | Blum Tandem Plus 563H | Undermount | 41 kg | Full | 229–533 |
| `blum_tandem_plus_563f` | Blum Tandem Plus 563F | Undermount | 41 kg | Full | 229–533 |
| `blum_movento_760h` | Blum Movento 760H | Undermount | 40 kg | Full | 250–600 |
| `blum_movento_769` | Blum Movento 769 | Undermount | 70 kg | Full | 457–762 |
| `accuride_3832` | Accuride 3832 | Side-mount | 45 kg | Full | 250–700 |
| `salice_futura` | Salice Futura | Undermount | 34 kg | Full | 305–533 |
| `salice_futura_smove` | Salice Futura Smove (soft-close) | Undermount | 34 kg | Full | 305–533 |
| `salice_progressa_plus` | Salice Progressa+ | Undermount | 54 kg | Full | 229–762 |
| `salice_progressa_plus_smove` | Salice Progressa+ Smove (soft-close) | Undermount | 54 kg | Full | 229–762 |

A trap worth knowing when ordering Blum: the **H/F suffix is drawer-side thickness, not extension** — 563**H** takes 1/2″ sides, 563**F** takes 3/4″ sides; both are full extension. (The 550H is the ¾-extension budget line.)

Every slide spec carries min/max side clearance, top/bottom clearance, bracket insets, minimum drawer height, and maximum drawer width — `evaluate_cabinet` checks a drawer against all of them and reports measured values, and the box dimensions in `design_drawer` come from these clearances.

## Door hinges — Blum Clip Top

How to read a Blum Clip Top SKU: **71T** = plain, **71B** = BLUMOTION (integrated soft-close); the next two digits are the overlay — **35**xx full, **36**xx half, **37**xx inset; the last two digits are the cup mounting — **..90** = INSERTA (tool-free expanding cup, no screws) and **..50** = screw-on (needs 2 × 606N cup screws, which the BOM adds as a fastener line).

| Key | Overlay | Soft-close | Angle | Part # | Cup |
|-----|---------|-----------|-------|--------|-----|
| `blum_clip_top_110_full` | Full | No | 110° | 71T3590 | INSERTA |
| `blum_clip_top_blumotion_110_full` | Full | Yes | 110° | 71B3590 | INSERTA |
| `blum_clip_top_110_half` | Half | No | 110° | 71T3690 | INSERTA |
| `blum_clip_top_blumotion_110_half` | Half | Yes | 110° | 71B3690 | INSERTA |
| `blum_clip_top_110_inset` | Inset | No | 110° | 71T3790 | INSERTA |
| `blum_clip_top_blumotion_110_inset` | Inset | Yes | 110° | 71B3790 | INSERTA |
| `blum_clip_top_170_full` | Full | No | 170° | 71T6550 | Screw-on |

(`blum_clip_top_110` and `blum_clip_top_170` are aliases for the full-overlay entries.)

**Hinges are only half the order.** Every Clip Top needs a mounting plate — a separate SKU. Each catalog entry carries `mounting_plate_part="173L8100"` (CLIP 0 mm wing plate, with pre-mounted 5 mm Euro system screws — pilot 5 mm holes at 37 mm from the cabinet front edge), and the BOM emits one plate line per hinge automatically. All presets with doors default to BLUMOTION.

All Clip Top hinges use a 35 mm cup (13 mm deep, 22.5 mm from the door edge). `HingeSpec.hinges_for_height()` and `hinge_positions()` implement Blum's published hinge-count and placement rules (cups 100 mm from top/bottom; 2 hinges up to 900 mm of door height, 3 to 1600, 4 to 2000, 5 above — plus weight-based bumps).

## Furniture legs

| Key | Model | Height | Adjustable | Load | Finish |
|-----|-------|--------|-----------|------|--------|
| `richelieu_176138106` | Richelieu Contemporary Square Leg | 100 mm (3-15/16″) | No | 50 kg | Brushed nickel |
| `richelieu_17613b106` | Richelieu Contemporary Square Leg | 100 mm | No | 50 kg | Matte black |
| `richelieu_adjustable_40mm` | Richelieu Adjustable Leg | 40–65 mm | Yes (M8) | 60 kg | Aluminum |
| `hairpin_152mm` | Hairpin Leg 152 mm (6″) | 152.4 mm | No | 30 kg | Matte black |
| `hairpin_200mm` | Hairpin Leg 200 mm | 200 mm | No | 30 kg | Matte black |

`get_leg(key)` returns the `LegSpec`. The `design_legs` MCP tool returns placement coordinates, load-per-leg, and hardware BOM lines. Note the generic hairpin ratings: 30 kg per leg is fine for a console, marginal for a loaded sideboard — the load check will tell you, and heavier 1/2″-rod hairpins or a fifth centre leg are the usual fixes.

## Joinery consumables

The BOM also knows the consumables that carcass joinery implies: Festool Domino tenons (5 × 30 pack of 300 = part 494938; 8 × 40 = 493298), pocket screws, dowels, and biscuits, each counted from the actual joint census. The carcass tenon size rule: 5 × 30 for stock ≤ 19 mm, 8 × 40 above.

## Pricing

`hardware.py` exports a `PRICE_LIST` dict (116 entries) and a `price_for(key)` helper used by the cutlist tools to add cost estimates to the BOM output.

```python
from cabineteer.hardware import price_for, PRICE_LIST

price_for("blum_tandem_550h")   # → 28.5  (per pair)
price_for("topknobs-hb-96")     # → 10.0  (each)
price_for("unknown-key")        # → 0.0   (never raises)
```

All prices are list/MSRP in USD — not market prices. `generate_cutlist` labels the output accordingly and returns a `cost_estimate` block:

```json
"cost_estimate": {
  "sheet_goods_usd": 318.00,
  "hardware_by_category_usd": {
    "slide": 342.00,
    "hinge": 38.00,
    "hinge_accessory": 10.92,
    "leg": 72.00,
    "joinery": 17.00,
    "fastener": 8.00
  },
  "hardware_total_usd": 487.92,
  "grand_total_usd": 805.92,
  "note": "List/MSRP prices — actual cost varies by supplier and region."
}
```

Each `hardware_bom` entry also gets `unit_price_usd` and `line_total_usd` fields, and each `sheet_goods` entry gets `price_per_sheet_usd` and `line_total_usd`.

### Updating prices

Edit the `PRICE_LIST` dict at the bottom of `hardware.py`. Keys must match the hardware catalog key (for slides/hinges/legs/pulls) or the SKU string used in `cutlist.py` (for joinery consumables, fasteners, and edge-band rolls like `edgeband-hotmelt-white_oak`).

Sheet goods use keys of the form `sheet_<material>_<thickness>mm` — the list ships with Baltic birch (raw and pre-finished) in 6/9/12/15/18 mm plus `sheet_rift_white_oak_ply_18mm`. A sheet material with no matching key is flagged `price_missing` in the cutlist rather than silently costed at zero; hardware keys missing from the list return `0.0` and show as `$0.00` lines.
