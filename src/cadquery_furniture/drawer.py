"""
Parametric drawer box generator.

Builds drawer boxes sized to fit cabinet openings with proper hardware clearances.
Supports dovetail-style (sides overlap front/back) and butt-joint construction.

All dimensions in millimeters. Drawer orientation:
- X axis: width (left to right)
- Y axis: depth (front to back)
- Z axis: height (bottom to top)
- Origin at front-bottom-left exterior corner
"""

from dataclasses import dataclass, field
from typing import Optional

try:
    import cadquery as cq
except ImportError:
    cq = None

from .hardware import DrawerSlideSpec, get_slide, get_pull
from .cabinet import CabinetConfig, PartInfo
from .joinery import (
    DrawerJoineryStyle,
    DrawerJoinerySpec,
    drawer_joinery_spec,
    apply_drawer_joinery_to_side,
    apply_drawer_joinery_to_front_back,
)
from .pulls import PullPlacement, VerticalPolicy, pull_positions


# ─── Standard drawer box heights ──────────────────────────────────────────────
# Industry-standard box heights in mm (3"–12" in 1" increments).
# Manufacturers (Eagle Woodworking, Drawer Connection, etc.) stock these sizes
# natively, making batch ordering and interchangeable spares straightforward.
STANDARD_BOX_HEIGHTS: tuple[float, ...] = (
    76.0,   # 3"
    102.0,  # 4"
    127.0,  # 5"
    152.0,  # 6"
    178.0,  # 7"
    203.0,  # 8"
    229.0,  # 9"
    254.0,  # 10"
    279.0,  # 11"
    305.0,  # 12"
)


def snap_to_standard_box_height(raw_mm: float) -> float:
    """Return the largest standard box height that fits within *raw_mm*.

    If *raw_mm* is smaller than the smallest standard height (76 mm / 3"),
    return *raw_mm* unchanged so callers never get a negative or zero result.

    Examples
    --------
    >>> snap_to_standard_box_height(135)   # fits a 5" (127 mm) box
    127.0
    >>> snap_to_standard_box_height(102)   # exactly 4" — stays 4"
    102.0
    >>> snap_to_standard_box_height(60)    # below minimum — pass through
    60.0
    """
    best = None
    for h in STANDARD_BOX_HEIGHTS:
        if h <= raw_mm:
            best = h
    return best if best is not None else raw_mm


