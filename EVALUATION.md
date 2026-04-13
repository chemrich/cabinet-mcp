# cadquery-furniture — Evaluation Report

**Date:** 2026-04-05
**Environment:** uv 0.11.2 / Python 3.10.12
**Test run:** 33 passed, 0 failed in 0.03s

---

## Setup (uv)

```bash
uv venv --python /usr/bin/python3
uv pip install -e ".[dev]"
uv run pytest cadquery_furniture/tests/ -v -p no:cacheprovider
```

A `uv.lock` file has been generated for reproducibility. Add `addopts = "-p no:cacheprovider"` to `[tool.pytest.ini_options]` in `pyproject.toml` to avoid a temp-file cleanup error when running inside a sandbox/mounted filesystem.

---

## Test Results

All **33 tests pass** cleanly. Coverage is solid for the pure-Python evaluation and cutlist paths. The CadQuery-dependent geometry paths (`make_side_panel`, `build_cabinet`, `build_drawer`, etc.) are not tested because cadquery is not available in the sandbox — this is by design.

---

## Bugs Found

### BUG 1 — `cutlist.py`: `extract_bom_parametric` always returns empty list

**File:** `cadquery_furniture/cutlist.py`, line 129–151
**Severity:** High — this function is broken and silently returns nothing

```python
def extract_bom_parametric(parts: list[PartInfo]) -> list[CutlistPanel]:
    panels = []
    for part in parts:       # iterates but…
        try:
            return extract_bom(parts)   # …tries the whole list on every iteration
        except Exception:
            pass             # if extract_bom fails, falls through to append
        panels.append(CutlistPanel(...))
    return panels
```

**Problem:** `return extract_bom(parts)` is inside the loop. If extraction succeeds it returns on the first iteration (correct by accident). If extraction fails — e.g. when CadQuery is not installed — the exception is caught and the fallback `panels.append(...)` runs, but `extract_bom(parts)` is retried again on every subsequent iteration and fails again, so only one fallback panel is ever appended before the loop logic continues. Net result: returns `[]` when CadQuery is absent and parts list has more than one item.

**Fix:** Hoist the try/except outside the loop:

```python
def extract_bom_parametric(parts: list[PartInfo]) -> list[CutlistPanel]:
    try:
        return extract_bom(parts)
    except Exception:
        pass
    # CadQuery not available — return zero-dimension fallback panels
    return [
        CutlistPanel(
            name=part.name,
            length=0, width=0,
            thickness=part.material_thickness,
            grain_direction=part.grain_direction,
            edge_band=part.edge_band,
            notes=part.notes + " [dimensions not computed — CadQuery not available]",
        )
        for part in parts
    ]
```

---

### BUG 2 — `cabinet.py`: `dado_x` mirror logic is inverted

**File:** `cadquery_furniture/cabinet.py`, lines 129 and 139
**Severity:** High — dados are cut on the wrong face of each side panel

```python
dado_x = 0 if not mirror else cfg.side_thickness - cfg.dado_depth
```

The left panel (`mirror=False`) is positioned at assembly `x=0`. Its interior face is at local `x=side_thickness`. The dado must be cut from the interior side at `x = side_thickness - dado_depth`. With `dado_x=0`, it is cut from the exterior face instead.

The bottom panel is positioned in the assembly at `x = side_thickness - dado_depth`, so it would not engage the dado cut on the left panel as coded.

**Fix:** Invert the condition:

```python
dado_x = cfg.side_thickness - cfg.dado_depth if not mirror else 0
```

The same inversion affects the rabbet cut for the back panel (line 119–125) and the shelf pin hole column (line 151).

---

### BUG 3 — `cabinet.py`: shelf pin hole x-position is identical for both sides

**File:** `cadquery_furniture/cabinet.py`, line 151
**Severity:** Medium — drilling goes to the same column on both left and right panels

```python
hole_x = cfg.side_thickness / 2 if not mirror else cfg.side_thickness / 2
```

Both branches compute `side_thickness / 2`. For the 32mm system, pin columns are typically inset a fixed distance from the interior face (e.g., 37mm from the face). The current code drills dead-center of the panel regardless of which face is interior.

**Fix:**

```python
# Left panel: interior face at x = side_thickness, columns inset from there
hole_x = cfg.side_thickness - cfg.shelf_pin_row_inset  if not mirror else cfg.shelf_pin_row_inset
```

(This also depends on getting BUG 2 fixed first so the correct face is established.)

---

### BUG 4 — `evaluation.py`: duplicate drawer height error

**File:** `cadquery_furniture/evaluation.py`, lines 118–135 and 136–146
**Severity:** Low — users see the same height violation twice

`check_drawer_hardware_clearances` calls `slide.validate_drawer_dims(...)`, which already checks `drawer_height < min_drawer_height`. Then it checks the same condition again explicitly. A short drawer generates two `ERROR` issues with nearly identical messages.

**Fix:** Remove the explicit `drawer_min_height` block (lines 136–146) since `validate_drawer_dims` covers it, or remove the height check from `validate_drawer_dims` and keep it only in the evaluation layer.

