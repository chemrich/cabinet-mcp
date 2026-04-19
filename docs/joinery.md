# Joinery

Drawer corner joints and cabinet carcass joinery are selected via enums on the respective config objects. All cut dimensions are computed from stock thickness — there is no hand-tuning per joint.

## Drawer corners

| Style | Key | Description | Router bit? |
|-------|-----|-------------|-------------|
| Butt | `BUTT` | Plain butt, glue + fastener | No |
| QQQ | `QQQ` | Quarter-Quarter-Quarter locking rabbet (Phipps) | No |
| Half-lap | `HALF_LAP` | Overlapping half-depth rabbet at each corner | No |
| Drawer lock | `DRAWER_LOCK` | Stepped L-tongue/socket via router bit | Yes |

The **QQQ system** (Stephen Phipps, *This Is Carpentry*, 2014) sets dado blade width, cut depth, and fence distance all equal to half the stock thickness. The resulting locking rabbet is stronger than a dovetail in shear and requires no jig — but it does require true-thickness stock.

`DrawerJoinerySpec.from_stock(style, side_thickness, front_back_thickness)` returns all cut dimensions.

## Carcass joinery

| Method | Key | Notes |
|--------|-----|-------|
| Dado & rabbet | `DADO_RABBET` | Default; pre-modelled in `cabinet.py` |
| Floating tenon | `FLOATING_TENON` | Festool Domino — see sizes below |
| Pocket screw | `POCKET_SCREW` | Kreg-style angled pocket |
| Biscuit | `BISCUIT` | #0 / #10 / #20; primarily for alignment |
| Dowel | `DOWEL` | 8 mm / 10 mm; compatible with 32 mm grid |

`DominoSpec`, `PocketScrewSpec`, `BiscuitSpec`, and `DowelSpec` each provide `count_for_span()` and `positions_for_span()` for automatic fastener layout across a panel edge.

## Festool Domino sizes

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
