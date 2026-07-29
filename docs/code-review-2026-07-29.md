# Code review — 2026-07-29

Deep review of everything merged since the 2026-07-17 review (range `b4064fe..HEAD`,
PRs #30–#56: edge banding + band stock accounting, mitered corners, assembly
instructions v1/v2, rips_first optimizer, part IDs, sheet-size/optimizer
overrides, project fork/update, worktop, manga scale reference, hinge-system
BOM, banding cutlist docs).

Method: 8 parallel module-scoped review agents (cutlist / server / assembly /
project+presets / evaluation+joinery+hardware / cabinet+drawer+door / visualize
/ tests+evals infra), every finding substantiated with an executed repro; the
critical and five of the majors additionally re-reproduced independently by the
orchestrator. Baseline at review time: **1475 passed / 6 skipped**, evals
**305/305 scenarios, 1139/1139 assertions** (all green — none of the findings
below are covered by existing tests; two are baked *into* tests).

Severity: **critical** = shop-damaging output · **major** = wrong
numbers/labels in shipped docs or silent data loss · **minor** = edge-case,
cosmetic-with-consequences, or robustness · **nit** = polish.

---

## CRITICAL

### C1. `miter_mortise_placement` solves the mirror image — the prescribed mortise exits the show face
`joinery.py:752-753` — the solver models the perpendicular plunge as eating
toward the **inside** face and therefore walls off the inside face and biases
the entry toward the **long point**. The real geometry is the opposite: the
bevel-face inward normal has a +cos 45° component toward the **outside (show)
face** (cross-section `{x ≤ y}`, inside face y=0, outside y=t: outward normal
(1,−1)/√2 ⇒ plunge (−1,+1)/√2).

Verified: 5×30 @ t=18 returns `from_heel=21.6, from_long_point=3.8` — entry
15.27 mm from the inside face; at 15 mm plunge depth the mortise bottom centre
lands at y≈25.9 mm in 18 mm stock, i.e. blows through the show face ~4 mm
before full depth. The assembly doc relays the placement verbatim, so
following the instructions guarantees the blow-through its own warning step
describes.

The bug is baked into spec and tests: `tests/test_miter_corners.py:23` asserts
the mirrored bias (`from_heel > face_width/2`) and CLAUDE.md documents
"biases toward the long point". All three need the same flip.

**Fix:** feasible window measured from the inside face is
`[hw, t − wall_mm − hw − c·depth]` (bias toward the **heel**; the wall
protects the show face). Numerically this is exactly a swap of
`from_heel`/`from_long_point`; `min_t` is symmetric so feasibility verdicts
(and `check_miter_corners`) are already correct. Update test + CLAUDE.md +
assembly.py step wording ("centreline N mm from the long point" → heel).

*Context: current sideboards reverted to butt tenons, so no real stock was cut
from this path — but it ships, and the doc actively instructs the error.*

---

## MAJOR

### M1. Assembly plan tenon span ≠ hardware BOM span → plan and BOM disagree on tenons per joint
`assembly.py:177` uses `span = cfg.interior_depth` (= depth − back_rabbet_width,
default −9); the BOM (`cutlist.py:2365`) uses depth − back_thickness (default
−6). Same `DominoSpec(max_spacing=150)`, different span ⇒ different
`count_for_span` in recurring 3 mm depth windows near every 150 mm threshold.

Verified: depth 356 → plan cuts **3** mortises/joint (12 tenons) while the BOM
orders **16** ("4 per joint × 4 joints"); depths 354/358 agree. Violates the
module's own "census matches the BOM" contract. `test_two_column_census_matches_bom`
only asserts joint-count parity, so the suite stays green.

**Fix:** compute both from one expression (single source of truth); decide
which span is *correct* for mortise spacing (the panels are cut to
depth − back_thickness, so that is the honest span) and use it in both.

### M2. Divider mortise maps omit column-shelf face rows — and the note says "mortise the two ENDS only"
`assembly.py:329-343` — the joint census correctly emits
`col N shelf ↔ divider M` with face mortises in the divider, but the divider
map hard-codes exactly two edge rows (bottom/top end) plus a note actively
telling the builder not to cut anything else. Verified: 2-column cabinet with
`fixed_shelf_positions=(300,)` → joint exists in the schedule, no red row on
the divider map. Shelf mortises never get machined; discovered at dry fit.

**Fix:** append a face `MortiseRow` per bordering column shelf (offset re-based
to divider bottom), condition the note.