---

### BUG 5 — `cutlist.py`: `consolidate_bom` discards original part notes

**File:** `cadquery_furniture/cutlist.py`, line 181
**Severity:** Low — "1/4 inch plywood" and similar material notes vanish after consolidation

When a new key is first inserted, `notes=panel.name` overwrites `panel.notes`. Subsequent merges append only part names. Original notes (e.g. "1/4 inch plywood") are lost.

**Fix:**

```python
new_panel = CutlistPanel(
    ...
    notes=panel.notes,  # preserve original notes
)
```

And in the merge branch, decide whether to append the part name or the notes separately.

---

## Coverage Gaps

The following code paths have **no tests** and some contain the bugs above:

| Path | Gap |
|------|-----|
| `cutlist.extract_bom_parametric` | Untested; contains BUG 1 |
| `cutlist.print_bom` | Untested output function |
| `DrawerConfig` properties (`box_width`, `box_height`, `box_depth`, `bottom_panel_*`, `face_*`) | No unit tests |
| `CabinetConfig` properties (`interior_width`, `interior_depth`, `back_panel_width`) | No unit tests |
| `evaluate_cabinet` integration runner | No end-to-end test tying checks together |
| `Accuride 3832` hardware spec | Only Blum Tandem tested |
| `Blum Movento 760H` hardware spec | Only Blum Tandem tested |
| `check_shelf_deflection` marginal warning (70–100% of limit) | Not tested |
| `drawer.drawers_from_cabinet_config` | Untested |
| `evaluation.print_report` | Untested output function |

### Suggested additional tests

```python
# DrawerConfig properties
def test_drawer_config_box_dims():
    cfg = DrawerConfig(opening_width=564, opening_height=150, opening_depth=541)
    assert abs(cfg.box_width - 538.6) < 0.1
    assert cfg.box_height == 147.0
    assert cfg.box_depth <= cfg.opening_depth

# CabinetConfig properties
def test_cabinet_config_derived_dims():
    cfg = CabinetConfig(width=600, height=720, depth=550)
    assert cfg.interior_width == 564.0
    assert cfg.interior_depth == 541.0
    assert cfg.back_panel_width == 576.0

# extract_bom_parametric fallback
def test_extract_bom_parametric_no_cq():
    parts = [PartInfo(name='p', shape=None, material_thickness=18, grain_direction='length')]
    result = extract_bom_parametric(parts)
    assert len(result) == 1
    assert 'not computed' in result[0].notes

# Shelf deflection marginal warning
def test_shelf_deflection_marginal():
    # Tune values to hit 70–99% of limit
    issues = check_shelf_deflection(span=900, depth=300, thickness=18, load_kg=20)
    warnings = [i for i in issues if i.severity == Severity.WARNING]
    assert len(warnings) > 0

# evaluate_cabinet integration
def test_evaluate_cabinet_clean():
    cfg = CabinetConfig(height=720, width=600, depth=550,
                        drawer_config=[(150, "drawer"), (150, "drawer")])
    issues = evaluate_cabinet(cfg)
    errors = [i for i in issues if i.severity == Severity.ERROR]
    assert len(errors) == 0
```

---

## Design Observations

**Slide bracket inset is conservative.** `BLUM_TANDEM_550H` has `rear_bracket_inset=2, front_bracket_inset=2`, so a 500mm interior depth yields only a 450mm slide (usable=496mm, and 500mm slide requires 504mm interior). In practice the Blum 550H front bracket sits at the cabinet face with ~0mm inset; double-check datasheet values.

**`DrawerConfig.box_depth` uses slide length as a hard cap**, which is correct. But the test in `test_evaluation.py::TestDrawerHardwareClearances::test_valid_drawer` uses `opening_depth=500`, which selects a 450mm slide. The test passes because no depth check is asserted — worth adding an assertion that the slide selected is reasonable for the given depth.

**`examples/` directory is empty.** A working end-to-end example script would be valuable both as documentation and as a smoke test that exercises the full pipeline.

**No `[tool.pytest.ini_options] addopts`** — recommend adding `-p no:cacheprovider` to avoid the temp-file cleanup permission error on mounted filesystems.

---

## Recommended pyproject.toml changes

```toml
[tool.pytest.ini_options]
testpaths = ["cadquery_furniture/tests"]
addopts = "-p no:cacheprovider"
```

---

## Summary

| Category | Count |
|----------|-------|
| Tests passing | 33 / 33 |
| High severity bugs | 2 (BUG 1, BUG 2) |
| Medium severity bugs | 1 (BUG 3) |
| Low severity bugs | 2 (BUG 4, BUG 5) |
| Untested code paths | ~10 |

The pure-Python evaluation and cutlist layers are solid and well-structured. The CadQuery geometry layer (cabinet.py, drawer.py) has the most risk — the dado/rabbet mirror logic is inverted (BUG 2), and those functions can't be tested without a CadQuery install. The `extract_bom_parametric` fallback path (BUG 1) is silently broken.
