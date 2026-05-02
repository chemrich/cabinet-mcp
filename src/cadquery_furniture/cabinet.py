"""
Parametric base cabinet model.

Generates a frameless (Euro-style) base cabinet with:
- Two side panels with dados for shelves and rabbet for back
- Bottom panel in dados
- Fixed shelves in dados
- Back panel in rabbets
- Optional adjustable shelf pin holes (32mm system)

All dimensions in millimeters. The cabinet is oriented with:
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
    cq = None  # allow import for type checking / planning without cadquery installed

from .hardware import DrawerSlideSpec, get_slide, LegSpec, get_leg, get_pull, MountStyle
from .pulls import HingeSide, door_pull_x_center
from .joinery import (
    CarcassJoinery,
    DominoSpec,
    PocketScrewSpec,
    BiscuitSpec,
    DownelSpec,
    DEFAULT_DOMINO,
    DEFAULT_POCKET_SCREW,
    DEFAULT_BISCUIT,
    DEFAULT_DOWEL,
)


@dataclass(frozen=True)
class OpeningConfig:
    """One opening (a single face-height zone) within a column stack.

    ``height_mm`` is the vertical space allocated to this opening.
    ``opening_type`` describes what fills it:
      "drawer"    — a drawer box on slides
      "door"      — a single swinging door
      "door_pair" — a matched pair of doors side-by-side
      "shelf"     — a fixed shelf
      "open"      — open compartment (no door/drawer)

    The optional override fields (all default to ``None``) let individual
    openings deviate from the cabinet-level defaults.  ``None`` means
    "inherit from the column or cabinet config".
    """
    height_mm: float
    opening_type: str
    hinge_key:      Optional[str]   = None
    hinge_side:     Optional[str]   = None   # "left" | "right"
    pull_key:       Optional[str]   = None
    num_doors:      Optional[int]   = None   # 1 or 2; only for door types
    door_thickness: Optional[float] = None


@dataclass(frozen=True)
class ColumnConfig:
    """One vertical column within a single cabinet carcass.

    A cabinet may have multiple side-by-side columns separated by interior
    vertical dividers — e.g. a left column of three drawers next to a right
    column with a single door.

    ``width_mm`` is the **interior** width of the column opening (not
    including adjacent divider panel thickness).  The sum of all column
    widths plus ``(n_columns − 1) × side_thickness`` must equal the
    cabinet's ``interior_width``; the evaluator enforces this.
    """
    width_mm: float
    openings: tuple[OpeningConfig, ...]  # stacked bottom-to-top


@dataclass
class CabinetConfig:
    """Configuration for a base cabinet."""

    # Overall exterior dimensions
    width: float = 600.0
    height: float = 720.0
    depth: float = 550.0

    # Materials
    side_thickness: float = 18.0  # 3/4" Baltic birch
    bottom_thickness: float = 18.0
    top_thickness: float = 18.0
    shelf_thickness: float = 18.0
    back_thickness: float = 6.0  # 1/4" plywood

    # Joinery
    dado_depth: float = 9.0  # half thickness dado for shelves/bottom
    back_rabbet_width: float = 9.0  # rabbet width for back panel
    back_rabbet_depth: float = 6.0  # matches back_thickness

    # Shelves
    fixed_shelf_positions: list[float] = field(default_factory=list)
    # Heights from cabinet bottom (exterior) to shelf bottom

    # Adjustable shelves (32mm system)
    adj_shelf_holes: bool = False
    shelf_pin_diameter: float = 5.0
    shelf_pin_depth: float = 10.0
    shelf_pin_row_inset: float = 37.0  # from front and back edges
    shelf_pin_start_z: float = 80.0  # first hole height from bottom
    shelf_pin_end_z: float = 640.0  # last hole height from bottom
    shelf_pin_spacing: float = 32.0  # 32mm system

    # Opening stack (from bottom up).  Used in single-column mode.
    # When ``columns`` is non-empty this field is ignored; each ColumnConfig
    # carries its own stack.
    openings: list[OpeningConfig] = field(default_factory=list)

    # Multi-column layout.  When non-empty, the cabinet interior is divided into
    # side-by-side vertical columns by interior dividers.
    # Column widths must sum to ``interior_width``; the evaluator checks this.
    columns: list[ColumnConfig] = field(default_factory=list)

    drawer_slide: str = "blum_tandem_550h"

    # Door hardware
    door_hinge: str = "blum_clip_top_110_full"

    # Pull hardware (optional defaults).  These keys propagate down to drawers
    # and doors generated from this cabinet via ``drawers_from_cabinet_config``
    # and ``doors_from_cabinet_config`` — i.e. every drawer in this carcass
    # gets ``drawer_pull`` and every door gets ``door_pull`` unless the per-
    # drawer / per-door config overrides it.  ``None`` means no pull.
    drawer_pull: Optional[str] = None
    door_pull: Optional[str] = None
    door_hinge_side: HingeSide = "left"    # hinge side for single doors
    door_pull_inset_mm: float = 50.0       # gap from latch edge to pull body near-end

    # Leg / foot hardware (used by build_multi_bay_cabinet and design_legs)
    leg_key: str = "richelieu_176138106"
    leg_count: int = 4
    leg_inset: float = 30.0  # foot centre inset from cabinet edge (mm)

    # Carcass joinery method
    carcass_joinery: CarcassJoinery = CarcassJoinery.FLOATING_TENON

    # Per-method joinery specs (used when the matching joinery method is selected)
    domino_spec: DominoSpec = field(default_factory=lambda: DEFAULT_DOMINO)
    pocket_screw_spec: PocketScrewSpec = field(default_factory=lambda: DEFAULT_POCKET_SCREW)
    biscuit_spec: BiscuitSpec = field(default_factory=lambda: DEFAULT_BISCUIT)
    dowel_spec: DownelSpec = field(default_factory=lambda: DEFAULT_DOWEL)

    def __post_init__(self) -> None:
        """Normalize openings and column openings to OpeningConfig objects."""
        self.openings = [
            op if isinstance(op, OpeningConfig)
            else OpeningConfig(height_mm=float(op[0]), opening_type=str(op[1]))
            for op in self.openings
        ]
        normalized_cols = []
        for col in self.columns:
            if col.openings and not isinstance(col.openings[0], OpeningConfig):
                normalized_cols.append(ColumnConfig(
                    width_mm=col.width_mm,
                    openings=tuple(
                        OpeningConfig(height_mm=float(op[0]), opening_type=str(op[1]))
                        for op in col.openings
                    ),
                ))
            else:
                normalized_cols.append(col)
        self.columns = normalized_cols

    # Derived / computed
    @property
    def interior_width(self) -> float:
        """Width between side panels."""
        return self.width - (self.side_thickness * 2)

    @property
    def interior_depth(self) -> float:
        """Depth from front edge to back panel face."""
        return self.depth - self.back_rabbet_width

    @property
    def interior_height(self) -> float:
        """Height from top of bottom panel to underside of top panel."""
        return self.height - self.bottom_thickness - self.top_thickness

    @property
    def back_panel_width(self) -> float:
        """Back panel fits in rabbets on both sides."""
        return self.width - (self.side_thickness - self.back_rabbet_depth) * 2

    @property
    def back_panel_height(self) -> float:
        """Back panel height — spans from carcass floor to underside of top panel."""
        return self.height - self.top_thickness


def _require_cq():
    if cq is None:
        raise ImportError(
            "cadquery is required for 3D modeling. Install with: pip install cadquery"
        )


def make_side_panel(cfg: CabinetConfig, mirror: bool = False) -> "cq.Workplane":
    """Create a side panel with dados for bottom/shelves and rabbet for back.

    Args:
        cfg: Cabinet configuration.
        mirror: If True, mirror joinery for the right side panel.
    """
    _require_cq()

    # Start with a solid panel
    panel = (
        cq.Workplane("XY")
        .box(cfg.side_thickness, cfg.depth, cfg.height, centered=False)
    )

    # Cut rabbet for back panel along the back edge.
    # The rabbet runs the full height on the inside-back edge.
    # Left panel (mirror=False): interior face at x=side_thickness; rabbet cut from
    # x = side_thickness - back_rabbet_depth.
    # Right panel (mirror=True): interior face at x=0; rabbet cut starts at x=0.
    rabbet = (
        cq.Workplane("XY")
        .transformed(offset=(
            cfg.side_thickness - cfg.back_rabbet_depth if not mirror else 0,
            cfg.depth - cfg.back_rabbet_width,
            0,
        ))
        .box(cfg.back_rabbet_depth, cfg.back_rabbet_width, cfg.height, centered=False)
    )
    panel = panel.cut(rabbet)

    # Cut dado for bottom panel.
    # Left panel (mirror=False): interior face is at local x=side_thickness,
    # so the dado must start at x = side_thickness - dado_depth.
    # Right panel (mirror=True): interior face is at local x=0, dado starts at x=0.
    dado_x = cfg.side_thickness - cfg.dado_depth if not mirror else 0
    bottom_dado = (
        cq.Workplane("XY")
        .transformed(offset=(dado_x, 0, 0))
        .box(cfg.dado_depth, cfg.depth - cfg.back_rabbet_width, cfg.bottom_thickness, centered=False)
    )
    panel = panel.cut(bottom_dado)

    # Cut dado for top panel — extends full depth so the top panel (which runs
    # to the back exterior) seats flush in the dado along its entire length.
    top_dado = (
        cq.Workplane("XY")
        .transformed(offset=(dado_x, 0, cfg.height - cfg.top_thickness))
        .box(cfg.dado_depth, cfg.depth, cfg.top_thickness, centered=False)
    )
    panel = panel.cut(top_dado)

    # Cut dados for fixed shelves
    for shelf_z in cfg.fixed_shelf_positions:
        shelf_dado = (
            cq.Workplane("XY")
            .transformed(offset=(dado_x, 0, shelf_z))
            .box(cfg.dado_depth, cfg.depth - cfg.back_rabbet_width, cfg.shelf_thickness, centered=False)
        )
        panel = panel.cut(shelf_dado)

    # Drill shelf pin holes (32mm system).
    # Holes bore horizontally from the interior face (X direction), so the
    # workplane must be YZ (normal = X). x_start is the global X where the
    # bore begins; the cylinder extends shelf_pin_depth toward the exterior.
    if cfg.adj_shelf_holes:
        x_start = (cfg.side_thickness - cfg.shelf_pin_depth) if not mirror else 0
        z = cfg.shelf_pin_start_z
        while z <= cfg.shelf_pin_end_z:
            for y_inset in [cfg.shelf_pin_row_inset, cfg.depth - cfg.back_rabbet_width - cfg.shelf_pin_row_inset]:
                pin_hole = (
                    cq.Workplane("YZ")
                    .transformed(offset=(y_inset, z, x_start))
                    .cylinder(
                        cfg.shelf_pin_depth,
                        cfg.shelf_pin_diameter / 2,
                        centered=(True, True, False),
                    )
                )
                panel = panel.cut(pin_hole)
            z += cfg.shelf_pin_spacing

    return panel


def make_bottom_panel(cfg: CabinetConfig) -> "cq.Workplane":
    """Create the bottom panel. Sits in dados on both sides."""
    _require_cq()
    # Width: interior width + dado depth on each side (panel extends into dados)
    panel_width = cfg.interior_width + (cfg.dado_depth * 2)
    panel_depth = cfg.depth - cfg.back_rabbet_width

    return (
        cq.Workplane("XY")
        .box(panel_width, panel_depth, cfg.bottom_thickness, centered=False)
    )


def make_top_panel(cfg: CabinetConfig) -> "cq.Workplane":
    """Create the top panel. Sits in dados at the top of both side panels.

    Extends to the full cabinet depth so the top surface is flush with the
    back face of the side panels. The back panel stops at the underside of
    this panel (back_panel_height = height - top_thickness).
    """
    _require_cq()
    panel_width = cfg.interior_width + (cfg.dado_depth * 2)

    return (
        cq.Workplane("XY")
        .box(panel_width, cfg.depth, cfg.top_thickness, centered=False)
    )


def make_shelf(cfg: CabinetConfig) -> "cq.Workplane":
    """Create a fixed shelf panel. Same dimensions as bottom."""
    _require_cq()
    panel_width = cfg.interior_width + (cfg.dado_depth * 2)
    panel_depth = cfg.depth - cfg.back_rabbet_width

    return (
        cq.Workplane("XY")
        .box(panel_width, panel_depth, cfg.shelf_thickness, centered=False)
    )


def make_back_panel(cfg: CabinetConfig) -> "cq.Workplane":
    """Create the back panel. Sits in rabbets on both sides."""
    _require_cq()
    return (
        cq.Workplane("XY")
        .box(cfg.back_panel_width, cfg.back_thickness, cfg.back_panel_height, centered=False)
    )


def make_interior_divider(
    cfg: CabinetConfig,
    height_override: Optional[float] = None,
) -> "cq.Workplane":
    """Create an interior vertical divider for multi-bay assemblies.

    Unlike a standard side panel, the divider:
    - Stops at ``depth - back_rabbet_width`` (flush with the back panel's front
      face — does not extend into the back rabbet zone).
    - Has dados for the bottom panel on *both* interior faces so adjacent bay
      horizontal panels are properly supported.
    - Has no back rabbet (the continuous back panel covers the back).

    ``height_override`` clips the divider to a shorter height (e.g. the top of
    the drawer zone in an armoire so the upper door section stays open).  When
    clipped, only bottom dados are cut; no top dados are added.
    """
    _require_cq()
    panel_depth = cfg.depth - cfg.back_rabbet_width
    height      = height_override if height_override is not None else cfg.height

    panel = cq.Workplane("XY").box(cfg.side_thickness, panel_depth, height, centered=False)

    # Bottom dado — left face (x = 0 side, facing the bay to the left)
    panel = panel.cut(
        cq.Workplane("XY")
        .transformed(offset=(0, 0, 0))
        .box(cfg.dado_depth, panel_depth, cfg.bottom_thickness, centered=False)
    )
    # Bottom dado — right face (x = side_thickness side, facing the bay to the right)
    panel = panel.cut(
        cq.Workplane("XY")
        .transformed(offset=(cfg.side_thickness - cfg.dado_depth, 0, 0))
        .box(cfg.dado_depth, panel_depth, cfg.bottom_thickness, centered=False)
    )
    if height_override is None:
        # Top dado — left face (full panel depth to receive the full-depth top panel)
        panel = panel.cut(
            cq.Workplane("XY")
            .transformed(offset=(0, 0, height - cfg.top_thickness))
            .box(cfg.dado_depth, panel_depth, cfg.top_thickness, centered=False)
        )
        # Top dado — right face
        panel = panel.cut(
            cq.Workplane("XY")
            .transformed(offset=(cfg.side_thickness - cfg.dado_depth, 0, height - cfg.top_thickness))
            .box(cfg.dado_depth, panel_depth, cfg.top_thickness, centered=False)
        )
    # Note: divider depth = depth - back_rabbet_width; the top panel
    # extends further back but sits above the divider, so no conflict.

    return panel


@dataclass
class PartInfo:
    """Metadata for a part in the assembly."""
    name: str
    shape: object  # cq.Workplane
    material_thickness: float
    grain_direction: str  # "length" or "width" — which dimension follows grain
    edge_band: list[str] = field(default_factory=list)  # list of edges to band
    notes: str = ""


def build_cabinet(
    cfg: Optional[CabinetConfig] = None,
    suppress_left_side: bool = False,
    suppress_right_side: bool = False,
    suppress_back: bool = False,
) -> tuple["cq.Assembly", list[PartInfo]]:
    """Build a complete cabinet assembly from configuration.

    Args:
        cfg:                Cabinet configuration (defaults to CabinetConfig()).
        suppress_left_side:  When True, omit the left side panel.  Used when
                             a dedicated interior divider panel takes its place.
        suppress_right_side: When True, omit the right side panel.  Used when
                             a dedicated interior divider panel takes its place.
        suppress_back:       When True, omit the back panel.  Used when a
                             single continuous back spans all bays.

    Returns:
        Tuple of (cq.Assembly, list of PartInfo for BOM/cutlist).
    """
    _require_cq()
    if cfg is None:
        cfg = CabinetConfig()

    parts: list[PartInfo] = []

    # ── Side panels ──────────────────────────────────────────────────────
    left_side  = make_side_panel(cfg, mirror=False) if not suppress_left_side  else None
    right_side = make_side_panel(cfg, mirror=True)  if not suppress_right_side else None

    if left_side is not None:
        parts.append(PartInfo(
            name="left_side",
            shape=left_side,
            material_thickness=cfg.side_thickness,
            grain_direction="length",
            edge_band=["front"],
        ))
    if right_side is not None:
        parts.append(PartInfo(
            name="right_side",
            shape=right_side,
            material_thickness=cfg.side_thickness,
            grain_direction="length",
            edge_band=["front"],
        ))

    # ── Bottom panel ─────────────────────────────────────────────────────
    bottom = make_bottom_panel(cfg)
    parts.append(PartInfo(
        name="bottom",
        shape=bottom,
        material_thickness=cfg.bottom_thickness,
        grain_direction="width",  # grain runs left-to-right
        edge_band=["front"],
    ))

    # ── Top panel ────────────────────────────────────────────────────────
    top = make_top_panel(cfg)
    parts.append(PartInfo(
        name="top",
        shape=top,
        material_thickness=cfg.top_thickness,
        grain_direction="width",
        edge_band=["front"],
    ))

    # ── Fixed shelves ────────────────────────────────────────────────────
    shelves = []
    for i, shelf_z in enumerate(cfg.fixed_shelf_positions):
        shelf = make_shelf(cfg)
        shelves.append(shelf)
        parts.append(PartInfo(
            name=f"shelf_{i}",
            shape=shelf,
            material_thickness=cfg.shelf_thickness,
            grain_direction="width",
            edge_band=["front"],
        ))

    # ── Back panel ───────────────────────────────────────────────────────
    back = make_back_panel(cfg) if not suppress_back else None
    if back is not None:
        parts.append(PartInfo(
            name="back",
            shape=back,
            material_thickness=cfg.back_thickness,
            grain_direction="width",
            notes="1/4 inch plywood",
        ))

    # ── Assembly ─────────────────────────────────────────────────────────
    assy = cq.Assembly(name="base_cabinet")

    # Left side: sits at x=0 (omitted when suppress_left_side=True)
    if left_side is not None:
        assy.add(left_side, name="left_side", loc=cq.Location((0, 0, 0)),
                 color=cq.Color(0.87, 0.72, 0.53, 1.0))

    # Right side: sits at x = width - side_thickness (omitted when suppress_right_side=True)
    if right_side is not None:
        assy.add(right_side, name="right_side",
                 loc=cq.Location((cfg.width - cfg.side_thickness, 0, 0)),
                 color=cq.Color(0.87, 0.72, 0.53, 1.0))

    # Bottom: sits between sides, in the dados
    # X position: side_thickness - dado_depth (panel extends into dado)
    bottom_x = cfg.side_thickness - cfg.dado_depth
    assy.add(bottom, name="bottom", loc=cq.Location((bottom_x, 0, 0)),
             color=cq.Color(0.87, 0.72, 0.53, 1.0))

    # Shelves
    for i, (shelf, shelf_z) in enumerate(zip(shelves, cfg.fixed_shelf_positions)):
        shelf_x = cfg.side_thickness - cfg.dado_depth
        assy.add(shelf, name=f"shelf_{i}", loc=cq.Location((shelf_x, 0, shelf_z)),
                 color=cq.Color(0.80, 0.65, 0.45, 1.0))

    # Top panel: sits in dados at the top of both sides
    top_x = cfg.side_thickness - cfg.dado_depth
    top_z = cfg.height - cfg.top_thickness
    assy.add(top, name="top", loc=cq.Location((top_x, 0, top_z)),
             color=cq.Color(0.87, 0.72, 0.53, 1.0))

    # Back panel: sits in rabbets (omitted when suppress_back=True)
    if back is not None:
        back_x = cfg.side_thickness - cfg.back_rabbet_depth
        back_y = cfg.depth - cfg.back_rabbet_width
        assy.add(back, name="back", loc=cq.Location((back_x, back_y, 0)),
                 color=cq.Color(0.75, 0.60, 0.40, 0.8))

    return assy, parts


def _make_pull_shape(pull_spec, vertical: bool = False) -> "Optional[cq.Workplane]":
    """Return a simple 3D body for a pull, centered at its geometric midpoint.

    The caller places this shape so its origin sits at:
        (face_center_x, face_front_y - projection/2, face_center_z)

    ``vertical=True`` rotates the bar so its long axis runs along Z (used for
    door pulls, which are mounted vertically).

    Returns None for flush/recessed pulls (nothing projects above the face).
    """
    _require_cq()
    proj = max(pull_spec.projection_mm, 4.0)
    if pull_spec.mount_style is MountStyle.FLUSH:
        return None
    if pull_spec.mount_style is MountStyle.KNOB:
        r = max(proj * 0.6, 8.0)
        return cq.Workplane("XY").sphere(r)
    # SURFACE or EDGE bar pull — a rounded rectangular bar
    bar_h = min(proj * 0.7, 12.0)
    if vertical:
        return cq.Workplane("XY").box(bar_h, proj, pull_spec.length_mm, centered=True)
    return cq.Workplane("XY").box(pull_spec.length_mm, proj, bar_h, centered=True)


def build_multi_bay_cabinet(
    bay_configs: list["CabinetConfig"],
    foot_height: Optional[float] = None,
    foot_diameter: Optional[float] = None,
    face_thickness: float = 18.0,
    outer_overlay: float = 18.0,
    inner_overlay: float = 8.0,
    face_gap: float = 4.0,
    face_bottom_overhang: float = 0.0,
    face_top_overhang: float = 0.0,
    include_drawers: bool = True,
    include_faces: bool = True,
    include_feet: bool = True,
    feet_at_dividers: bool = True,
    furniture_top: bool = False,
    transition_shelf_zs: Optional[list[float]] = None,
    divider_top_z: Optional[float] = None,
) -> tuple["cq.Assembly", list["PartInfo"]]:
    """Build a multi-bay cabinet assembly with bays positioned side-by-side.

    Bay 0 is leftmost; the outer edges of bay 0 and bay[-1] are flush with
    the full cabinet exterior.  Drawer faces span the dividers using
    ``outer_overlay`` on the two outermost edges and ``inner_overlay`` on
    all interior bay joints, leaving a ``divider_thickness - 2 * inner_overlay``
    gap between adjacent bay faces.

    The face stack is anchored at top and bottom:
    - Bottom of lowest face = ``bottom_thickness - face_bottom_overhang``
      (0 = faces start at top of bottom panel; set to bottom_thickness for flush-to-carcass-exterior)
    - Top of highest face  = ``height - top_thickness + face_top_overhang``
      (0 = faces end at underside of top panel; set to top_thickness for flush-to-carcass-exterior)

    Between adjacent faces ``face_gap`` is the **total** clearance between the
    bottom edge of the upper face and the top edge of the lower face.  Half of
    ``face_gap`` is trimmed from each side of the opening boundary, so both
    faces share the gap symmetrically.

    Args:
        bay_configs:          Ordered list of CabinetConfig, left to right.
        foot_height:          Adjustable-foot height in mm (default 102 mm = 4″).
        foot_diameter:        Foot cylinder diameter in mm.
        face_thickness:       Drawer face panel thickness in mm.
        outer_overlay:        Face overhang on outermost cabinet edges (flush = side_thickness).
        inner_overlay:        Face overhang on interior bay dividers.
        face_gap:             Total vertical gap between adjacent faces (mm).  Half is
                              trimmed from the top of the lower face and half from the
                              bottom of the upper face.
        face_bottom_overhang: How far the bottom face extends below the top surface of
                              the bottom panel (default 0 = starts at top of bottom panel).
        face_top_overhang:    How far the top face extends above the underside of the top
                              panel (default 0 = ends at underside of top panel).
        include_drawers:      Build and add drawer box assemblies.
        include_faces:        Build and add drawer face panels.
        include_feet:         Build and add adjustable-foot cylinders.
        furniture_top:        When True, adds a "furniture top" style: a front cap
                              strip extends the top panel forward to the drawer-face
                              plane, and the bottom of the lowest drawer face drops
                              to the underside of the carcass bottom panel
                              (face_bottom_overhang is automatically set to
                              bottom_thickness; an explicit face_bottom_overhang
                              argument is ignored when furniture_top=True).

    Returns:
        (cq.Assembly, list[PartInfo]) — the full assembly and its parts list.
    """
    _require_cq()

    # Lazy import to avoid circular dependency (drawer.py imports from cabinet.py)
    from .drawer import DrawerConfig, build_drawer

    all_parts: list[PartInfo] = []
    assy = cq.Assembly(name="multi_bay_cabinet")

    n_bays = len(bay_configs)

    # ── Bay X offsets ──────────────────────────────────────────────────────────
    # Adjacent bays share a single divider panel: the right panel of bay N serves
    # as the left wall of bay N+1.  Each non-leftmost bay is therefore shifted
    # one side_thickness to the left so its interior aligns with the shared panel.
    x_offsets: list[float] = []
    x = 0.0
    for i, cfg in enumerate(bay_configs):
        x_offsets.append(x)
        x += cfg.width - (cfg.side_thickness if i < n_bays - 1 else 0)
    total_width = x

    # ── furniture_top override ─────────────────────────────────────────────────
    # "Furniture top, flush bottom": the top panel cap extends forward to the face
    # plane; the lowest drawer face drops to the carcass underside.
    if furniture_top:
        face_bottom_overhang = bay_configs[0].bottom_thickness
        face_top_overhang    = -face_gap        # same reveal as between adjacent faces

    # Colours — alternate slightly between bays for clarity
    carcass_colours = [
        cq.Color(0.87, 0.72, 0.53, 1.0),
        cq.Color(0.80, 0.65, 0.45, 1.0),
        cq.Color(0.87, 0.72, 0.53, 1.0),
    ]
    drawer_colour = cq.Color(0.78, 0.65, 0.42, 1.0)
    face_colour   = cq.Color(0.55, 0.38, 0.22, 1.0)
    foot_colour   = cq.Color(0.25, 0.25, 0.28, 1.0)

    # ── Carcass bays ───────────────────────────────────────────────────────────
    for bay_idx, (cfg, bx) in enumerate(zip(bay_configs, x_offsets)):
        bay_assy, bay_parts = build_cabinet(
            cfg,
            suppress_left_side=(bay_idx > 0),           # divider provides left wall
            suppress_right_side=(bay_idx < n_bays - 1), # divider provides right wall
            suppress_back=True,                          # single continuous back added below
        )
        col = carcass_colours[bay_idx % len(carcass_colours)]
        assy.add(bay_assy, name=f"bay_{bay_idx}",
                 loc=cq.Location((bx, 0, 0)),
                 color=col)
        for p in bay_parts:
            all_parts.append(PartInfo(
                name=f"bay{bay_idx}_{p.name}",
                shape=p.shape,
                material_thickness=p.material_thickness,
                grain_direction=p.grain_direction,
                edge_band=list(p.edge_band),
                notes=p.notes,
            ))

    # ── Interior vertical dividers ─────────────────────────────────────────────
    # One purpose-built divider per bay boundary, placed at x_offsets[1:].
    # Depth = depth - back_rabbet_width so the back edge is flush with the
    # front face of the continuous back panel (no protrusion behind the back).
    divider_colour = cq.Color(0.87, 0.72, 0.53, 1.0)
    for div_idx, (div_x, cfg) in enumerate(zip(x_offsets[1:], bay_configs)):
        div_shape = make_interior_divider(cfg, height_override=divider_top_z)
        assy.add(div_shape, name=f"divider_{div_idx}",
                 loc=cq.Location((div_x, 0, 0)),
                 color=divider_colour)
        all_parts.append(PartInfo(
            name=f"divider_{div_idx}",
            shape=div_shape,
            material_thickness=cfg.side_thickness,
            grain_direction="length",
            edge_band=["front"],
        ))

    # ── Continuous back panel ──────────────────────────────────────────────────
    # A single panel spanning all bays, fitting into the outer side-panel rabbets
    # and running behind the shared interior dividers.
    cfg0 = bay_configs[0]
    cfg_last = bay_configs[-1]
    cont_back_width = (
        total_width
        - (cfg0.side_thickness - cfg0.back_rabbet_depth)   # left rabbet offset
        - (cfg_last.side_thickness - cfg_last.back_rabbet_depth)  # right rabbet offset
    )
    cont_back = (
        cq.Workplane("XY")
        .box(cont_back_width, cfg0.back_thickness, cfg0.back_panel_height, centered=False)
    )
    back_x = cfg0.side_thickness - cfg0.back_rabbet_depth
    back_y = cfg0.depth - cfg0.back_rabbet_width
    assy.add(cont_back, name="back",
             loc=cq.Location((back_x, back_y, 0)),
             color=cq.Color(0.75, 0.60, 0.40, 0.8))
    all_parts.append(PartInfo(
        name="back",
        shape=cont_back,
        material_thickness=cfg0.back_thickness,
        grain_direction="width",
        notes="1/4 inch plywood — single panel spanning all bays",
    ))

    # ── Transition shelves ─────────────────────────────────────────────────────
    # Full-width horizontal panels at drawer-to-door boundaries (e.g. armoire base).
    if transition_shelf_zs:
        shelf_colour_ts = cq.Color(0.87, 0.72, 0.53, 1.0)
        ts_cfg  = bay_configs[0]
        ts_w    = total_width - 2 * ts_cfg.side_thickness
        ts_dep  = ts_cfg.depth - ts_cfg.back_rabbet_width
        ts_thk  = ts_cfg.shelf_thickness
        for ts_idx, ts_z in enumerate(transition_shelf_zs):
            ts_panel = (
                cq.Workplane("XY")
                .box(ts_w, ts_dep, ts_thk, centered=False)
            )
            assy.add(
                ts_panel,
                name=f"transition_shelf_{ts_idx}",
                loc=cq.Location((ts_cfg.side_thickness, 0.0, ts_z)),
                color=shelf_colour_ts,
            )
            all_parts.append(PartInfo(
                name=f"transition_shelf_{ts_idx}",
                shape=ts_panel,
                material_thickness=ts_thk,
                grain_direction="width",
                edge_band=["front"],
                notes="transition shelf — drawer-to-door boundary",
            ))

    # ── Furniture top cap ──────────────────────────────────────────────────────
    # A thin horizontal strip that extends the top panel forward to the drawer
    # face plane, creating a flush furniture-style top edge.
    if furniture_top:
        top_cap = (
            cq.Workplane("XY")
            .box(total_width, face_thickness, cfg0.top_thickness, centered=False)
        )
        cap_z = cfg0.height - cfg0.top_thickness
        assy.add(top_cap, name="top_front_cap",
                 loc=cq.Location((0.0, -face_thickness, cap_z)),
                 color=carcass_colours[0])
        all_parts.append(PartInfo(
            name="top_front_cap",
            shape=top_cap,
            material_thickness=cfg0.top_thickness,
            grain_direction="width",
            edge_band=["front", "left", "right"],
            notes="furniture top front cap — spans full cabinet width",
        ))

    # ── Drawer boxes ───────────────────────────────────────────────────────────
    if include_drawers:
        for bay_idx, (cfg, bx) in enumerate(zip(bay_configs, x_offsets)):
            if not cfg.openings:
                continue

            slide = get_slide(cfg.drawer_slide)
            z = cfg.bottom_thickness  # drawers sit above the bottom panel

            for drw_idx, op in enumerate(cfg.openings):
                opening_h = op.height_mm
                if op.opening_type == "drawer":
                    dcfg = DrawerConfig(
                        opening_width=cfg.interior_width,
                        opening_height=opening_h,
                        opening_depth=cfg.interior_depth,
                        slide_key=cfg.drawer_slide,
                        applied_face=False,  # faces handled below
                    )
                    drw_assy, drw_parts = build_drawer(dcfg)

                    drw_x = bx + cfg.side_thickness + slide.nominal_side_clearance
                    drw_y = dcfg.front_gap
                    drw_z = z + slide.min_bottom_clearance

                    assy.add(drw_assy, name=f"bay{bay_idx}_drawer{drw_idx}",
                             loc=cq.Location((drw_x, drw_y, drw_z)),
                             color=drawer_colour)

                z += opening_h

    # ── Drawer faces ───────────────────────────────────────────────────────────
    if include_faces:
        for bay_idx, (cfg, bx) in enumerate(zip(bay_configs, x_offsets)):
            if not cfg.openings:
                continue

            is_leftmost  = bay_idx == 0
            is_rightmost = bay_idx == n_bays - 1

            left_ov  = outer_overlay if is_leftmost  else inner_overlay
            right_ov = outer_overlay if is_rightmost else inner_overlay

            face_w = left_ov + cfg.interior_width + right_ov

            # Global X of the face's left edge
            if is_leftmost:
                face_x = 0.0
            else:
                face_x = bx + cfg.side_thickness - inner_overlay

            # Anchor the face stack between the bottom and top panels.
            # z_face_start = bottom of the lowest face (in assembly Z coordinates)
            # z_face_end   = top of the highest face
            z_face_start = cfg.bottom_thickness - face_bottom_overhang
            z_face_end   = cfg.height - cfg.top_thickness + face_top_overhang

            # Collect drawer openings with their cumulative Z position within the
            # carcass interior (measured from the top of the bottom panel).
            drawer_slots: list[tuple[int, int, float]] = []  # (drw_idx, opening_h, opening_z)
            z_acc = cfg.bottom_thickness
            for drw_idx, op in enumerate(cfg.openings):
                if op.opening_type == "drawer":
                    drawer_slots.append((drw_idx, op.height_mm, z_acc))
                z_acc += op.height_mm

            n_faces = len(drawer_slots)
            for face_num, (drw_idx, opening_h, opening_z) in enumerate(drawer_slots):
                is_first = face_num == 0
                is_last  = face_num == n_faces - 1

                # Bottom edge of this face.
                # Non-first faces start face_gap/2 above the opening boundary so
                # the gap straddles the boundary symmetrically.
                if is_first:
                    face_z_bot = z_face_start
                else:
                    face_z_bot = opening_z + face_gap / 2

                # Top edge of this face.
                # Anchor to z_face_end only when this drawer is also the last
                # opening in the column (i.e. no door/open openings above it).
                # If door openings follow, apply the same face_gap/2 trim so the
                # gap above the top drawer matches the gaps between drawers.
                is_last_in_col = (drw_idx == len(cfg.openings) - 1)
                if is_last and is_last_in_col:
                    face_z_top = z_face_end
                else:
                    face_z_top = opening_z + opening_h - face_gap / 2

                face_h = face_z_top - face_z_bot
                face_shape = (
                    cq.Workplane("XY")
                    .box(face_w, face_thickness, face_h, centered=False)
                )
                # y = -face_thickness so face sits proud of carcass front
                assy.add(face_shape,
                         name=f"bay{bay_idx}_face{drw_idx}",
                         loc=cq.Location((face_x, -face_thickness, face_z_bot)),
                         color=face_colour)
                all_parts.append(PartInfo(
                    name=f"bay{bay_idx}_face{drw_idx}",
                    shape=face_shape,
                    material_thickness=face_thickness,
                    grain_direction="width",
                    edge_band=["all"],
                ))

    # ── Door panels ────────────────────────────────────────────────────────────
    # Render a flat face panel for every "door" or "door_pair" slot.
    # "door_pair" splits into two panels with a 3 mm centre gap.
    # Uses the same z_face_start / z_face_end anchors as drawer faces so that
    # in mixed columns all face edges align at the top and bottom.
    if include_faces:
        door_gap_centre = 3.0
        for bay_idx, (cfg, bx) in enumerate(zip(bay_configs, x_offsets)):
            if not cfg.openings:
                continue

            is_leftmost  = bay_idx == 0
            is_rightmost = bay_idx == n_bays - 1
            left_ov  = outer_overlay if is_leftmost  else inner_overlay
            right_ov = outer_overlay if is_rightmost else inner_overlay
            face_w   = left_ov + cfg.interior_width + right_ov
            face_x   = 0.0 if is_leftmost else bx + cfg.side_thickness - inner_overlay

            z_face_start = cfg.bottom_thickness - face_bottom_overhang
            z_face_end   = cfg.height - cfg.top_thickness + face_top_overhang
            n_slots      = len(cfg.openings)

            z_acc = cfg.bottom_thickness
            for slot_idx, op in enumerate(cfg.openings):
                opening_h  = op.height_mm
                slot_type  = op.opening_type
                if slot_type in ("door", "door_pair"):
                    is_first = slot_idx == 0
                    is_last  = slot_idx == n_slots - 1
                    # Door face starts at z_acc + face_gap/2 — same rule as between
                    # adjacent drawers.  The transition shelf sits behind the face.
                    face_z_bot = z_face_start if is_first else z_acc + face_gap / 2
                    face_z_top = z_face_end   if is_last  else z_acc + opening_h - face_gap / 2
                    face_h = face_z_top - face_z_bot

                    if slot_type == "door_pair":
                        door_w = (face_w - door_gap_centre) / 2
                        for i, dx in enumerate(
                            [face_x, face_x + door_w + door_gap_centre]
                        ):
                            ds = (
                                cq.Workplane("XY")
                                .box(door_w, face_thickness, face_h, centered=False)
                            )
                            assy.add(
                                ds,
                                name=f"bay{bay_idx}_door{slot_idx}_{i}",
                                loc=cq.Location((dx, -face_thickness, face_z_bot)),
                                color=face_colour,
                            )
                            all_parts.append(PartInfo(
                                name=f"bay{bay_idx}_door{slot_idx}_{i}",
                                shape=ds,
                                material_thickness=face_thickness,
                                grain_direction="length",
                                edge_band=["all"],
                            ))
                    else:
                        ds = (
                            cq.Workplane("XY")
                            .box(face_w, face_thickness, face_h, centered=False)
                        )
                        assy.add(
                            ds,
                            name=f"bay{bay_idx}_door{slot_idx}",
                            loc=cq.Location((face_x, -face_thickness, face_z_bot)),
                            color=face_colour,
                        )
                        all_parts.append(PartInfo(
                            name=f"bay{bay_idx}_door{slot_idx}",
                            shape=ds,
                            material_thickness=face_thickness,
                            grain_direction="length",
                            edge_band=["all"],
                        ))
                z_acc += opening_h

    # ── Pull hardware ──────────────────────────────────────────────────────────
    # For each bay that has a drawer_pull configured, place the pull body on
    # every drawer face.  Pulls are named bay{i}_pull{j}_{k} so the visualizer
    # can animate them alongside the matching face (bay{i}_face{j}).
    if include_faces:
        from .pulls import pull_positions as _pull_positions
        pull_colour = cq.Color(0.40, 0.40, 0.45, 1.0)

        for bay_idx, (cfg, bx) in enumerate(zip(bay_configs, x_offsets)):
            if not cfg.drawer_pull or not cfg.openings:
                continue
            try:
                pull_spec = get_pull(cfg.drawer_pull)
            except KeyError:
                continue

            pull_body = _make_pull_shape(pull_spec)
            if pull_body is None:
                continue  # flush / recessed pulls have nothing to render

            is_leftmost  = bay_idx == 0
            is_rightmost = bay_idx == n_bays - 1
            left_ov  = outer_overlay if is_leftmost  else inner_overlay
            right_ov = outer_overlay if is_rightmost else inner_overlay
            face_w   = left_ov + cfg.interior_width + right_ov
            face_x   = 0.0 if is_leftmost else bx + cfg.side_thickness - inner_overlay

            z_face_start = cfg.bottom_thickness - face_bottom_overhang
            z_face_end   = cfg.height - cfg.top_thickness + face_top_overhang

            drawer_slots: list[tuple[int, float, float]] = []
            z_acc = cfg.bottom_thickness
            for drw_idx, op in enumerate(cfg.openings):
                if op.opening_type == "drawer":
                    drawer_slots.append((drw_idx, op.height_mm, z_acc))
                z_acc += op.height_mm

            n_faces = len(drawer_slots)
            pull_py = -face_thickness - pull_spec.projection_mm / 2.0

            is_last_slot_drawer = cfg.openings[-1].opening_type == "drawer"
            for face_num, (drw_idx, opening_h, opening_z) in enumerate(drawer_slots):
                is_first = face_num == 0
                is_last  = face_num == n_faces - 1
                is_last_in_col = drw_idx == len(cfg.openings) - 1
                face_z_bot = z_face_start if is_first else opening_z + face_gap / 2
                if is_last and is_last_in_col:
                    face_z_top = z_face_end
                else:
                    face_z_top = opening_z + opening_h - face_gap / 2
                face_h = face_z_top - face_z_bot

                try:
                    placements = _pull_positions(face_w, face_h, pull_spec, cfg.drawer_pull)
                except ValueError:
                    continue

                for p_idx, placement in enumerate(placements):
                    cx, cz = placement.center
                    assy.add(
                        pull_body,
                        name=f"bay{bay_idx}_pull{drw_idx}_{p_idx}",
                        loc=cq.Location((face_x + cx, pull_py, face_z_bot + cz)),
                        color=pull_colour,
                    )

    # ── Door pull hardware ─────────────────────────────────────────────────────
    # Place a pull body on every door / door_pair face for bays with door_pull set.
    if include_faces:
        from .pulls import pull_positions as _pull_positions
        pull_colour = cq.Color(0.40, 0.40, 0.45, 1.0)
        door_gap_centre = 3.0

        for bay_idx, (cfg, bx) in enumerate(zip(bay_configs, x_offsets)):
            if not cfg.door_pull or not cfg.openings:
                continue
            try:
                pull_spec = get_pull(cfg.door_pull)
            except KeyError:
                continue

            pull_body = _make_pull_shape(pull_spec, vertical=True)
            if pull_body is None:
                continue

            is_leftmost  = bay_idx == 0
            is_rightmost = bay_idx == n_bays - 1
            left_ov  = outer_overlay if is_leftmost  else inner_overlay
            right_ov = outer_overlay if is_rightmost else inner_overlay
            face_w   = left_ov + cfg.interior_width + right_ov
            face_x   = 0.0 if is_leftmost else bx + cfg.side_thickness - inner_overlay

            z_face_start = cfg.bottom_thickness - face_bottom_overhang
            z_face_end   = cfg.height - cfg.top_thickness + face_top_overhang
            n_slots      = len(cfg.openings)
            pull_py      = -face_thickness - pull_spec.projection_mm / 2.0

            z_acc = cfg.bottom_thickness
            for slot_idx, op in enumerate(cfg.openings):
                opening_h = op.height_mm
                slot_type = op.opening_type
                if slot_type in ("door", "door_pair"):
                    is_first   = slot_idx == 0
                    is_last    = slot_idx == n_slots - 1
                    face_z_bot = z_face_start if is_first else z_acc + face_gap / 2
                    face_z_top = z_face_end   if is_last  else z_acc + opening_h - face_gap / 2
                    face_h     = face_z_top - face_z_bot

                    if slot_type == "door_pair":
                        # Pair: left leaf hinges left (outer), right leaf hinges right (outer).
                        # Pulls go on the latch (inner) edges regardless of cfg.door_hinge_side.
                        door_w = (face_w - door_gap_centre) / 2
                        pair_hinge_sides: list[HingeSide] = ["left", "right"]
                        for door_i, door_x in enumerate(
                            [face_x, face_x + door_w + door_gap_centre]
                        ):
                            hs = pair_hinge_sides[door_i]
                            cx = door_pull_x_center(door_w, pull_spec, hs, cfg.door_pull_inset_mm, vertical=True)
                            try:
                                placements = _pull_positions(
                                    door_w, face_h, pull_spec, cfg.door_pull,
                                    x_override_mm=cx,
                                    vertical="upper_third",
                                )
                            except ValueError:
                                continue
                            for p_idx, placement in enumerate(placements):
                                _cx, cz = placement.center
                                assy.add(
                                    pull_body,
                                    name=f"bay{bay_idx}_doorpull{slot_idx}_{door_i}_{p_idx}",
                                    loc=cq.Location((door_x + _cx, pull_py, face_z_bot + cz)),
                                    color=pull_colour,
                                )
                    else:
                        cx = door_pull_x_center(
                            face_w, pull_spec, cfg.door_hinge_side, cfg.door_pull_inset_mm, vertical=True
                        )
                        try:
                            placements = _pull_positions(
                                face_w, face_h, pull_spec, cfg.door_pull,
                                x_override_mm=cx,
                                vertical="upper_third",
                            )
                        except ValueError:
                            continue
                        for p_idx, placement in enumerate(placements):
                            _cx, cz = placement.center
                            assy.add(
                                pull_body,
                                name=f"bay{bay_idx}_doorpull{slot_idx}_{p_idx}",
                                loc=cq.Location((face_x + _cx, pull_py, face_z_bot + cz)),
                                color=pull_colour,
                            )
                z_acc += opening_h

    # ── Feet ───────────────────────────────────────────────────────────────────
    if include_feet:
        cfg0       = bay_configs[0]
        depth      = cfg0.depth
        foot_inset = cfg0.leg_inset

        # Resolve leg spec from the first bay's config; fall back to caller overrides
        try:
            leg_spec = get_leg(cfg0.leg_key)
            _foot_height   = foot_height   if foot_height   is not None else leg_spec.height_mm
            _foot_diameter = foot_diameter if foot_diameter is not None else leg_spec.base_diameter_mm
        except KeyError:
            _foot_height   = foot_height   if foot_height   is not None else 102.0
            _foot_diameter = foot_diameter if foot_diameter is not None else 50.0

        # X positions: outer corners only, or also under each interior divider
        foot_xs = [foot_inset, total_width - foot_inset]
        if feet_at_dividers:
            foot_xs += list(x_offsets[1:])
        foot_ys = [foot_inset, depth - foot_inset]

        foot_shape = (
            cq.Workplane("XY")
            .cylinder(_foot_height, _foot_diameter / 2, centered=(True, True, False))
        )
        fi = 0
        for fx in foot_xs:
            for fy in foot_ys:
                assy.add(foot_shape, name=f"foot_{fi}",
                         loc=cq.Location((fx, fy, -_foot_height)),
                         color=foot_colour)
                fi += 1

    return assy, all_parts