### M3. Banding cutlist doc sweeps hot-melt panels into the hardwood board plan (double-provisioned)
`server.py:3962-3965` — `_cutlist_pipeline` selects `banded = [p for p in
all_panels if p.edge_band]`, but #53's marker-stripping only clears markers
for `edge_band_mode == "none"`. In a mixed project (hardwood-with-stock cabinet
+ hot-melt cabinet) the hot-melt panels are chop-planned as hardwood pieces
with the hardwood cabinet's stock spec — the doc's board/strip counts exceed
the hardware BOM band line (which groups per token correctly), while the
hot-melt roll lines are *also* emitted. Verified by 2-cabinet project repro:
banding CSV contains the hot-melt cabinet's edges (16 pieces / 5 strips) vs
BOM "8 pieces → 3 strips".

**Fix:** filter the doc's panel set to the hardwood band group's panels
(project tool already builds `band_groups`); single-cabinet path is already
guarded.

Related (same wiring, cutlist agent's cross-module note): multi-project
batches pack the doc jointly with the first hardwood cfg but the BOM *sums*
per-project packings — board counts can diverge in the other direction too.
Fix together: doc packs exactly the panels of each band group, per group.

### M4. `generate_assembly_instructions` part-ID lookup collides across thickness/material
`server.py:5263-5267` — `_dims_key = (name, min-dim, max-dim)` while the
cutlist distinguishes rows by thickness and material; dict build is
last-wins. Verified: two same-footprint cabinets in 18 mm and 12 mm stock →
cutlist has `S1` (18 mm) and `S2` (12 mm); assembly doc labels **both**
cabinets' side maps `S2`. Builder mortises the wrong stack.

**Fix:** add `round(thickness,1)` + material to the key.

### M5. Layout graphics label placements with the wrong part ID when rows differ only by edge_band/grain
`cutlist.py:182-198` — `consolidate_bom` keys rows on
name+dims+grain+material+edge_band+source, but `_group_id_map` keys only
(source, name, min-dim, max-dim). Banded + unbanded same-dim panels (routine
since #53), differing grain, or transposed L×W collide; last ID wins for every
placement. Verified: 2×side(banded) + 2×side(unbanded) → parts table lists S1
and S2; SVG labels read S2, S2, S2, S2 — S1 never appears in the graphic.
Exactly the "output isn't self-evidencing" failure class.

**Fix:** stamp `part_id` on pieces at optimizer-expansion time (carry through
`Placement`), or extend the id-map key with edge_band + grain + exact dims.

### M6. HTML and PDF number the same sheet's breakdown cuts differently
HTML sorts cuts by `(depth, pos)` (`cutlist.py:2787`); the PDF drawing
(`:3588`) and PDF cut-sequence table (`:3374`) sort by `(depth,)` only.
Same-depth cuts in different sub-rectangles can order differently ⇒ "cut #2"
names different physical cuts in the two documents. Verified across 300 random
layouts: 3 diverging sheets. (Sort lines predate the diff; the
renderers-must-agree contract makes it in-scope.)

**Fix:** identical sort key `(depth, pos)` at all three sites (rips_first's
declared cuts are unaffected).

### M7. `update_project` config patches silently no-op for `pull_preset`, `drawer_config`, `num_drawers`, and `openings`-on-columns
`project.py:618-633` — round-tripped snapshots always carry expanded keys
(`drawer_pull: null`, `openings`, `columns`), so:
- `pull_preset` patch: change log claims success, but `build_cabinet_config`'s
  `setdefault` does nothing against present-with-None keys; the preset key then
  evaporates on re-save. **Verified independently.**
- `drawer_config` / `num_drawers` patch: alias only honored when `openings`
  absent — always present after round-trip; heights stay unchanged while the
  log claims success. The `update_project` tool description *recommends*
  passing `drawer_config`.
- `openings` patch on a `columns` cabinet: dead data, columns still governs.

**Fix:** canonicalize in `apply_project_patch`: expand `pull_preset` eagerly
(overwrite the expansion keys, auto-pin vs shared tokens, drop the alias);
`drawer_config`/`num_drawers` → replace `openings` and clear `columns`
(and vice versa).

### M8. Evaluator's band-length check ignores vertical edges — tall cabinets never warn
`evaluation.py:734-736` — "longest banded edge" considers only width-derived
lengths. A 2100 mm pantry side (banded front edge) or 2009 mm door long edge
vs a 1219 mm board draws zero design-time length issues. Verified.

**Fix:** include `height` (side front edges) and tallest door/face long edge
in `longest` — or reuse real per-edge lengths via `band_pieces_for_panels`.

### M9. Tests and evals write into the real `~/.cabinet-mcp`
- `tests/test_optimizer_overrides.py:60-77`, `tests/test_sheet_size_overrides.py:25-63`
  call `_tool_generate_cutlist` without HOME isolation → 10 real files per
  pytest run. **Verified: the strays are in the store right now.**
- `evals/harness.py` has no HOME sandbox; ~10 project-writing scenarios never
  clean up → 13 `eval_*.json` projects + `_lite_test.json`/`test_run.json` +
  eval assembly/cutlist dirs in the real store. Assertions like
  `list_projects(query=...) count == 1` are state-dependent on that shared
  store; the two lifecycle scenarios are non-idempotent after an interrupted
  run (demonstrated: pre-seeded leftovers → 0/2 passed).

**Fix:** monkeypatch `Path.home` in the two test files (pattern already in
`test_project.py`); sandbox HOME around `evals.run_all` (tempdir), which also
makes cleanup calls unnecessary. Then sweep the existing strays out of the
real store (list first, delete only obvious `eval_*`/`test_*`/`bom_*_test`
artifacts).

---

## MINOR

1. **`strip_width_mm > width_mm` → 0 boards ordered + CSV crash.**
   `cutlist.py:1777` `per_board=0`; BOM emits `pieces_needed=0` at $0 with a
   "0/board" note; `to_banding_csv:1975` → `ZeroDivisionError` aborting the
   whole cutlist tool call mid-write. `check_edge_banding` only *warns*
   (envelope) for such stock. Fix: `pack_band_pieces` raises a clear
   ValueError; consider upgrading the evaluator warning to error.
   *(Found independently by cutlist, evals-infra, and evaluation agents.)*
2. **Banding doc "offal" overstated by one kerf** (`cutlist.py:2127-2128`):
   n strips leaving an offcut consume n kerfs, not n−1. 89 mm board / 20 mm
   strips / 3.2 kerf → doc says 22.6 mm, physical is 19.4 mm.
3. **Zero-sheet groups print phantom "(#2–#1)" ranges** (HTML `:2963`, PDF
   `:3255-3257`) when every panel is unplaced. Emit "—".
4. **Banding PDF chop-plan table 176 mm wide vs 159 mm A4 frame**
   (`cutlist.py:2324`) — right column clips on hard-margin printers.
5. **`optimization_note` misreports rips_first as opcut** (`server.py:4035-4044`)
   — shows on every one of Charlie's standing runs. Derive from actual
   `algorithm_used` values.
6. **Exported cutlist JSON `stock` ignores `sheet_size_overrides`**
   (`server.py:3894-3898`) — packing uses 2453×1234, JSON declares 2440×1220.
7. **`_parse_sheet_size_overrides` accepts a string** (`server.py:3717-3719`):
   `"2453x1234"` → 2.0×4.0 mm sheet, everything unplaced, no error.
8. **Add-then-edit same cabinet in one patch loses add-time overrides**
   (`project.py:590-594` vs `:638-639`) — later edit writes an exhaustive
   `overrides` list containing only the edited key; explicit add-time
   `drawer_slide` silently reverts to the shared token.
9. **`notes: null` persisted as the string `"None"`** (`project.py:532-534`).
10. **No-op value patches log a fake change and bump mtime** (`project.py:630-633`)
    — project jumps to top of newest-first listing with no real change.
11. **`kitchen_base_door_pair_wide` missed by the BLUMOTION sweep**
    (`presets.py:212`) — still `blum_clip_top_110_half` while every sibling
    preset converted. Confirm intent or convert.
12. **1/4" tolerance off by float epsilon** (`evaluation.py:682`):
    `abs(6.35−6.4) < 0.05` is False → true-1/4" spec draws the spurious
    "sold in 1/8 or 1/4 only" warning; 1/8" passes. Widen tolerance.
13. **Face-gap check: exactly-closed gap (0 mm) is only a WARNING**
    (`evaluation.py:790-791`) — faces physically bind; make `gap_after <= 0`
    the error condition.
14. **Coverage check omits door/face edges** (`evaluation.py:702-704`):
    per-opening `door_thickness=25` with 20 mm strips escapes the
    "strip cannot cover the edge" error.
15. **Manga jitter escapes the interior-fit check** (`drawer.py:373-376` vs
    `:403-404`): jitter adds up to 4 mm x / 6 mm y beyond the checked
    footprint → verified 1.5 mm interpenetration into the side panel in a
    tight-but-passing interior. Viewer-only cosmetics; fold worst-case jitter
    into the check or clamp jitter to slack.
16. **A cabinet named `manga2` renders invisible** (`visualize.py:495-505`):
    the manga ancestor-walk regex has no structural gate, so a legitimately
    named cabinet classifies as manga volumes (level 2 → hidden at initial
    count 1). Gate on parent matching `BOX_RE`.
17. **Eval `HAS_ERROR`/`HAS_WARNING` expected-arg is dead** (`evals/harness.py:379-382`)
    — `Op.HAS_ERROR, "door_overlay_collision"` passes on *any* error. Make it
    filter by check name when expected is a string.
18. **`test_rips_first.py:61-70` over-fits a magic 124 mm tail** — excludes any
    124 mm rip anywhere; regressions below the 150 mm floor can hide. Assert
    against `RIPS_FIRST_MIN_STRIP_MM` instead.
19. **Operator-precedence bug in `tests/test_cutlist.py:134`** —
    `A and B or C` parses as `(A and B) or C`; parenthesize.
20. **CI lite-guard only checks cadquery** (`.github/workflows/ci.yml`) —
    extend to opcut/rectpack/reportlab.

## NIT

- Fence height printed `:.0f` — 15 mm stock's 7.5 shows as "8 mm"
  (`assembly.py:427/551`); use `:g`.
- Single-column shelf row labeled "(left side only)" though it joins both
  sides (`assembly.py:267-277`) — right panel's mortises skipped.
  *(Arguably minor; grouped here because single-column shelves via
  `ColumnConfig` on n=1 are rare — promote if that layout is in use.)*
- Miter-step text "divider rows on top and bottom only" wrong when fixed
  shelves exist (`assembly.py:448-450`).
- Mixed panel thickness: single `side_t/2` fence height prescribed for all
  edge mortises misaligns joints when bottom/top/shelf thickness ≠ side
  thickness (`assembly.py:256-261`) — raise/warn on non-uniform stock.
- Every shelf-family map reuses `pid("shelf_1")` → distinct shelf rows show
  the same ID (`assembly.py:356`).
- `min_t` doc drift: formula says 16.5, docstring/CLAUDE.md say ~16.6
  (`joinery.py:744`).
- Hot-melt over-thickness warning threshold 1.5 mm vs message text "≤ ~1 mm"
  (`evaluation.py:617`).
- `BAND_RIP_KERF_MM` used in a *length* margin (`evaluation.py:747`).
- `project_names` as a plain string iterates per character (`server.py:5072`).
- `generate_assembly_instructions` `format="docx"` returns success with empty
  files (`server.py:5237`).
- Layout/banding PDF `except ImportError: pass` silent in lite mode
  (`server.py:3955, 3982`) — assembly tool reports "PDF skipped"; match it.
- `design_project` overwrite guard is check-then-act (`server.py:4885`).
- rips_first lone-column trim not fence-gated and undeclared in `cuts`
  (`cutlist.py:1035-1038`) — document as track-saw trim or gate it.
- `assign_part_ids` letter wrap at 26 projects (`cutlist.py:161`).
- M-key swallows the keypress in manga-less viewers (`visualize.py:1610`).
- Presets stray 9-space indentation (`presets.py:688, 839`).
- `_await`/`_run` helpers triplicated across test files on deprecated implicit
  event-loop APIs (breaks ≥3.14); consolidate in conftest.
- `test_optimizer_overrides.py:71-77` locates groups by display-name
  substrings — brittle to label wording.

---

## Clean areas (verified, no findings)

- **Path traversal / injection:** all filesystem stems validated
  (`_safe_stem`, `_PROJECT_NAME_RE`); viewer HTML survives hostile
  `cutlist_prompt` XSS probes; HTTP binds 127.0.0.1.
- **rips_first geometry:** 200 random trials — no overlaps/out-of-bounds,
  counts conserved, kerf respected, grain never violated.
- **Banding math self-consistency:** BOM board counts match the doc for
  single-cabinet runs; CSV/HTML/PDF agree on numbering, schedules, flags.
- **Heavy-bottom boundaries** exact per spec; **band marker sets**
  byte-identical to the documented banded set; **core-shrink/miter dims** in
  cabinet.py are config-only in-range.
- **Patch worktop semantics, lineage round-trip, filename validation,
  token precedence, `_config_to_dict` coverage** — all verified.
- **Hinge/plate/screw internal consistency** (INSERTA↔0 screws, screw-on↔2,
  plates per hinge, price-list keys) — consistent; SKUs not second-guessed
  per the 2026-07-28 order correction.
- **Viewer worktop/manga classification, O/V/X-key interplay, f-string
  escaping (`node --check` on 547 KB emitted script), GLTF dedup tolerance.**
- **The 6 test skips** are legitimate (BUTT has no rabbet; QQQ covered by its
  dedicated 21-case class).
- **Assembly renderer sign conventions** (front-edge reference, SVG vs
  reportlab y-axis) agree between data, HTML, and PDF.
- **`consolidate_bom`/`consolidate_hardware_lines`** keys and price-override
  survival correct; opcut unique-ID counter intact.

## Deferred / judgment calls (need Charlie)

- **M1 span choice:** plan uses depth−9, BOM uses depth−6 — which span is the
  shop-true mortise field? (Panels are cut to depth−back_thickness; rabbet
  only relieves the back edge.) Fix will standardize on whichever you call.
- **Preset hinge (#11):** was `kitchen_base_door_pair_wide` left on the plain
  71T half-overlay deliberately?
- **rips_first lone-column trim (nit):** treat >508 mm secondary rips as
  track-saw cuts (document) or forbid (gate)?
