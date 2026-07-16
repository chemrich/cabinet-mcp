---
name: add-preset
description: Add a new named cabinet preset to cabinet-mcp. Use when asked to add a preset, template, or canned design to presets.py (surfaced via list_presets / apply_preset). Covers the CabinetPreset registration pattern, the opening-stack sum invariant, and the guard test that every preset must evaluate with zero errors.
---

# Adding a cabinet preset

Presets live in `src/cadquery_furniture/presets.py` as frozen `CabinetPreset` dataclasses, registered by wrapping each in `_p(...)`.

## Steps

1. **Add the preset** near the others in its category section:

   ```python
   _p(CabinetPreset(
       name="workshop_tool_chest",          # slug for apply_preset (kebab/snake, unique)
       display_name="Workshop Tool Chest",   # human label
       description="One-line use-case description.",
       category="workshop",                  # kitchen | workshop | bedroom | bathroom | storage
       tags=["workshop", "drawer", "tool"],  # searchable
       difficulty="standard",                # basic | standard | advanced
       config=CabinetConfig(
           width=900, height=720, depth=550,
           openings=[                         # (height_mm, opening_type) bottom→top
               (300, "drawer"),
               (192, "drawer"),
               (192, "drawer"),
           ],
           drawer_slide="blum_tandem_550h",
           door_hinge="blum_clip_top_110_full",
           carcass_joinery=CarcassJoinery.DADO_RABBET,
       ),
   ))
   ```

2. **Honor the opening-stack invariant.** The opening heights must sum to the interior height = `height - top_thickness - bottom_thickness` (default `720 - 18 - 18 = 684`). A stack that over-fills raises an ERROR (the guard test rejects it). A stack that sums *exactly* to interior — which every existing preset does — raises a benign `cumulative_heights` **WARNING** (zero reveal at the top); that is accepted, not something to design away. The bar for a preset is **zero ERROR-severity issues**, warnings allowed.

3. **Use real hardware keys.** `drawer_slide` / `door_hinge` / `drawer_pull` / `door_pull` must exist in `hardware.py` (`SLIDES`, `HINGES`, `PULLS`). An unknown key is **not** silently dropped or resolved to `None` — it raises `KeyError` (loudly, listing the available keys) as soon as the hardware is consulted for a matching opening, e.g. when you `evaluate_cabinet` or generate a cutlist for a config that has the relevant drawer/door. Check valid keys with `list_hardware` or by grepping the spec dicts.

4. **For multi-column presets:** set `columns=[ColumnConfig(width_mm=..., openings=[...]), ...]` instead of a single `openings` stack; each column's stack must sum to interior height, and column widths + dividers must sum to interior width. If any column has a `door`/`door_pair` taller than ~305 mm, ask the user whether to add a fixed shelf before finalizing (see the shelf-prompt feedback memory).

## Verify

- **Run the guard test.** The zero-error guard is `TestPresetEvaluationClean::test_no_errors` in `tests/test_new_presets.py`. It is parametrized over `ALL_PRESET_SLUGS = sorted(PRESETS)`, so your new preset is picked up automatically once registered with `_p(...)` — no separate list to edit. The same file's `TestOpeningStackIntegrity` also checks your stack sums to interior. Run:
  ```bash
  uv run pytest tests/test_new_presets.py -q
  ```
- **Spot-check** the new preset has no ERROR-severity issues by driving the handler (see `drive-mcp-handlers`):
  ```python
  from cadquery_furniture.presets import PRESETS
  from cadquery_furniture.evaluation import evaluate_cabinet
  issues = evaluate_cabinet(PRESETS["workshop_tool_chest"].config)
  print([(i.check, i.severity.name) for i in issues])   # no ERROR entries; a cumulative_heights WARNING is expected
  ```
- Then run the full suite + evals (`run-evals` skill) — several eval scenarios apply presets and assert on them.