@dataclass
class DrawerConfig:
    """Configuration for a single drawer box."""

    # Opening dimensions (from cabinet)
    opening_width: float  # between cabinet sides
    opening_height: float  # vertical space for this drawer
    opening_depth: float  # from cabinet front to back panel

    # Materials
    side_thickness: float = 15.0  # 5/8" for drawer sides
    front_back_thickness: float = 15.0  # 5/8" for sub-front and back
    bottom_thickness: float = 6.0  # 1/4" plywood

    # Joinery for bottom panel
    bottom_dado_depth: float = 6.0  # how deep the dado is cut
    bottom_dado_inset: float = 12.0  # distance from bottom edge to dado bottom

    # Gaps / reveals
    front_gap: float = 2.0  # gap between drawer box front and cabinet face
    vertical_gap: float = 12.0  # clearance above drawer box

    # Hardware
    slide_key: str = "blum_tandem_550h"

    # Corner joinery style
    joinery_style: DrawerJoineryStyle = DrawerJoineryStyle.HALF_LAP

    # Height snapping: when True, box_height snaps down to the nearest standard
    # size (see STANDARD_BOX_HEIGHTS) so orders can be batched by common heights.
    # Set to False to use the full computed clearance-adjusted height instead.
    use_standard_height: bool = True

    # Drawer face (applied face, not the sub-front)
    applied_face: bool = True
    face_overlay_sides: float = 10.0  # how much face overlaps opening per side
    face_overlay_top: float = 3.0
    face_overlay_bottom: float = 3.0
    face_thickness: float = 18.0  # 3/4"

    # Pull hardware (optional).  ``pull_key`` is a key into the PULLS registry
    # (see ``hardware.PULLS`` / ``cadquery_furniture/data/pulls_catalog.json``).
    # When ``None``, no pull is placed on the drawer face and the BOM omits it.
    # ``pull_count`` of 0 defers to :func:`pulls.recommend_pull_count` (1 for
    # knobs/flush; 1 if face_width ≤ 762 mm (30″), else 2 for surface/edge pulls).
    # ``pull_vertical`` controls the height at which the pull centres sit —
    # ``"center"`` (default), ``"upper_third"``, or ``"lower_third"``.
    pull_key: Optional[str] = None
    pull_count: int = 0
    pull_vertical: VerticalPolicy = "center"

    @property
    def slide(self) -> DrawerSlideSpec:
        return get_slide(self.slide_key)

    @property
    def joinery(self) -> DrawerJoinerySpec:
        """Computed corner-joint dimensions for the selected joinery style."""
        return drawer_joinery_spec(
            self.joinery_style, self.side_thickness, self.front_back_thickness
        )

    @property
    def box_width(self) -> float:
        """Drawer box width (exterior)."""
        return self.opening_width - (self.slide.nominal_side_clearance * 2)

    @property
    def box_height(self) -> float:
        """Drawer box height (exterior).

        When ``use_standard_height`` is True (default), the raw computed height
        is snapped *down* to the nearest value in ``STANDARD_BOX_HEIGHTS`` so
        that box orders can be batched by a small set of common sizes.  The
        remaining clearance is absorbed into the vertical gap above the box.
        """
        raw = self.opening_height - self.slide.min_bottom_clearance - self.vertical_gap
        if self.use_standard_height:
            return snap_to_standard_box_height(raw)
        return raw

    @property
    def standard_box_height(self) -> float:
        """Always returns the snapped standard height regardless of use_standard_height."""
        raw = self.opening_height - self.slide.min_bottom_clearance - self.vertical_gap
        return snap_to_standard_box_height(raw)

    @property
    def box_depth(self) -> float:
        """Drawer box depth (front to back, exterior)."""
        slide_length = self.slide.slide_length_for_depth(self.opening_depth)
        return min(
            self.opening_depth - self.front_gap,
            slide_length,
        )

    @property
    def bottom_panel_width(self) -> float:
        """Bottom panel width — fits in dados on both sides."""
        return self.box_width - (self.side_thickness * 2) + (self.bottom_dado_depth * 2)

    @property
    def bottom_panel_depth(self) -> float:
        """Bottom panel depth — fits in dados in front and back."""
        return self.box_depth - (self.front_back_thickness * 2) + (self.bottom_dado_depth * 2)

    @property
    def face_width(self) -> float:
        """Applied drawer face width."""
        return self.opening_width + (self.face_overlay_sides * 2)

    @property
    def face_height(self) -> float:
        """Applied drawer face height."""
        return self.opening_height + self.face_overlay_top + self.face_overlay_bottom

    @property
    def pull_placements(self) -> list[PullPlacement]:
        """Pull placements on the applied drawer face, in face-local coords.

        Returns an empty list when ``pull_key`` is ``None`` or the drawer has
        no applied face (``applied_face=False``) — there is nowhere to mount
        a pull in either case.  Otherwise resolves the catalog entry and
        delegates to :func:`pulls.pull_positions`.
        """
        if self.pull_key is None or not self.applied_face:
            return []
        pull = get_pull(self.pull_key)
        return pull_positions(
            self.face_width,
            self.face_height,
            pull,
            self.pull_key,
            count=self.pull_count,
            vertical=self.pull_vertical,
        )


def _require_cq():
    if cq is None:
        raise ImportError("cadquery is required. Install with: pip install cadquery")


