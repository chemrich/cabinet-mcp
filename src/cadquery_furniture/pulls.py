"""
Placement policy and drill-hole geometry for cabinet pulls and knobs.

This module is pure Python — no CadQuery dependency.  It answers three
questions given a drawer front or door face and a selected pull:

  1. How many pulls should go on this face?
  2. Where does each pull sit, in face-local coordinates?
  3. Does the pull physically fit, and what alternatives would?

Face-local coordinates
----------------------
The origin ``(0, 0)`` is the bottom-left corner of the visible face.
    +x  increases rightward (along the face width)
    +z  increases upward  (along the face height)
Every coordinate returned by this module is in this frame.  The caller
(cabinet assembly code, CadQuery visualiser, etc.) is responsible for
transforming face-local coords into cabinet-global coords.

Dual-pull threshold
-------------------
``DUAL_PULL_THRESHOLD_MM`` (600 mm) is the face-width cutoff at which the
default placement switches from one centred pull to two pulls spaced at the
⅓ and ⅔ points of the face.  This follows the conventional cabinet-shop rule
of thumb: drawers wider than ~24″ feel unbalanced opening on a single pull.
Callers can override by passing an explicit ``count`` to
:func:`pull_positions`.

Knobs are always placed singly — splitting a knob into a "dual knob" layout
is never the right answer; if the face is too wide for a single knob, choose
a pull instead.

Vertical placement
------------------
    "center"       — centre of face (default; matches kitchen-base convention)
    "upper_third"  — pull sits at ⅓ down from the top, i.e. z = 2/3 · height
                     (traditional tall-drawer placement: pulls within arm's
                     reach when drawers are stacked in a dresser)
    "lower_third"  — z = 1/3 · height; used on overhead/wall cabinets so
                     the pull is accessible without reaching the top

End margin
----------
``END_MARGIN_MM`` (40 mm) is the minimum clearance between the outer edge of
the pull body and the edge of the face.  Faces with cc + 2·margin exceeding
the width will be flagged by :func:`pull_fits_face` so the caller can pick a
shorter pull or split to two pulls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .hardware import MountStyle, PullSpec, PULLS


# ── Policy constants ─────────────────────────────────────────────────────────

DUAL_PULL_THRESHOLD_MM: float = 600.0
"""Face-width cutoff. Faces wider than this default to two pulls at ⅓/⅔."""

END_MARGIN_MM: float = 40.0
"""Minimum clearance from the pull's outer edge to the face edge."""


VerticalPolicy = Literal["center", "upper_third", "lower_third"]
"""Vertical placement options exposed to callers."""


# ── Return types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PullPlacement:
    """One pull (or knob) placed on a face.

    ``center`` is the pull's geometric centre in face-local coordinates.
    ``hole_coords`` is the tuple of drill-hole centres (in face-local coords)
    the caller should use to bore mounting holes — one entry for knobs, two
    for surface/edge pulls, empty for flush pulls.
    ``pull_key`` is the catalog id of the chosen pull so BOM generators can
    trace each placement back to a SKU.
    """
    center: tuple[float, float]
    hole_coords: tuple[tuple[float, float], ...]
    pull_key: str


# ── Count selection ──────────────────────────────────────────────────────────


def recommend_pull_count(face_width_mm: float, pull: PullSpec) -> int:
    """Recommend how many pulls to place on a face of the given width.

    Rules:
      - Knobs    : always 1 (see module docstring).
      - Flush    : always 1 (a single routed recess per face).
      - Surface / edge:
          face_width ≤ DUAL_PULL_THRESHOLD_MM → 1
          face_width >  DUAL_PULL_THRESHOLD_MM → 2
    """
    if pull.mount_style in (MountStyle.KNOB, MountStyle.FLUSH):
        return 1
    if face_width_mm <= DUAL_PULL_THRESHOLD_MM:
        return 1
    return 2


# ── Fit check ────────────────────────────────────────────────────────────────


def pull_fits_face(
    face_width_mm: float,
    pull: PullSpec,
    count: int | None = None,
) -> bool:
    """Return True if the chosen pull physically fits the face.

    The guarantee is that for *any* placement we would generate, the pull's
    body stays at least ``END_MARGIN_MM`` away from the nearest face edge.

    For single-pull placements this is simply:
        face_width ≥ length_mm + 2 · END_MARGIN_MM

    For dual-pull placements at ⅓/⅔ spacing, each pull's outer edge sits at
        x_outer = face_width · ⅔ + length_mm / 2   (for the right pull)
    so the same lower bound on face_width as single-pull applies in practice
    (dual pulls are only used above 600 mm, and a pull of body length L fits
     at ⅔ · face + L/2 ≤ face - END_MARGIN iff face ≥ 3·(L/2 + END_MARGIN)).
    We apply the tighter dual-pull inequality when count = 2.
    """
    if count is None:
        count = recommend_pull_count(face_width_mm, pull)

    if count <= 1:
        return face_width_mm >= pull.length_mm + 2 * END_MARGIN_MM

    # Dual-pull: the rightmost pull's centre sits at x = 2/3 · face_width;
    # its outer edge is at 2/3 · face_width + length/2, which must be
    # ≤ face_width - END_MARGIN_MM.  Rearranging:
    #     face_width ≥ 3 · (length/2 + END_MARGIN)
    return face_width_mm >= 3.0 * (pull.length_mm / 2.0 + END_MARGIN_MM)


