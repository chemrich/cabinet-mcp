# Full code review — 2026-07-17

Scope: full codebase with emphasis on the five PRs merged 2026-07-17 (#24 per-drawer
options + size-based bottoms, #25 project library + batch cutlists, #26
drawer_box_thickness + sheet pooling, #27 pre-finished drawer boxes, #28 per-drawer
slide_key) and their integration with older code. Method: eight parallel module-cluster
review agents, every finding substantiated with a runnable repro or code trace, majors
independently re-verified before acceptance. Baseline before fixes: main@0cd32ac,
1240 tests passed / 6 skipped, evals 291 scenarios / 1009 assertions, 100%.

Severity: **major** = wrong output, crash, or data loss reachable through normal tool
use; **minor** = wrong in an edge case, misleading output, or robustness gap;
**nit** = latent/cosmetic. Every item below was verified; "deferred data" items need
Charlie's shop/supplier input and are deliberately not code-fixed.

## Majors

| # | Where | Defect |
|---|---|---|
| M1 | `hardware.py` Movento 769, Salice Futura ×2 | `max_load_kg` (documented as *dynamic* rating) carries the *static* number: Movento 77 vs 70 kg dynamic, Salice 45 vs 34 kg — capacity overstated up to 32%, per the specs' own source comments. |
| M2 | `joinery.py` QQQ `from_stock` | With `front_back_thickness ≤ side_thickness/2` the sub-front tongue/channel is deeper than the panel (19/6 stock → channel 9.5 mm in a 6 mm panel, rabbet −3.5 mm) — physically impossible joint, reachable via `design_drawer` with no error. |
| M3 | `auto_fix.py` `_fix_cumulative_heights` | Rebuilds openings from a hand-written field list that omits `slide_key` and `bottom_thickness` — a height rebalance silently strips per-drawer hardware/bottom overrides (verified: overrides → `None` after fix). |
| M4 | `evaluation.py` slide resolution | A bad per-opening `slide_key` (or bad cabinet default) raises an uncaught `KeyError` out of `evaluate_cabinet` — the whole evaluation aborts with a bare traceback instead of an ERROR issue. |
| M5 | `auto_fix.py` `_min_opening_height` | Ignores standard-height snapping: clamped openings yield raw box height = slide minimum, which snaps *down* below the minimum (79→76 for Salice) — auto_fix reports "Rebalanced" but the returned config still fails evaluation. Also ignores per-opening `slide_key` when clamping. |
| M6 | `evals/scenarios.py` (45 `generate_cutlist` calls) | Scenarios omit `name`, so the stem defaults to `"cabinet"` and every eval run silently overwrites a user's real `~/.cabinet-mcp/cutlists/cabinet_*` files (verified by mtime). Only `eval_`-prefixed pollution is accepted convention. |
| M7 | `server.py` `_cabinet_assembly` bay configs | The hand-built per-column bay `CabinetConfig` omits `drawer_box_thickness` / `drawer_box_prefinished` (and `leg_key`/`leg_count`/`leg_inset`, `adj_shelf_holes` + pin params, dado/rabbet params, joinery specs) — multi-column visualizations render 15 mm default boxes and default feet while cutlist/evaluation use the configured values. Root cause: hand-picked field list instead of `dataclasses.replace`. |

## Minors

- `evaluation.py`: pre-loop `slide = get_slide(cab_cfg.drawer_slide)` is dead but still
  crashes on a bad cabinet default even when every opening overrides it; the CadQuery
  `check_drawer_in_opening` loop validates every drawer against the cabinet-level slide,
  wrong under mixed per-drawer slides; the `try/except` guarding the heavy-bottom check
  carries a false comment ("already reported above" — nothing reports it).
- `cabinet.py` `to_opening`: per-opening option values are not type-coerced (string
  `"12"` crashes the cutlist with a raw traceback); explicit `bottom_thickness ≤ 0`
  accepted everywhere (negative-thickness sheet group); `float("nan")` heights pass and
  NaN silently disables every downstream check; column normalization only inspects
  `openings[0]`, so mixed tuples keep raw rows and crash later; dead
  `get_slide(cfg.drawer_slide)` in `build_multi_bay_cabinet` fails visualize for
  configs evaluate/cutlist accept.
- `door.py` / `cabinet.py` door path: `doors_from_cabinet_config` ignores every
  per-opening door override (`num_doors`, `hinge_key`, `pull_key`, `door_thickness`,
  `hinge_side`); `num_doors: 2` on a `"door"` slot bills 2× hinges while rendering and
  evaluating as a single door.
- `server.py`: top-level `waste_pct` is just the thickest carcass group's value; batch
  `project_names` accepts duplicates (double-counts everything), the default joined
  batch stem can exceed the 100-char limit, `batch_name` colliding with a saved project
  silently overwrites that project's cutlist files, `batch_name` without
  `project_names` is silently ignored; `list_projects` `count` includes unreadable
  snapshots while `names` excludes them; a sheet-goods group with no PRICE_LIST entry
  prices silently at $0.00; the visualize path sorts column stacks
  (`_sort_drawer_config`) while cutlist/evaluation consume raw order.
