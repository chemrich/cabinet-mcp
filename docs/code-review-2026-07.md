# Full Codebase Review — July 2026

Top-to-bottom correctness and security review of `cabinet-mcp`. Conducted across
eight parallel module-focused passes; every high-impact finding below was
independently reproduced against the working tree.

**Baseline at review time:** 1060 tests pass / 6 skipped; 283 eval scenarios /
940 assertions pass. That green is thinner than it looks — the two areas with
real bugs (the CadQuery geometry paths and the embedded viewer) are exactly the
areas with the least test/eval coverage. The pure-Python parametric core
(clearances, dado/rabbet offsets, column→bay width math, persistence
round-trip, the eval harness's fail-closed behavior) checks out. Defects
cluster in three places: untested CadQuery geometry, the presentation/BOM
layer, and input handling at the server boundary.

Severity: **Critical** = broken/insecure as shipped; **Major** = wrong,
user-visible; **Minor/Nit** = cleanup.

---

## Critical / high-impact

### C1 — Door hinge-cup borings are cut on the wrong axis (feature has never worked)
`door.py:229` (`make_door_panel`) uses `cq.Workplane("YZ")` with a transposed
offset, so cups bore across the door *width* at a transposed position instead of
into the back face. Reproduced: a 500×700 door removes **6,254 mm³** vs the
**25,015 mm³** two cups should remove — one cup lands entirely off the panel,
the other half-off. Same class as the historical shelf-pin workplane bug.
Untested (tests assert only `HingeSpec` numbers). Latent (no internal caller
today) but broken as shipped.
**Fix:** `cq.Workplane("XZ").transformed(offset=(boring_x, z_pos, -t)).cylinder(cup_depth, cup_r, centered=(True, True, False))`.

### C2 — `visualize_project` crashes on any multi-column cabinet
`server.py:149` (`_sort_drawer_config`) does `str(row[1])`, but multi-column
openings arrive as dicts, raising `KeyError: 1`. Reproduced end-to-end: a
two-column project returns `ERROR: KeyError: 1`. Zero eval coverage of either
visualize tool, which is why it went unnoticed.
**Fix:** normalize each row via `cabinet.to_opening` before sorting, or handle
the dict case in `_type`/`_height`.

### C3 — Path traversal in cutlist/visualize output names
`project.py` validates project names as filename stems, but the
cutlist/visualize `name` argument (and inline-project `name`) bypass that.
Reproduced: `name="../../../../tmp/.../pwned_cutlist"` wrote files outside
`~/.cabinet-mcp`. Affects `generate_cutlist`, `visualize_cabinet`,
`generate_project_cutlist`, `visualize_project` (inline project `name` is never
validated — validation lives only in `save_project`).
**Fix:** route these through a shared `_safe_stem()` (the project-name regex)
and validate inline `project["name"]`.

### C4 — `describe_design` is blind to multi-column cabinets
`describe.py:122` reads only `cfg.openings`, ignoring `cfg.columns`.
Reproduced: the `armoire_2col` preset (6 drawers + 2 doors) returns
`hardware: {}` and `pull_selection_required: False` — the hardware summary is
empty **and the pull-selection workflow gate the server prompts depend on never
fires** for any multi-column design.
**Fix:** aggregate openings across all columns for counts/hardware/pull gating.

### C5 — Domino mortises overrun panel ends for 9 of 10 sizes
`min_edge_distance` is used as a slot-*center* offset in `joinery.py` but as
slot-*edge* clearance in `evaluation.py:465` — the two consumers disagree on the
field's meaning. Reproduced: 8×40 has `min_edge=11` but half-slot `=20.25`, so
the end mortise breaks out of the panel by 9.25 mm. Only 14×28 is safe.
**Fix:** define `min_edge_distance` as slot-edge→panel-end clearance and place
end centers at `min_edge_distance + mortise_length/2` (also makes the
evaluation `min_span` formula exactly consistent).

### C6 — `HAS_KEY` eval assertions silently ignore their expected argument
`harness.py` (`evaluate_assertion`) checks only that the *path* resolves, never
that the named key exists. Confirmed by reading the impl. Eight assertions
across three scenarios are weaker than authored (e.g.
`("files", HAS_KEY, "csv")` passes even if `csv` disappears). The intended
nested keys all currently exist, so tightening won't break the suite.
**Fix:** when `op == HAS_KEY` and `exp` is a string, require
`isinstance(value, dict) and exp in value`; keep `expected in (None, True)` as
the bare-existence check. Also validate `--tag` against `ALL_TAGS` and exit
non-zero when 0 scenarios match (a typo'd tag currently exits 0 — a vacuous
green).

---

## Major (correctness, user-visible)

- **Multi-bay drawer face above a door overlaps it.** `cabinet.py:1064` anchors
  the first *drawer* face to the bottom of the whole stack rather than the first
  *opening*. Reproduced: with `[(450,'door'),(234,'drawer')]`, `bay0_face1`
  spans z 18–702, covering the door at z 18–466. The top-side fix
  (`is_last_in_col`) never got a bottom-side twin; the bug is duplicated in the
  pull-placement block. Fix: `face_z_bot = z_face_start if drw_idx == 0 else opening_z + face_gap/2`.
- **Several evaluation checks can never fire** — they compare a derived property
  against its own defining formula (back-panel width `evaluation.py:306`, side
  clearances `1256-1281`, single-door inset fit `724`), while the
  **inset-door-*pair* check fires spuriously on every correct pair**.
- **CadQuery evaluation checks disagree with the pure-Python paths.**
  `check_drawer_in_opening` includes the applied face in the bbox, so every
  applied-face drawer flunks all three fit checks; `check_interference` includes
  each node's own compound, emitting phantom null-shape warnings. Both would
  flood any assembly-backed evaluation with false errors.
- **auto_fix isn't fixed-point-safe.** The cumulative-heights fixer leaves its
  target error in place for fractional (¾″) interiors, can trade it for new
  hardware errors, and lands on a state the evaluator itself warns about; the
  back-panel fixer can set a rabbet deeper than the side panel (impossible
  geometry the evaluator can't see). The server `auto_fix_cabinet` tool then
  **drops the very field the back-panel fixer changed** from its returned config
  (hand-picked subset serialization — also loses `columns`, joinery specs, etc.).
- **rectpack optimizer has the opcut ID-collision bug** documented as fixed for
  opcut — same-named panels collide (`cutlist.py:478`), producing wrong waste %,
  phantom rotation markers, and unreliable unplaced detection. Zero test
  coverage on that path.
- **Pulls BOM ignores per-opening `num_doors`** (`cutlist.py:935`) while the
  hinge BOM honors it — internally contradictory hardware counts. Joinery
  consumable count ignores `cfg.columns` (latent; current callers pass
  `columns_raw`).
- **Viewer injection / state bugs.** `<\/script>` in `cutlist_prompt` breaks and
  injects the viewer HTML (`json.dumps` doesn't escape `/`); `title`/`info`
  interpolated unescaped. X-ray and diag-color toggles corrupt each other's
  material cache, leaving persistent wrong materials. Fix: `.replace("<\/", "<\\/")`
  on JSON embeds, `html.escape()` the title/info, and cross-disable the two
  toggles.
- **Imperial formatter renders 600 mm as "1 ft 12 in"** (`describe.py:44` —
  rounds inches without carrying into feet). Hits the prose of every standard
  base cabinet.
- **Hardware spec-data issues.** Biscuit slot depths too shallow for #10/#20 to
  seat; `hinge_positions()` goes non-monotonic on doors under ~200 mm; every
  901–1200 mm door self-flags a hinge-spacing warning (`max_hinge_spacing=700`
  contradicts the spec's own 2-hinge rule).

---

## Minor / nits

- Dual-pull placement (`pulls.py`) can approve two physically overlapping pulls
  (checks pull-to-edge, not pull-to-pull gap).
- reportlab crashes the cutlist PDF on tag-like cabinet names (`cutlist.py:1866`
  — unescaped into `Paragraph` markup).
- `consolidate_bom` pollutes notes with a redundant `", side"` and drops the
  second panel's own notes (`cutlist.py:243`).
- Curly-apostrophe furniture lookups silently fail (`furniture_refs.py:589`
  `_norm` — curly→curly no-op replace).
- Adjustable feet get wood-grain textured (`visualize.py:347` — only `/pull/i`
  is exempted); a cabinet named `pull*` loses its finish in project scenes.
- Cutlist request text hardcodes Baltic birch, ignoring a `drawer_box_finish`
  override.
- Project name validation misses length caps and case-insensitive (APFS)
  collisions.
- `.claude/settings.json` allow-rules use a stale `mcp__cabinet-mcp__` prefix;
  the server registers as `cabinet`, so the rules match nothing.
- Assorted spec/message mismatches: Domino min-thickness message says "+3 mm"
  but code uses +2; degenerate drawer-height message omits `min_bottom_clearance`;
  Festool/dowel part numbers disagree between `joinery.py` and `cutlist.py`
  PRICE_LIST (needs a supplier-catalog check).

---

## Systemic notes

- **No unit tests** for `auto_fix.py`, `describe.py`, `proportions.py`
  (eval-only coverage — and their eval assertions include the weakened `HAS_KEY`
  cases, so `describe.py` in particular is thinner than the suite suggests).
- **Optimizer paths**: rectpack has zero coverage anywhere; strip is exercised
  only in lite CI. Full-mode `auto` always picks opcut, so
  `TestNoRectpack`-style tests don't actually hit the fallback.
- **Visualize tools have zero eval coverage** despite being the historically
  buggiest area (six documented viewer fixes) — and C2 lives there.
- **Duplication breeds these bugs**: the multi-bay face/door/pull placement
  logic is copy-pasted three times (which is how the face-overlap bug exists in
  two places); the four `positions_for_span` implementations are near-identical
  copies. Extracting shared helpers would collapse whole classes of drift.

---

## Suggested fix sequencing (separate PRs)

1. **Security/crash** — C2, C3, viewer `<\/script>`/escaping. Independently testable.
2. **Geometry** — C1, multi-bay face overlap. All CadQuery; need new geometry tests (the coverage gap that let them survive).
3. **Evaluation/auto_fix** — inset-pair, tautological checks, fixer convergence, dropped-field serialization.
4. **BOM/joinery** — C5 Domino semantics, rectpack IDs, pulls `num_doors`, biscuit depths, hinge rules.
5. **Describe + infra** — C4, C6, imperial formatter, `--tag` guard, stale settings prefix.

Two items need shop-reality judgment before coding: the Festool/dowel
part-number mismatches (verify against the actual supplier SKUs) and the IKEA
pull price basis (per-pack vs per-each — ambiguous in the data, affects BOM
totals).