# ── Placement math ───────────────────────────────────────────────────────────


def _vertical_z(face_height_mm: float, policy: VerticalPolicy) -> float:
    """Return the pull centre z-coordinate for a given vertical policy."""
    if policy == "center":
        return face_height_mm / 2.0
    if policy == "upper_third":
        # One-third of the way down from the top → z = 2/3 · height
        return face_height_mm * 2.0 / 3.0
    if policy == "lower_third":
        return face_height_mm / 3.0
    raise ValueError(
        f"Unknown vertical policy {policy!r}. "
        f"Valid options: 'center', 'upper_third', 'lower_third'."
    )


def _horizontal_centers(face_width_mm: float, count: int) -> list[float]:
    """Return x-coordinates of pull centres for the given count.

    1 pull  → at face centre
    2 pulls → at ⅓ and ⅔ of face width
    3+ pulls→ evenly distributed across the face at (i+1)/(n+1) · width
    """
    if count <= 0:
        raise ValueError(f"count must be ≥ 1, got {count}")
    if count == 1:
        return [face_width_mm / 2.0]
    if count == 2:
        return [face_width_mm / 3.0, face_width_mm * 2.0 / 3.0]
    step = face_width_mm / (count + 1)
    return [step * (i + 1) for i in range(count)]


def pull_positions(
    face_width_mm: float,
    face_height_mm: float,
    pull: PullSpec,
    pull_key: str,
    count: int = 0,
    vertical: VerticalPolicy = "center",
) -> list[PullPlacement]:
    """Return pull placements on a drawer face or door.

    Parameters
    ----------
    face_width_mm, face_height_mm :
        Dimensions of the visible face the pull mounts on.
    pull :
        The selected PullSpec (from :func:`hardware.get_pull`).
    pull_key :
        The catalog id — carried through into each PullPlacement for BOM.
    count :
        Number of pulls.  ``0`` (the default) defers to
        :func:`recommend_pull_count`.  Knobs ignore ``count`` above 1
        (we never split a knob into a dual layout).
    vertical :
        Vertical placement — ``"center"`` (default), ``"upper_third"``, or
        ``"lower_third"``.  See the module docstring.

    Returns
    -------
    list[PullPlacement]
        One entry per placement, each with the pull's centre and the set of
        drill-hole coordinates for the chosen mount style.
    """
    if face_width_mm <= 0 or face_height_mm <= 0:
        raise ValueError(
            f"Face dimensions must be positive, got "
            f"{face_width_mm}×{face_height_mm} mm"
        )

    if count <= 0:
        count = recommend_pull_count(face_width_mm, pull)

    # Knobs never split — coerce to 1 and let the caller choose a longer pull
    # if they need more gripping area.
    if pull.mount_style is MountStyle.KNOB and count > 1:
        count = 1

    z = _vertical_z(face_height_mm, vertical)
    centres_x = _horizontal_centers(face_width_mm, count)

    placements: list[PullPlacement] = []
    for cx in centres_x:
        hole_coords = tuple(
            (cx + dx, z) for dx in pull.hole_offsets_from_center
        )
        placements.append(PullPlacement(
            center=(cx, z),
            hole_coords=hole_coords,
            pull_key=pull_key,
        ))
    return placements


# ── Selection helpers ────────────────────────────────────────────────────────


def compatible_pulls(
    face_width_mm: float,
    *,
    style: Optional[str] = None,
    finish: Optional[str] = None,
    mount_style: Optional[MountStyle] = None,
    brand: Optional[str] = None,
    catalog: Optional[dict[str, PullSpec]] = None,
) -> list[tuple[str, PullSpec]]:
    """Filter the pulls catalog to items that fit the face and match criteria.

    A pull is considered compatible when:
      - it passes :func:`pull_fits_face` for a single-pull layout, AND
      - all supplied filter arguments match (case-sensitive equality).

    ``catalog`` defaults to the global :data:`hardware.PULLS`.  Pass a custom
    dict to search a subset or a test fixture.

    Returns
    -------
    list of ``(key, PullSpec)`` tuples in catalog iteration order.
    """
    source = catalog if catalog is not None else PULLS
    matches: list[tuple[str, PullSpec]] = []
    for key, pull in source.items():
        if not pull_fits_face(face_width_mm, pull, count=1):
            continue
        if style is not None and pull.style != style:
            continue
        if finish is not None and pull.finish != finish:
            continue
        if mount_style is not None and pull.mount_style is not mount_style:
            continue
        if brand is not None and pull.brand != brand:
            continue
        matches.append((key, pull))
    return matches
