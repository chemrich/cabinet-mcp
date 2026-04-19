"""
proportions.py — furniture proportion utilities for drawer heights and column widths.

Two public functions:

    graduated_drawer_heights(total_mm, num_drawers, ratio, ...)  → list[float]
    column_widths(total_mm, num_columns, wide_index, ratio, ...)  → list[float]

Both accept either a numeric ratio or a named preset string.

Named presets
─────────────
  "equal"   — 1.0   all openings the same height / all columns the same width
  "subtle"  — 1.20  gentle graduation; almost imperceptible on fewer than 4 drawers
  "classic" — 1.40  the traditional cabinet-maker's graduation; reads clearly at 3–5 drawers
  "golden"  — 1.618 (φ) golden ratio; approximates the Fibonacci sequence

Background
──────────
Graduated drawer heights have been documented in woodworking literature since at
least the 18th century.  The most commonly cited system is a geometric progression
where each drawer opening is r× taller than the one directly above it (bottom
drawer is always the largest).  r ≈ 1.618 approximates the Fibonacci sequence
(successive Fibonacci numbers converge to the golden ratio).  Values of 1.2–1.4
are common in production furniture where the drama of full golden-ratio graduation
would be excessive.

Column-width proportions follow the same logic: a wide centre (or accent) column
at ratio φ relative to the flanking columns is the most cited specific value in
furniture design literature.
"""

from __future__ import annotations

import math

PHI = (1 + math.sqrt(5)) / 2  # golden ratio ≈ 1.618033…

RATIO_PRESETS: dict[str, float] = {
    "equal":   1.0,
    "subtle":  1.20,
    "classic": 1.40,
    "golden":  PHI,
}

_PRESET_DESCRIPTIONS: dict[str, str] = {
    "equal":   "Uniform — all openings identical",
    "subtle":  "Gentle 1.2× graduation — modern, understated",
    "classic": "Traditional 1.4× graduation — reads clearly at 3–5 drawers",
    "golden":  "Dramatic φ (1.618×) graduation — approximates Fibonacci; best at 3–4 drawers",
}


def _mm_to_inches_str(mm: float) -> str:
    """Fractional-inch string rounded to nearest ⅛″ (e.g. 79 mm → '3⅛')."""
    total_eighths = round(mm / 25.4 * 8)
    whole = total_eighths // 8
    rem   = total_eighths % 8
    frac  = {0: "", 1: "⅛", 2: "¼", 3: "⅜", 4: "½", 5: "⅝", 6: "¾", 7: "⅞"}[rem]
    return f"{whole}{frac}" if whole else frac


def _resolve_ratio(ratio: float | str, context: str) -> float:
    if isinstance(ratio, str):
        if ratio not in RATIO_PRESETS:
            valid = ", ".join(f'"{k}"' for k in RATIO_PRESETS)
            raise ValueError(
                f"Unknown {context} ratio preset {ratio!r}. Valid presets: {valid}."
            )
        return RATIO_PRESETS[ratio]
    ratio = float(ratio)
    if ratio <= 0:
        raise ValueError(f"{context} ratio must be > 0, got {ratio}.")
    return ratio


