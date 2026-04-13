"""
Parametric door generator for frameless (Euro-style) cabinets.

Supports three Blum Clip Top overlay types:
  Full overlay  — door overlaps the cabinet side by 16 mm per edge (most common)
  Half overlay  — 9.5 mm overlap for shared partitions between adjacent cabinets
  Inset         — door sits inside the opening with a reveal gap on all sides

Hinge cup borings (35 mm diameter, 13 mm deep, 22.5 mm from door edge) are cut
into the door model when CadQuery is available.

All dimensions in millimeters.  Door orientation:
  X axis : width (left to right)
  Y axis : thickness (front = y=0, back = y=door_thickness)
  Z axis : height (bottom to top)
  Origin : front-bottom-left exterior corner of the door panel
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

try:
    import cadquery as cq
except ImportError:
    cq = None

from .hardware import HingeSpec, OverlayType, get_hinge
from .cabinet import CabinetConfig, PartInfo


@dataclass
class DoorConfig:
    """Configuration for one or two doors covering a single cabinet opening.

    Parameters
    ----------
    opening_width :
        Interior opening width (between the two cabinet side panels, in mm).
    opening_height :
        Vertical height of the opening being covered (mm).
    num_doors :
        1 = single door; 2 = a pair of doors side-by-side.
    hinge_key :
        Key into the HINGES dict — selects overlay type and soft-close variant.
    door_thickness :
        Door panel thickness (mm).  Typical: 18 mm (3/4″).
    door_weight_kg :
        Estimated door weight used for hinge-count calculation (kg).
        Default 0 lets the count be driven by height alone.
    gap_top, gap_bottom :
        Clearance between door top/bottom and adjacent shelf or cabinet edge.
        Ignored for full/half overlay (door face sits proud of the opening).
    gap_side :
        Side reveal for *inset* doors only (applied to each side).
    gap_between :
        Gap between the two door panels in a *pair*.  Applied symmetrically
        so each door loses gap_between/2 from its inner edge.
    """

    # Opening / structural dimensions
    opening_width: float
    opening_height: float

    # Door arrangement
    num_doors: int = 1

    # Hardware
    hinge_key: str = "blum_clip_top_110_full"

    # Materials
    door_thickness: float = 18.0

    # Weight (for hinge count)
    door_weight_kg: float = 0.0

    # Gaps / reveals
    gap_top: float = 2.0
    gap_bottom: float = 2.0
    gap_side: float = 2.0       # inset only — each side
    gap_between: float = 2.0    # pairs only

    # ── Computed properties ───────────────────────────────────────────────

    @property
    def hinge(self) -> HingeSpec:
        """Return the hinge specification."""
        return get_hinge(self.hinge_key)

    @property
    def door_width(self) -> float:
        """Width of *each* door panel (mm).

        Full / Half overlay
        -------------------
        The door covers the opening *and* overlaps the cabinet sides:
          single : opening_width + 2 × overlay
          pair   : (opening_width + gap_between) / 2 + overlay − gap_between / 2
                 = opening_width / 2 + overlay

        Inset
        -----
        Door sits inside the opening with a gap on each side:
          single : opening_width − 2 × gap_side
          pair   : (opening_width − gap_between) / 2 − gap_side
        """
        ov = self.hinge.overlay
        if self.hinge.overlay_type == OverlayType.INSET:
            if self.num_doors == 1:
                return self.opening_width - (2 * self.gap_side)
            else:
                return (self.opening_width - self.gap_between) / 2 - self.gap_side
        else:
            # Full or half overlay
            if self.num_doors == 1:
                return self.opening_width + (2 * ov)
            else:
                # Each door: half the opening + outer overlay - half the center gap
                return self.opening_width / 2 + ov - self.gap_between / 2

    @property
    def door_height(self) -> float:
        """Height of each door panel (mm).

        Full / Half overlay — no top/bottom gap formula needed because the door
        face sits in front of the opening; standard practice is to subtract a
        nominal 4 mm (2 mm per edge) for expansion and reveal.

        Inset — door must clear the opening: subtract gap_top and gap_bottom.
        """
        if self.hinge.overlay_type == OverlayType.INSET:
            return self.opening_height - self.gap_top - self.gap_bottom
        else:
            # Full/half overlay: 2 mm gap at each end is built into the reveal
            return self.opening_height - self.gap_top - self.gap_bottom

    @property
    def hinge_count(self) -> int:
        """Number of hinges on each door panel."""
        return self.hinge.hinges_for_height(self.door_height, self.door_weight_kg)

    @property
    def hinge_positions_z(self) -> list[float]:
        """Z-positions (from door bottom) for each hinge centre on the door."""
        return self.hinge.hinge_positions(self.door_height, self.door_weight_kg)

    @property
    def total_hinge_count(self) -> int:
        """Total hinges needed across *all* doors in this DoorConfig."""
        return self.hinge_count * self.num_doors


# ─── CadQuery helpers ─────────────────────────────────────────────────────────


def _require_cq() -> None:
    if cq is None:
        raise ImportError("cadquery is required for 3D modeling. Install with: pip install cadquery")


def make_door_panel(cfg: DoorConfig) -> "cq.Workplane":
    """Create a door panel with hinge cup borings.

    The cup borings are drilled from the *back* face of the door (y = door_thickness)
    with centres at x = cup_boring_distance from the *hinge side* (x = 0) and z
    positions given by ``cfg.hinge_positions_z``.

    Returns a CadQuery Workplane representing the door solid.
    """
    _require_cq()

    h = cfg.hinge
    w = cfg.door_width
    ht = cfg.door_height
    t = cfg.door_thickness

    # Solid door panel
    panel = cq.Workplane("XY").box(w, t, ht, centered=False)

    # Cup borings from the back face of the door (y = t)
    cup_r = h.cup_diameter / 2
    cup_depth = h.cup_depth
    boring_x = h.cup_boring_distance  # from hinge-side edge

    for z_pos in cfg.hinge_positions_z:
        cup = (
            cq.Workplane("YZ")
            .transformed(offset=(t, boring_x, z_pos))
            # Drill in the –Y direction (into the door back face)
            .cylinder(cup_depth, cup_r, centered=(True, True, False))
        )
        panel = panel.cut(cup)

    return panel


def build_door(cfg: DoorConfig) -> tuple["cq.Assembly", list[PartInfo]]:
    """Build a single door assembly (one panel with PartInfo).

    Returns:
        (cq.Assembly, [PartInfo])
    """
    _require_cq()

    panel = make_door_panel(cfg)

    parts = [
        PartInfo(
            name="door",
            shape=panel,
            material_thickness=cfg.door_thickness,
            grain_direction="length",   # grain runs vertically (height direction)
            edge_band=["all"],          # all four edges typically banded on finished doors
        )
    ]

    assy = cq.Assembly(name="door")
    assy.add(panel, name="door", loc=cq.Location((0, 0, 0)),
             color=cq.Color(0.55, 0.38, 0.22, 1.0))

    return assy, parts


def build_door_pair(cfg: DoorConfig) -> tuple["cq.Assembly", list[PartInfo]]:
    """Build a matched door pair assembly (two panels positioned side by side).

    Left door hinge side is at x=0; right door hinge side is at the far right
    of the opening.  The gap_between gap is maintained at the centre.

    Returns:
        (cq.Assembly, [PartInfo for left, PartInfo for right])
    """
    if cfg.num_doors != 2:
        raise ValueError("build_door_pair requires num_doors=2")
    _require_cq()

    panel = make_door_panel(cfg)
    dw = cfg.door_width
    ov = cfg.hinge.overlay
    gap = cfg.gap_between

    parts = [
        PartInfo(
            name="door_left",
            shape=panel,
            material_thickness=cfg.door_thickness,
            grain_direction="length",
            edge_band=["all"],
        ),
        PartInfo(
            name="door_right",
            shape=panel,
            material_thickness=cfg.door_thickness,
            grain_direction="length",
            edge_band=["all"],
        ),
    ]

    assy = cq.Assembly(name="door_pair")

    # Left door: hinge on left, door face at y=0
    left_x = -ov  # left edge starts overlay amount to the left of the opening
    assy.add(panel, name="door_left",
             loc=cq.Location((left_x, 0, 0)),
             color=cq.Color(0.55, 0.38, 0.22, 1.0))

    # Right door: mirrored.  Its right edge extends overlay past the right side.
    # Right door left edge = left_x + dw + gap
    right_x = left_x + dw + gap
    assy.add(panel, name="door_right",
             loc=cq.Location((right_x, 0, 0)),
             color=cq.Color(0.55, 0.38, 0.22, 1.0))

    return assy, parts


# ─── Cabinet-level door generation ───────────────────────────────────────────


def doors_from_cabinet_config(
    cab_cfg: CabinetConfig,
) -> list[tuple["cq.Assembly", list[PartInfo], float]]:
    """Generate door assemblies from a cabinet's drawer_config.

    Entries whose slot_type is ``"door"`` get a single door; ``"door_pair"``
    gets a matched pair.  Other slot types (drawer, shelf, open) are skipped.

    Returns:
        List of (assembly, parts, z_bottom_of_opening) tuples.
    """
    if not cab_cfg.drawer_config:
        return []

    doors = []
    current_z = cab_cfg.bottom_thickness

    for opening_height, slot_type in cab_cfg.drawer_config:
        if slot_type in ("door", "door_pair"):
            num_doors = 2 if slot_type == "door_pair" else 1
            dcfg = DoorConfig(
                opening_width=cab_cfg.interior_width,
                opening_height=opening_height,
                num_doors=num_doors,
                hinge_key=getattr(cab_cfg, "door_hinge", "blum_clip_top_110_full"),
            )
            if num_doors == 1:
                assy, parts = build_door(dcfg)
            else:
                assy, parts = build_door_pair(dcfg)
            doors.append((assy, parts, current_z))

        current_z += opening_height

    return doors
