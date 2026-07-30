# Projects: multi-cabinet runs and the saved library

A *project* bundles one or more cabinets into a named, saved design — a bank of kitchen bases, a three-piece sideboard run, a desk with pedestals and a worktop. Projects are the durable unit of work: they persist as JSON under `~/.cabineteer/projects/`, and everything downstream (evaluation, 3D scenes, cutlists, assembly instructions) operates on them.

A single cabinet is just a one-cabinet project, so "save this design" always works the same way.

## Shared design tokens

The point of a run is consistency: same materials, same joinery, same banding on every piece. A project carries a **shared design block** of tokens that apply to every cabinet, and each cabinet may override individual tokens where it differs:

| Token | Controls |
|---|---|
| `carcass_material` / `face_material` | Sheet stock for carcasses / show faces (false fronts + doors) |
| `drawer_box_thickness` / `drawer_box_prefinished` | Drawer box stock and pre-finished switch |
| `carcass_corner_style` | `butt` or `miter` waterfall corners |
| `edge_band_mode` / `edge_band_thickness_mm` / `edge_band_material` / `edge_band_stock` | Edge banding — see [edge-banding.md](edge-banding.md) |

Change a token once and the whole run follows; a per-cabinet override wins back exactly where you asked it to.

## The library

> What have I designed recently?
> Open the miter-saw station — I want to swap the drawer slides.
> Rename triple_sideboard to dining-room-credenza. Delete the old draft.
> Fork the credenza as credenza-walnut.

- **Listing** (`list_projects`) comes back newest-first with cabinet counts, run widths, and your notes; search covers names *and* notes ("shop" finds the bench via its notes). Test clutter (names starting `eval_`/`test_`/…) stays hidden unless you ask.
- **Forking** (`duplicate_project`) copies a design and stamps its lineage — `forked_from` shows up in listings, permanently. Experiment on the copy; the original is untouched.
- **Overwrite protection:** saving over an existing name must be asked for explicitly (`overwrite=true`). A finished design can't be clobbered by accident, and deletion is its own deliberate tool call.

## Editing without re-describing

Small changes shouldn't require restating a whole design. `update_project` applies a **delta**:

> Make the top drawer in the left cabinet 150 mm.
> Switch the whole project to pre-finished drawer boxes.
> Add a third cabinet like the first but 600 wide. Drop the worktop.

Rules that make deltas safe:

- Patches shallow-merge; setting a key to `null` clears it.
- If you change a per-cabinet key that's currently governed by a shared token, the cabinet gets an explicit override pin — your edit sticks even though the token exists.
- Cabinets can be renamed, added, and removed in the same call.
- Convenience spellings are canonicalized (e.g. a pull preset expands to its concrete pulls; `num_drawers` replaces a previous explicit stack) so the saved file stays coherent.
- No-op patches don't touch the file or its change log.

Every applied patch is recorded in the project's change log, so a design's history reads honestly.

## Worktops

Desks and benches usually carry a slab across part of the run. A project-level `worktop` models it:

- Span, depth, thickness, and which cabinets it crosses
- `surface_height_mm` is measured **from the floor** — feet included — because that's the number that matters ergonomically
- `leg_count`: 4 (corners), 2 (front edge only — the cabinets carry the back), or 0 (fully cabinet-borne)

The worktop renders in the 3D scene (legs stay metal under any wood finish) and lands in the project cutlist as one finished-stock slab panel.

## Checking a run as a whole

`evaluate_project` runs the full per-cabinet evaluation and adds cross-cabinet consistency checks — mismatched heights or depths in a run, inconsistent hardware, token conflicts — the things that look fine on each cabinet in isolation and wrong when they're standing next to each other.

## From project to paperwork

- `visualize_project` — every cabinet in one 3D scene at its true run offset, worktop included ([viewer.md](viewer.md))
- `generate_project_cutlist` — one cutlist for the project, or several projects batched into a single purchase ([cutlists.md](cutlists.md))
- `generate_assembly_instructions` — printable carcass assembly docs with part IDs matching the cutlist ([assembly.md](assembly.md))
