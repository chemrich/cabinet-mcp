# Cutlists and sheet layouts

Ask for a cutlist and you get back everything needed to buy material and break down sheets: a consolidated parts list, per-sheet layout drawings with numbered cuts, a priced hardware BOM, and files written to `~/.cabineteer/cutlists/` in four formats (HTML, PDF, CSV, JSON).

Two tools do this work:

- `generate_cutlist` — one cabinet.
- `generate_project_cutlist` — a saved project, or **several projects batched into one purchase** (see [Batching projects](#batching-projects-into-one-purchase)).

## What's in the parts list

Every panel the design implies, not just the obvious ones:

- Carcass sides, top, bottom, fixed shelves, dividers (dividers are cut to interior height automatically when the carcass joinery is a butt-style method — floating tenon, pocket screw, biscuit, dowel — and kept full-height for dado/rabbet)
- Backs (6 mm by default)
- Drawer-box sides, fronts, backs, and dado-captured bottoms
- Applied false fronts and door leaves, in your show material
- Worktop / desk slabs from project designs

Panels are consolidated by name + dimensions ("side — 2 off"), and every row carries a **part ID** like `DB1` or `A-DB1` (the letter prefix appears in multi-project batches). The same ID appears in the parts table, the CSV, the sheet drawings, and the assembly instructions, so a panel can be traced from purchase to glue-up.

Dimensions print in **bold metric plus fractional inches to 1/32″** in every table. The sheet drawings stay metric.

## Materials and how they group

Sheet materials pack onto sheets per (material, thickness) group:

| Config field | Default | Controls |
|---|---|---|
| `carcass_material` | `baltic_birch` | Sides, top, bottom, shelves, dividers |
| `face_material` | `finished_wood` | Applied false fronts **and** door leaves |
| `drawer_box_thickness` | 15 mm | Drawer box side/front/back stock (12 mm is a common shop choice) |
| `drawer_box_prefinished` | off | Switches boxes + bottoms to pre-finished Baltic birch |

Two rules worth knowing:

- Any material name ending in `_ply` (e.g. `rift_white_oak_ply`), and the Baltic-birch stocks, are treated as sheet goods and get nested onto sheets. Other names — solid stock, `finished_wood` — become a labeled **order-out group** with no sheet layout, because you're buying or milling those separately.
- Pre-finished and raw Baltic birch **never share a sheet**, but same-stock panels from different parts of the build (drawer boxes, backs, bottoms) pool together to fill sheets efficiently.

If a sheet material has no price entry, the group is flagged `price_missing` rather than silently priced at zero.

## Sheet sizes

Default sheets are 2440 × 1220 mm (a nominal 8 × 4 ft Baltic-birch sheet). Real sheets vary by supplier — domestic oak ply often runs oversize. Override per material:

```json
"sheet_size_overrides": {"rift_white_oak_ply": [2453, 1234]}
```

Only the named material's sheets resize; everything else stays nominal. Kerf is configurable too (default 3.2 mm).

## The four layout algorithms

| Algorithm | What it is | When to use it |
|---|---|---|
| `opcut` | Guillotine forward-greedy nesting (default) | Best general-purpose packing; heterogeneous panel mixes |
| `rectpack` | Guillotine best-short-side-fit | Alternative packing; occasionally wins on uniform panels |
| `strip` | Pure-Python strip cutting | Automatic fallback in lite installs — no extra dependencies |
| `rips_first` | **Shop-sequence mode** — see below | When you break down sheets with a track saw first |

**`rips_first` mirrors how many small shops actually work:** full sheets are ripped into long strips with a track saw, strips are cross-cut into segments, and any segment needing a narrower width goes to the table saw for a secondary rip. The optimizer respects that sequence:

- Secondary rips are capped by your **fence capacity** (default 508 mm / 20″).
- No strip is ripped thinner than 150 mm on the track saw — narrow parts are bundled into a wider strip and split to final width on the table saw, where thin rips are safe and accurate.
- The drawing shows the *actual* cut plan: strip rips appear as the numbered breakdown cuts, in the order you'd make them.

It's opt-in (never chosen automatically), and you can mix algorithms per material group:

```json
"optimizer": "rips_first",
"optimizer_overrides": {"@6": "opcut"}
```

Override keys are `material@thickness`, `material`, or `@thickness` (most specific wins). The example above keeps 6 mm backs — usually a heterogeneous group that nests tighter with a true packer — on opcut while everything else follows the shop sequence. Each material group reports which algorithm laid it out.

## The standalone parts list

Alongside the layout files, every cutlist run writes `<name>_parts.pdf` — a portrait cut-parts document designed to be taped to the saw: per part, a **bold metric row** with scannable L/W/T columns, a grey imperial sub-row beneath, and a spanning note row for banding markers and remarks. Multi-project batches also write one per project (`<project>_parts.pdf`, part IDs keeping their batch letters) and use "Project B — kid1-desk" section rows in the combined doc instead of a Project column. The parts table inside the layout PDF uses the same format.

## The layout drawings

`generate_cutlist` writes a self-contained HTML file (per-sheet SVG drawings, tabs per thickness) and a landscape PDF (sheet drawings + parts list + guillotine cut-sequence tables; US Letter by default, `paper: "a4"` for A4). Both show:

- Numbered breakdown cuts with dimensions, in cutting order
- Rotated part labels with part IDs, fitted to their panels
- Grain direction respected for show parts

## The hardware BOM

Every cutlist ends with a shopping list: slides (sold as pairs), hinges **plus their mounting plates and screws as separate lines** (that's how Blum sells them), pulls with pack-quantity math, legs, and joinery consumables (Domino tenons by size and count, pocket screws, etc.). Each line carries a unit list price and a line total; the summary block totals sheet goods and hardware separately.

Prices are **list/MSRP snapshots**, not live market prices — treat the totals as estimates and check your supplier. See [hardware.md](hardware.md#pricing) for how to update the price list.

If the design uses edge banding, the BOM also includes either hot-melt rolls or a hardwood-boards-to-order line, and hardwood banding gets its own dedicated cutting document — see [edge-banding.md](edge-banding.md).

## Batching projects into one purchase

> One combined cutlist for the miter station and the kids desk.

`generate_project_cutlist` accepts multiple saved project names. Panels from all projects pack onto **shared sheets** for minimum total waste, but nothing loses its identity:

- Each project gets a color (a color-blind-safe palette) on every sheet drawing, with a legend
- Part IDs gain a project letter (`A-DB1`, `B-S2`) by order of appearance
- The parts table and CSV carry a Project column
- Hardware lines show the per-project split, e.g. legs: `miter_station ×12, kids-desk ×8`
- Sheets are numbered globally `#1…#N` across the whole batch

One purchase per SKU, zero mystery about whose parts are whose.

> **Note:** in the JSON result, the top-level `sheets_used` counts carcass material groups only (a legacy field). The per-group `sheet_goods` rows are the source of truth for total sheet counts — the HTML/PDF summaries already read from those.