def make_drawer_side(cfg: DrawerConfig, side: str = "left") -> "cq.Workplane":
    """Create a drawer side panel with bottom dado and corner joinery cuts.

    ``side`` is ``"left"`` or ``"right"`` and determines which face the bottom
    dado and corner joinery are cut into so they end up on the *inside* face
    once the panel is placed in the assembly.
    """
    _require_cq()

    if side not in ("left", "right"):
        raise ValueError(f"side must be 'left' or 'right', got {side!r}")

    panel = (
        cq.Workplane("XY")
        .box(cfg.side_thickness, cfg.box_depth, cfg.box_height, centered=False)
    )

    dado_x = (cfg.side_thickness - cfg.bottom_dado_depth) if side == "left" else 0.0
    dado = (
        cq.Workplane("XY")
        .transformed(offset=(dado_x, 0, cfg.bottom_dado_inset))
        .box(cfg.bottom_dado_depth, cfg.box_depth, cfg.bottom_thickness, centered=False)
    )
    panel = panel.cut(dado)

    panel = apply_drawer_joinery_to_side(
        panel, cfg.joinery, cfg.box_depth, cfg.box_height, side=side
    )

    return panel


def make_drawer_front_back(cfg: DrawerConfig, position: str = "back") -> "cq.Workplane":
    """Create a drawer sub-front or back panel with the bottom dado.

    ``position`` is ``"front"`` (sub-front) or ``"back"``; it controls which
    face the bottom dado is cut into so it ends up on the *inside* of the
    assembled drawer.

    The panel width is ``box_width − 2 × (side_thickness − engagement_x)`` so
    each end overhangs the carcass interior by ``engagement_x`` to seat in the
    side panel's rabbet (zero overhang for BUTT, ``side_dado_depth_x`` for
    QQQ / HALF_LAP / DRAWER_LOCK).
    """
    _require_cq()

    if position not in ("front", "back"):
        raise ValueError(f"position must be 'front' or 'back', got {position!r}")

    engagement_x = cfg.joinery.engagement_x
    interior_width = cfg.box_width - 2 * (cfg.side_thickness - engagement_x)

    panel = (
        cq.Workplane("XY")
        .box(interior_width, cfg.front_back_thickness, cfg.box_height, centered=False)
    )

    dado_y = 0.0 if position == "back" else (cfg.front_back_thickness - cfg.bottom_dado_depth)
    dado = (
        cq.Workplane("XY")
        .transformed(offset=(0, dado_y, cfg.bottom_dado_inset))
        .box(interior_width, cfg.bottom_dado_depth, cfg.bottom_thickness, centered=False)
    )
    panel = panel.cut(dado)

    panel = apply_drawer_joinery_to_front_back(
        panel, cfg.joinery, interior_width, cfg.box_height, position=position
    )

    return panel


def make_drawer_bottom(cfg: DrawerConfig) -> "cq.Workplane":
    """Create the drawer bottom panel."""
    _require_cq()
    return (
        cq.Workplane("XY")
        .box(cfg.bottom_panel_width, cfg.bottom_panel_depth, cfg.bottom_thickness, centered=False)
    )


def make_drawer_face(cfg: DrawerConfig) -> "cq.Workplane":
    """Create an applied drawer face."""
    _require_cq()
    return (
        cq.Workplane("XY")
        .box(cfg.face_width, cfg.face_thickness, cfg.face_height, centered=False)
    )


