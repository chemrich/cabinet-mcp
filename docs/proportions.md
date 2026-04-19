# Proportion system

Cabinet furniture has a long tradition of graduated proportions — drawers that get shorter as they rise, columns that widen toward a visual anchor. `proportions.py` encodes the most cited systems as named presets so a layout can be described in plain English ("classic graduation, golden column widths") and get mathematically correct dimensions back.

## Drawer height graduation

Each drawer is shorter than the drawer below it by a consistent ratio `r`:

```
bottom height = H
next up       = H / r
next up       = H / r²
  ⋮
top drawer    = H / r^(n-1)
```

`H` is chosen so all heights sum to the target interior height. Any rounding residual is absorbed by the bottom drawer.

| Preset | Ratio | Character | Best for |
|--------|-------|-----------|----------|
| `equal` | 1.0 | Uniform | Tool chests, utilitarian storage |
| `subtle` | 1.2× | Barely noticeable at 3, clear at 5+ | Modern minimalist |
| `classic` | 1.4× | The standard cabinet-maker's graduation | Dressers, sideboards, kitchen bases |
| `golden` | 1.618× (φ) | Dramatic — strong visual hierarchy | Showpieces, 3–4 drawers only |

**Example — 5-drawer sideboard, 864 mm interior:**

| Preset | Bottom → Top (mm) | Top drawer |
|--------|-------------------|------------|
| `equal` | 173 / 173 / 173 / 173 / 173 | 173 mm (6¾″) |
| `subtle` | 241 / 201 / 167 / 139 / 116 | 116 mm (4½″) |
| `classic` | 303 / 217 / 155 / 110 / 79 | 79 mm (3⅛″) |
| `golden` | ✗ top drawer below 75 mm minimum | — |

`graduated_drawer_heights()` raises `ValueError` rather than returning an unusable layout when the top drawer falls below the minimum.

## Column width proportions

One accent column is `ratio` times the width of each flanking column; flanking columns are always equal to each other.

| Preset | Ratio | 3 columns, 1184 mm interior |
|--------|-------|------------------------------|
| `equal` | 1.0 | 395 / 395 / 395 mm |
| `subtle` | 1.2× | 370 / 444 / 370 mm |
| `classic` | 1.4× | 348 / 488 / 348 mm |
| `golden` | 1.618× | 327 / 530 / 327 mm |

`wide_index` picks the accent: `1` (centre) is the conventional dresser layout; `0` or `2` give asymmetric compositions.

## Using proportions from the MCP tools

```
design_cabinet(width=600, height=900, depth=457,
               num_drawers=5, drawer_proportion="classic")

design_multi_column_cabinet(
    width=1220, height=900, depth=457,
    num_columns=3, wide_index=1, column_proportion="golden",
    num_drawers=5,             drawer_proportion="classic",
)
```

The tool computes the interior height, runs `graduated_drawer_heights`, and inserts the results as `drawer_config`. The response includes `proportions_used` so the caller can inspect or override any value.

## Using proportions from Python

```python
from cadquery_furniture.proportions import (
    graduated_drawer_heights,
    column_widths,
    describe_proportions,
)

graduated_drawer_heights(864, num_drawers=5, ratio="classic")
# → [303.3, 216.6, 154.7, 110.5, 78.9]  (bottom → top, sums to 864)

column_widths(1184, num_columns=3, wide_index=1, ratio="golden")
# → [326.7, 530.6, 326.7]

describe_proportions(864, num_drawers=4, ratio="golden")
# {"preset": "golden", "ratio": 1.618,
#  "heights_bottom_to_top_mm": [386.1, 238.6, 147.5, 91.2],
#  "bottom_to_top_ratio": 4.234}
```

## Mixing explicit and proportional specs

The shortcuts are additive, not exclusive:

- Explicit `columns` array with `width_mm` but no `drawer_config` → your widths, auto-computed heights
- Full `columns` array (widths + drawer configs) and no proportion parameters → untouched, no auto-layout
- `num_columns` + proportion parameters, no `columns` array → full auto-layout
