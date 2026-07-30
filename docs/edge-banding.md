# Edge banding

Plywood carcasses show raw edges at the front of every panel. cabineteer models the two common ways to cover them — iron-on hot-melt banding and shop-made solid-hardwood banding — deeply enough that the cutlist, the evaluator, and the assembly instructions all stay consistent with what you'll actually do at the bench.

## Choosing a mode

Set on the cabinet (or as a project-wide design token — see [projects.md](projects.md)):

| Field | Values | Default |
|---|---|---|
| `edge_band_mode` | `none` / `hot_melt` / `hardwood` | `none` |
| `edge_band_thickness_mm` | band thickness (hardwood: 1/8″ = 3.2 or 1/4″ = 6.4) | — |
| `edge_band_material` | e.g. `white_oak`, `white_birch` | — |

**What gets banded:** the front edge of every carcass panel (sides, top, bottom, shelves, dividers), and **all four edges** of drawer faces and door leaves. The cutlist rows carry explicit edge-band markers, so the paperwork always states which edges of which parts are in the banded set.

### Hot-melt (iron-on)

Pre-glued veneer tape, applied **after** the panels are cut, so panel dimensions in the cutlist are unchanged — but the finished part grows by the band thickness on each banded edge. cabineteer accounts for that growth honestly:

- The evaluator checks that growth on stacked drawer faces doesn't close the 4 mm face gap (`check_edge_band_face_gap`), and includes it in door-overlay collision checks.
- The BOM prices real product: 7/8″ × 50′ pre-glued rolls (white oak, white birch), one line per material.
- The assembly instructions add an ironing step after glue-up and cure.

### Hardwood (shop-ripped solid banding)

Solid strips glued to the panel edges — the furniture-grade option. Here the geometry works the other way: cabineteer **shrinks the panel cores** by the band thickness on each banded edge, so the *finished* dimensions and reveals come out exactly as designed. Cutlist rows note both core and finished sizes.

A practical note from real use: **1/8″ banding is much easier to live with than 1/4″.** A wide band next to plywood face veneer reads as a failed color match (they're different boards, and it shows); and band stiffness grows with the cube of thickness — 1/8″ strips pull flat with tape, 1/4″ needs cauls and clamps. The evaluator accepts both but validates the whole stock spec either way.

Also counter-intuitive but true: long thin bands rip most efficiently from the **edge of thick stock** (a 5/4 board on edge yields many 1/8″ strips), not from thin boards.

## Hardwood band stock and the banding cutlist

If you tell cabineteer what board you're buying, it plans the banding like any other material. Set the `edge_band_stock` token:

```json
"edge_band_stock": {"width_mm": 139.7, "length_mm": 1219.2, "price_usd": 52.0, "strip_width_mm": 20}
```

(That's a 1/8″ × 5.5″ × 48″ board ripped into 20 mm strips; the board's *thickness* is your `edge_band_thickness_mm`.)

With a stock spec in place you get:

- **A priced boards-to-order line** in the hardware BOM — real per-edge piece lengths (with a 10 mm proud allowance for flush-trimming) packed into strips and strips into boards, so the count is what you'd actually buy, with spares visible.
- **A dedicated banding cutting document** (`<name>_banding_cutlist.html/.csv/.pdf`) that leads with what matters at the saw: the rip width, the kerf assumption, and a **length schedule** — how many pieces you need at each length — followed by corner-treatment notes, with the full board → strip → piece chop plan as an appendix. Boards are numbered `#1…#N`; piece labels use the same part IDs as the sheet layouts.
- Pieces that land at exactly full strip length are flagged (no overhang left to flush-trim — plan accordingly), and any piece *longer* than your stock is listed separately so you find out before ordering, not after.

In multi-project batch cutlists, banding aggregates to one boards-to-order line per material across the whole batch.

## Corner treatments

The banding document spells out how bands meet at corners, because the strip list alone doesn't tell you:

- **Butt-joined carcasses:** the side panels' front bands run through top to bottom; top/bottom bands butt into them.
- **Mitered carcasses:** front bands meet in a 45° seam, trimmed flush to the beveled panel ends.
- **Face and door perimeters:** band the SHORT edges first, then the LONG edges overlap their end grain — the long, visible edges show a clean continuous band.

## What the evaluator checks

- Mode/thickness/material are coherent; banding on order-out faces is flagged.
- Hardwood stock spec is feasible: 1/8″ or 1/4″ thickness, 3–5.5″ board width, strip width covers the thickest banded edge, and your longest banded edge fits the strip length.
- Hot-melt growth doesn't collide door edges with neighbouring faces or close the face gap (hardwood is core-compensated, so it's dimension-neutral everywhere).

## Order of operations at the bench

The [assembly instructions](assembly.md) sequence banding correctly for each mode:

- **Hardwood: band BEFORE mortising.** The banded front edge becomes the reference edge for Domino mortise layout — band first or every mortise measurement shifts by the band thickness.
- **Hot-melt: iron AFTER glue-up and cure.**
