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

`DrawerJoinerySpec.from_stock(style, side_thickness, front_back_thickness)` returns all cut dimensions, and `compare_joinery` (MCP) prints them side by side for a given stock so you can pick a joint at the bench, not in the abstract.

## Carcass joinery

| Method | Key | Notes |
|--------|-----|-------|
| Dado & rabbet | `DADO_RABBET` | Default; pre-modelled in `cabinet.py` |
| Floating tenon | `FLOATING_TENON` | Festool Domino — see sizes below |
| Pocket screw | `POCKET_SCREW` | Kreg-style angled pocket |
| Biscuit | `BISCUIT` | #0 / #10 / #20; primarily for alignment |
| Dowel | `DOWEL` | 8 mm / 10 mm; compatible with 32 mm grid |

`DominoSpec`, `PocketScrewSpec`, `BiscuitSpec`, and `DowelSpec` each provide `count_for_span()` and `positions_for_span()` for automatic fastener layout across a panel edge. The same counts and positions feed the hardware BOM (consumables) and the [assembly instructions](assembly.md) (per-panel mortise maps) — one census, no drift between documents.

**Carcass Domino sizing is automatic:** 5 × 30 tenons for stock up to 19 mm, 8 × 40 above. With butt-style carcass joinery (floating tenon, pocket screw, biscuit, dowel), column dividers are cut to interior height; dado/rabbet keeps full-height dividers.

## Mitered waterfall corners

Set `carcass_corner_style="miter"` (per cabinet or as a project token) to put 45° waterfall miters on the four exterior corners — continuous grain wrapping from side to top, no visible plywood edge:

- Top and bottom are cut to full exterior width **long-point**, with bevel notes on their cutlist rows; sides keep their nominal dimensions with beveled-end notes.
- Divider and fixed-shelf joints stay butt tenons — only the show corners miter.
- For floating-tenon carcasses, `miter_mortise_placement()` solves where the Domino can sit inside the 45° face: the plunge eats toward the outside (show) face at cos 45°, so the placement biases toward the heel and enforces a ≥ 2 mm wall to the show face. A 5 × 30 at 15 mm needs ≥ 16.5 mm stock — the evaluator (`check_miter_corners`) errors when the stock is too thin, the mating thicknesses differ, or the joinery method can't do miters at all.
- The [assembly instructions](assembly.md) switch accordingly: fence-at-45° machine settings, a dial-in-on-scrap step, and tape-hinge + band-clamp glue-up.

Honest field report: miters look spectacular and cost real effort — a small box is a good first test before committing a large run to them. Butt corners with [hardwood edge banding](edge-banding.md) are the pragmatic alternative.

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