def graduated_drawer_heights(
    total_mm: float,
    num_drawers: int,
    ratio: float | str = "classic",
    *,
    min_height_mm: float = 75.0,
) -> list[float]:
    """Return drawer opening heights ordered bottom-to-top that sum to *total_mm*.

    The bottom drawer is always the tallest.  Each drawer above it is
    ``1/ratio`` the height of the drawer below it, creating a geometric
    progression.  Heights are rounded to 0.1 mm; any rounding residual is
    absorbed by the bottom (largest) drawer so the sum is exact.

    Parameters
    ----------
    total_mm:
        Interior height to fill, in mm.
    num_drawers:
        Number of drawer openings.
    ratio:
        Graduation ratio (each drawer is this much taller than the one above).
        Pass a float (e.g. 1.4) or a preset name: "equal", "subtle",
        "classic", or "golden".
    min_height_mm:
        Minimum acceptable opening height (default 75 mm ≈ 3").  A ValueError
        is raised if any drawer would fall below this threshold.

    Returns
    -------
    list[float]
        Heights in mm, index 0 = bottom (largest), index -1 = top (smallest).
    """
    if num_drawers < 1:
        raise ValueError("num_drawers must be >= 1.")
    if total_mm <= 0:
        raise ValueError("total_mm must be > 0.")

    r = _resolve_ratio(ratio, "drawer")

    if num_drawers == 1 or r == 1.0:
        h = round(total_mm / num_drawers, 1)
        # distribute any rounding residual to index 0
        heights = [h] * num_drawers
        heights[0] = round(total_mm - h * (num_drawers - 1), 1)
        return heights

    # Geometric series: h0, h0/r, h0/r², …, h0/r^(n-1)   (bottom to top)
    # Sum = h0 × Σ r^(-i) for i in 0..n-1
    inv_powers = [r ** (-i) for i in range(num_drawers)]
    h0 = total_mm / sum(inv_powers)

    heights = [round(h0 * p, 1) for p in inv_powers]

    # Reabsorb rounding error into the bottom drawer
    heights[0] = round(total_mm - sum(heights[1:]), 1)

    top_height = heights[-1]
    if top_height < min_height_mm:
        raise ValueError(
            f"With ratio={r:.3f} and {num_drawers} drawers the top drawer "
            f"would be {top_height:.0f} mm — below the {min_height_mm:.0f} mm "
            f"minimum.  Try a smaller ratio or fewer drawers."
        )

    return heights


def column_widths(
    total_mm: float,
    num_columns: int,
    wide_index: int | None = None,
    ratio: float | str = "golden",
) -> list[float]:
    """Return column interior widths that sum to *total_mm*.

    When *wide_index* is given, that column is ``ratio`` times the width of
    each of the remaining (equal-width) columns.  The classic sideboard layout
    is ``wide_index=1`` (centre) with ``ratio="golden"``.

    Parameters
    ----------
    total_mm:
        Total interior width to distribute, in mm.
    num_columns:
        Number of columns.
    wide_index:
        0-based index of the accent (wide) column.  ``None`` → all equal.
    ratio:
        How much wider the accent column is relative to each narrow column.
        Pass a float or a preset name: "equal", "subtle", "classic", "golden".

    Returns
    -------
    list[float]
        Widths in mm, left-to-right.  Sums to *total_mm* (within 0.1 mm due
        to rounding; residual absorbed by the wide column).
    """
    if num_columns < 1:
        raise ValueError("num_columns must be >= 1.")
    if total_mm <= 0:
        raise ValueError("total_mm must be > 0.")

    r = _resolve_ratio(ratio, "column")

    if num_columns == 1 or wide_index is None or r == 1.0:
        w = round(total_mm / num_columns, 1)
        widths = [w] * num_columns
        widths[0] = round(total_mm - w * (num_columns - 1), 1)
        return widths

    if not (0 <= wide_index < num_columns):
        raise ValueError(
            f"wide_index must be in 0..{num_columns - 1}, got {wide_index}."
        )

    # wide = r × narrow   →   (n_narrow × narrow) + r × narrow = total
    # narrow × (n_narrow + r) = total
    n_narrow = num_columns - 1
    w_narrow = round(total_mm / (n_narrow + r), 1)
    w_wide   = round(total_mm - w_narrow * n_narrow, 1)  # absorbs rounding

    widths = [w_narrow] * num_columns
    widths[wide_index] = w_wide
    return widths


def describe_proportions(
    total_mm: float,
    num_drawers: int,
    ratio: float | str = "classic",
) -> dict:
    """Return a human-readable summary of a graduated drawer stack.

    Useful for the MCP describe_design tool or for presenting options to the
    user before committing to a layout.
    """
    r = _resolve_ratio(ratio, "drawer")
    heights = graduated_drawer_heights(total_mm, num_drawers, r)
    label = ratio if isinstance(ratio, str) else f"{r:.3f}"
    return {
        "preset": label,
        "ratio": round(r, 4),
        "num_drawers": num_drawers,
        "total_mm": total_mm,
        "heights_bottom_to_top_mm": heights,
        "bottom_mm": heights[0],
        "top_mm": heights[-1],
        "bottom_to_top_ratio": round(heights[0] / heights[-1], 3),
    }