- `project.py`: `list_saved_projects` stats the file before the `try` (dangling symlink
  sinks the listing); unknown `shared` keys raise a bare `TypeError` instead of the
  friendly `ValueError` other input paths give; corrupt snapshot loads surface with no
  project name/path; a supplied `overrides` list is exhaustive (suppresses inference) —
  correct but undocumented.
- `cutlist.py`: `consolidate_hardware_lines` appends duplicate notes ("533 mm" × 21 in
  the kapex BOM); `_panel_colour` uses salted `hash()` → nondeterministic colors per
  run; sheet name interpolated into layout HTML without `_esc`; a known slide that
  doesn't fit the depth raises out of the whole hardware BOM (vs unknown key skipping
  one drawer); optimizers pack panels onto mismatched-thickness stock without warning;
  pull walker misses the `op.slide_key` threading (inert today); the slide walker's
  `DrawerConfig` is dead weight; `to_json` `can_rotate` disagrees with the optimizers
  about `None` grain.
- `hardware.py`: documented Blum hinge-count tables (≤1200→2, ≤1800→3) are dead —
  the 700 mm max-spacing rule dominates above 900 mm (docstrings corrected; whether
  700 mm is a real Blum constraint is deferred data); `validate_drawer_dims` accepts
  `drawer_depth` but never checks it.
- `presets.py`: `config_dict()` drops `drawer_joinery`, leg fields, shelf-pin params,
  joinery specs, per-column `fixed_shelf_positions`, and per-opening options (latent —
  all current presets use defaults; guard test added); tall `adj_shelf_holes` presets
  (pantry 2100, armoire 1900, linen tower 1900) keep the default
  `shelf_pin_end_z=640`, drilling pins only in the bottom third; multi-column presets
  list an empty `opening_stack` in `list_presets`.
- `joinery.py`: `from_stock` accepts zero/negative stock; `glue_area_corner` mixes
  per-mm and absolute units across styles (no callers).
- `server.py` `compare_joinery`: QQQ note hardcodes "18 mm" regardless of input.
- `visualize.py` `_js_str`: `<!--` not escaped (script-data double-escape parse
  breakage; no code execution demonstrated; MCP inputs pre-validated).
- Skills/CI: `run-evals` frontmatter still says 283/940; `add-scenario` recommends
  asserting on `ERROR:` results the harness cannot express; `cabinet-review` lists a
  nonexistent `conftest.py`; lite CI has no guard asserting CadQuery is actually absent.
- `evals/scenarios.py`: `count GTE 1` tautology in `project_library_list_and_load`.

## Deferred data — resolved post-merge (follow-up PR), one item remaining

- ~~Blum hinge spacing/count~~ — **resolved against Blum's published chart**
  (ea.blum.com "Number of hinges"): ≤900 → 2, ≤1600 → 3, ≤2000 → 4, >2000 → 5.
  The 700 mm spacing raise reproduces this chart within a hinge across the practical
  range — the old 1200/1800 base table was the wrong element, now replaced. Only
  behavioral change: doors over 2000 mm get 5 hinges (was 4).
- ~~Salice Progressa+ 686 mm~~ — **confirmed orderable**: the US inch series includes
  27" (686 mm); cabinetparts.com lists 27" Progressa+ Smove. Part number remains
  pattern-derived; the misleading "catalog lists 700 mm" comment is corrected.
- ~~9 mm sheet prices~~ — **added**: raw $56 (3/8" B/BB 5×5, Baker Lumber Jul 2026),
  pre-finished $78 (interpolated between the 6/12 mm pre-finished premiums).
- ~~9" Blum 563 "B10" price anomaly~~ — **confirmed real** (Charlie, 2026-07-18):
  WWE and multiple vendors agree the 9" runs ~$5 over the longer lengths; part
  number correct, not a kit — a low-volume specialty length that simply prices
  higher. PRICE_LIST values stand as-is. No deferred data items remain.

## Explicitly verified clean

Round-trip integrity of the project store (all per-opening options through columns,
shared tokens, pull-preset expansion, explicit overrides); prefinished/raw and mixed-SKU
consolidation keying; batch/path-traversal hardening (`_safe_stem`, `project_path`);
HTML/PDF escaping of all server-generated strings; GLTF dedup-suffix regexes and the
per-box drawer-open animation under mixed slides; `price_for` fallback collision-free
over current keys; slide part-number coverage; Domino/pocket/biscuit/dowel span rules;
harness ops fail-closed, lite CI genuinely lite today (291/1009 passing in a clean lite
venv); new-scenario index assertions sit on deterministic sort orders.