def build_drawer(cfg: DrawerConfig) -> tuple["cq.Assembly", list[PartInfo]]:
    """Build a complete drawer box assembly.

    Returns:
        Tuple of (cq.Assembly, list of PartInfo for BOM/cutlist).
    """
    _require_cq()

    parts: list[PartInfo] = []

    # ── Build parts ──────────────────────────────────────────────────────
    left_side = make_drawer_side(cfg, side="left")
    right_side = make_drawer_side(cfg, side="right")
    sub_front = make_drawer_front_back(cfg, position="front")
    back = make_drawer_front_back(cfg, position="back")
    bottom = make_drawer_bottom(cfg)

    parts.append(PartInfo(
        name="drawer_side_L", shape=left_side,
        material_thickness=cfg.side_thickness,
        grain_direction="length",
    ))
    parts.append(PartInfo(
        name="drawer_side_R", shape=right_side,
        material_thickness=cfg.side_thickness,
        grain_direction="length",
    ))
    parts.append(PartInfo(
        name="drawer_sub_front", shape=sub_front,
        material_thickness=cfg.front_back_thickness,
        grain_direction="width",
    ))
    parts.append(PartInfo(
        name="drawer_back", shape=back,
        material_thickness=cfg.front_back_thickness,
        grain_direction="width",
    ))
    parts.append(PartInfo(
        name="drawer_bottom", shape=bottom,
        material_thickness=cfg.bottom_thickness,
        grain_direction="width",
        notes="1/4 inch plywood",
    ))

    if cfg.applied_face:
        face = make_drawer_face(cfg)
        parts.append(PartInfo(
            name="drawer_face", shape=face,
            material_thickness=cfg.face_thickness,
            grain_direction="width",
            edge_band=["all"],
        ))

    # ── Assembly ─────────────────────────────────────────────────────────
    assy = cq.Assembly(name="drawer_box")

    COL_SIDE   = cq.Color(0.90, 0.76, 0.50, 1.0)   # warm honey maple — sides
    COL_FB     = cq.Color(0.96, 0.91, 0.76, 1.0)   # light ash cream  — front/back
    COL_BOTTOM = cq.Color(0.60, 0.46, 0.28, 1.0)   # dark ply brown   — bottom

    assy.add(left_side, name="side_L", loc=cq.Location((0, 0, 0)), color=COL_SIDE)

    assy.add(right_side, name="side_R",
             loc=cq.Location((cfg.box_width - cfg.side_thickness, 0, 0)),
             color=COL_SIDE)

    # Sub-front and back: each end seats into the side panel's rabbet.
    # x-offset reduced by engagement_x (= 0 for BUTT, side_dado_depth_x otherwise).
    fb_x = cfg.side_thickness - cfg.joinery.engagement_x

    assy.add(sub_front, name="sub_front", loc=cq.Location((fb_x, 0, 0)), color=COL_FB)

    assy.add(back, name="back",
             loc=cq.Location((fb_x, cfg.box_depth - cfg.front_back_thickness, 0)),
             color=COL_FB)

    # Bottom panel captured in dados
    bottom_x = cfg.side_thickness - cfg.bottom_dado_depth
    bottom_y = cfg.front_back_thickness - cfg.bottom_dado_depth
    bottom_z = cfg.bottom_dado_inset
    assy.add(bottom, name="bottom",
             loc=cq.Location((bottom_x, bottom_y, bottom_z)),
             color=COL_BOTTOM)

    # Applied face
    if cfg.applied_face:
        face = make_drawer_face(cfg)
        face_x = -(cfg.face_overlay_sides + cfg.slide.nominal_side_clearance)
        face_y = -cfg.face_thickness
        face_z = -cfg.face_overlay_bottom
        assy.add(face, name="face",
                 loc=cq.Location((face_x, face_y, face_z)),
                 color=cq.Color(0.65, 0.45, 0.28, 1.0))

    return assy, parts


def drawers_from_cabinet_config(cab_cfg: CabinetConfig) -> list[tuple["cq.Assembly", list[PartInfo], float]]:
    """Generate drawer assemblies from a cabinet's drawer_config.

    Returns:
        List of (drawer_assembly, parts, z_position) tuples.
    """
    if not cab_cfg.openings:
        return []

    drawers = []
    # Start stacking from the bottom panel
    current_z = cab_cfg.bottom_thickness

    for op in cab_cfg.openings:
        opening_height = op.height_mm
        if op.opening_type == "drawer":
            dcfg = DrawerConfig(
                opening_width=cab_cfg.interior_width,
                opening_height=opening_height,
                opening_depth=cab_cfg.interior_depth,
                slide_key=cab_cfg.drawer_slide,
                pull_key=cab_cfg.drawer_pull,
            )
            drawer_assy, drawer_parts = build_drawer(dcfg)

            # Position within cabinet: centered in opening with slide clearance
            drawer_x = cab_cfg.side_thickness + dcfg.slide.nominal_side_clearance
            drawer_y = dcfg.front_gap
            drawer_z = current_z

            drawers.append((drawer_assy, drawer_parts, drawer_z))

        current_z += opening_height

    return drawers
