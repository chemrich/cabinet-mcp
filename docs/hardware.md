# Hardware catalogue

Drawer slide, door hinge, furniture leg, and pull specifications are frozen dataclasses in `hardware.py`. Every spec knows its clearance requirements and can validate a proposed drawer or door.

Pulls and knobs — 45 catalog entries across Top Knobs, Rockler, Richelieu, Hafele, and IKEA — live on a dedicated page: [docs/pulls.md](pulls.md).

See [ATTRIBUTIONS.md](../ATTRIBUTIONS.md) for the datasheet and distributor sources behind each entry.

## Drawer slides

| Key | Model | Type | Load | Extension |
|-----|-------|------|------|-----------|
| `blum_tandem_550h` | Blum Tandem 550H | Undermount | 30 kg | Partial |
| `blum_tandem_plus_563h` | Blum Tandem Plus 563H | Undermount | 45 kg | Full |
| `blum_movento_760h` | Blum Movento 760H | Undermount | 40 kg | Full |
| `blum_movento_769` | Blum Movento 769 | Undermount | 77 kg | Full |
| `accuride_3832` | Accuride 3832 | Side-mount | 45 kg | Full |
| `salice_futura` | Salice Futura | Undermount | 45 kg | Full |
| `salice_progressa_plus` | Salice Progressa+ | Undermount | 54 kg | Full |

## Door hinges — Blum Clip Top

| Key | Overlay | Soft-close | Part # |
|-----|---------|-----------|--------|
| `blum_clip_top_110_full` | Full (16 mm) | No | 71B3550 |
| `blum_clip_top_blumotion_110_full` | Full (16 mm) | Yes | 71B3590 |
| `blum_clip_top_110_half` | Half (9.5 mm) | No | 71H3550 |
| `blum_clip_top_blumotion_110_half` | Half (9.5 mm) | Yes | 71H3590 |
| `blum_clip_top_110_inset` | Inset (0 mm) | No | 71N3550 |
| `blum_clip_top_blumotion_110_inset` | Inset (0 mm) | Yes | 71N3590 |
| `blum_clip_top_170_full` | Full (16 mm) | No | 71B3750 |

All Clip Top hinges use a 35 mm cup (13 mm deep, 22.5 mm from door edge). `HingeSpec.hinges_for_height()` and `hinge_positions()` implement Blum's published hinge-count and placement rules (100 mm from top/bottom; spacing thresholds at 1 200 mm and 1 800 mm).

## Furniture legs

| Key | Model | Height | Adjustable | Load | Finish |
|-----|-------|--------|-----------|------|--------|
| `richelieu_176138106` | Richelieu Contemporary Square Leg | 100 mm (3-15/16″) | No | 50 kg | Brushed nickel |
| `richelieu_17613b106` | Richelieu Contemporary Square Leg | 100 mm | No | 50 kg | Matte black |
| `richelieu_adjustable_40mm` | Richelieu Adjustable Leg | 40–65 mm | Yes (M8) | 60 kg | Aluminum |
| `hairpin_200mm` | Hairpin Leg 200 mm | 200 mm | No | 30 kg | Matte black |

`get_leg(key)` returns the `LegSpec`. The `design_legs` MCP tool returns placement coordinates, load-per-leg, and hardware BOM lines.

## Pricing

`hardware.py` exports a `PRICE_LIST` dict and a `price_for(key)` helper used by `generate_cutlist` to add cost estimates to the BOM output.

```python
from cadquery_furniture.hardware import price_for, PRICE_LIST

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
    "leg": 72.00,
    "joinery": 17.00,
    "fastener": 8.00
  },
  "hardware_total_usd": 477.00,
  "grand_total_usd": 795.00,
  "note": "List/MSRP prices — actual cost varies by supplier and region."
}
```

Each `hardware_bom` entry also gets `unit_price_usd` and `line_total_usd` fields, and each `sheet_goods` entry gets `price_per_sheet_usd` and `line_total_usd`.

### Updating prices

Edit the `PRICE_LIST` dict at the bottom of `hardware.py`. Keys must match the hardware catalog key (for slides/hinges/legs/pulls) or the SKU string used in `cutlist.py` (for joinery consumables and fasteners). Sheet goods use the keys `sheet_baltic_birch_18mm`, `sheet_baltic_birch_15mm`, and `sheet_baltic_birch_6mm`. Missing keys silently return `0.0` — no test failures, but the line will show `$0.00` in the estimate.
