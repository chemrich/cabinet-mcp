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

from .hardware import DrawerSlideSpec, get_slide
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

    # Opening stack (from bottom up, list of (height, slot_type)).
    # slot_type options:
    #   "drawer"     — a drawer box on slides
    #   "door"       — a single swinging door
    #   "door_pair"  — a matched pair of doors side-by-side
    #   "shelf"      — a fixed or adjustable shelf opening
    #   "open"       — open compartment (no door/drawer)
    drawer_config: list[tuple[float, str]] = field(default_factory=list)
    drawer_slide: str = "blum_tandem_550h"

    # Door hardware
    door_hinge: str = "blum_clip_top_110_full"

    # Carcass joinery method
    carcass_joinery: CarcassJoinery = CarcassJoinery.DADO_RABBET

    # Per-method joinery specs (used when the matching joinery method is selected)
    domino_spec: DominoSpec = field(default_factory=lambda: DEFAULT_DOMINO)
    pocket_screw_spec: PocketScrewSpec = field(default_factory=lambda: DEFAULT_POCKET_SCREW)
    biscuit_spec: BiscuitSpec = field(default_factory=lambda: DEFAULT_BISCUIT)
    dowel_spec: DownelSpec = field(default_factory=lambda: DEFAULT_DOWEL)

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
        return self.height


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

    # Cut dado for top panel (mirrors bottom dado, at z = height - top_thickness)
    top_dado = (
        cq.Workplane("XY")
        .transformed(offset=(dado_x, 0, cfg.height - cfg.top_thickness))
        .box(cfg.dado_depth, cfg.depth - cfg.back_rabbet_width, cfg.top_thickness, centered=False)
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

    # Drill shelf pin holes (32mm system)
    if cfg.adj_shelf_holes:
        z = cfg.shelf_pin_start_z
        while z <= cfg.shelf_pin_end_z:
            for y_inset in [cfg.shelf_pin_row_inset, cfg.depth - cfg.back_rabbet_width - cfg.shelf_pin_row_inset]:
                # Left panel: interior face at x=side_thickness, columns inset from there.
                # Right panel: interior face at x=0, columns inset from there.
                hole_x = cfg.side_thickness - cfg.shelf_pin_row_inset if not mirror else cfg.shelf_pin_row_inset
                pin_hole = (
                    cq.Workplane("XY")
                    .transformed(offset=(hole_x, y_inset, z))
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
    """Create the top panel. Sits in dados at the top of both side panels."""
    _require_cq()
    panel_width = cfg.interior_width + (cfg.dado_depth * 2)
    panel_depth = cfg.depth - cfg.back_rabbet_width

    return (
        cq.Workplane("XY")
        .box(panel_width, panel_depth, cfg.top_thickness, centered=False)
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


@dataclass
class PartInfo:
    """Metadata for a part in the assembly."""
    name: str
    shape: object  # cq.Workplane
    material_thickness: float
    grain_direction: str  # "length" or "width" — which dimension follows grain
    edge_band: list[str] = field(default_factory=list)  # list of edges to band
    notes: str = ""


def build_cabinet(cfg: Optional[CabinetConfig] = None) -> tuple["cq.Assembly", list[PartInfo]]:
    """Build a complete cabinet assembly from configuration.

    Returns:
        Tuple of (cq.Assembly, list of PartInfo for BOM/cutlist).
    """
    _require_cq()
    if cfg is None:
        cfg = CabinetConfig()

    parts: list[PartInfo] = []

    # ── Side panels ──────────────────────────────────────────────────────
    left_side = make_side_panel(cfg, mirror=False)
    right_side = make_side_panel(cfg, mirror=True)

    parts.append(PartInfo(
        name="left_side",
        shape=left_side,
        material_thickness=cfg.side_thickness,
        grain_direction="length",  # grain runs vertically (height)
        edge_band=["front"],
    ))
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
    back = make_back_panel(cfg)
    parts.append(PartInfo(
        name="back",
        shape=back,
        material_thickness=cfg.back_thickness,
        grain_direction="width",
        notes="1/4 inch plywood",
    ))

    # ── Assembly ─────────────────────────────────────────────────────────
    assy = cq.Assembly(name="base_cabinet")

    # Left side: sits at x=0
    assy.add(left_side, name="left_side", loc=cq.Location((0, 0, 0)),
             color=cq.Color(0.87, 0.72, 0.53, 1.0))

    # Right side: sits at x = width - side_thickness
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

    # Back panel: sits in rabbets
    back_x = cfg.side_thickness - cfg.back_rabbet_depth
    back_y = cfg.depth - cfg.back_rabbet_width
    assy.add(back, name="back", loc=cq.Location((back_x, back_y, 0)),
             color=cq.Color(0.75, 0.60, 0.40, 0.8))

    return assy, parts


def build_multi_bay_cabinet(
    bay_configs: list["CabinetConfig"],
    foot_height: float = 102.0,
    foot_diameter: float = 50.0,
    face_thickness: float = 18.0,
    outer_overlay: float = 18.0,
    inner_overlay: float = 17.0,
    face_v_gap: float = 2.0,
    face_bottom_overhang: float = 0.0,
    face_top_overhang: float = 0.0,
    include_drawers: bool = True,
    include_faces: bool = True,
    include_feet: bool = True,
) -> tuple["cq.Assembly", list["PartInfo"]]:
    """Build a multi-bay cabinet assembly with bays positioned side-by-side.

    Bay 0 is leftmost; the outer edges of bay 0 and bay[-1] are flush with
    the full cabinet exterior.  Drawer faces span the dividers using
    ``outer_overlay`` on the two outermost edges and ``inner_overlay`` on
    all interior bay joints, leaving a ``inner_overlay * 2 - bay_side_thickness``
    gap between adjacent bay faces (typically 2 mm).

    The face stack is anchored at top and bottom:
    - Bottom of lowest face = ``bottom_thickness - face_bottom_overhang``
      (0 = faces start at top of bottom panel; set to bottom_thickness for flush-to-carcass-exterior)
    - Top of highest face  = ``height - top_thickness + face_top_overhang``
      (0 = faces end at underside of top panel; set to top_thickness for flush-to-carcass-exterior)

    Args:
        bay_configs:          Ordered list of CabinetConfig, left to right.
        foot_height:          Adjustable-foot height in mm (default 102 mm = 4″).
        foot_diameter:        Foot cylinder diameter in mm.
        face_thickness:       Drawer face panel thickness in mm.
        outer_overlay:        Face overhang on outermost cabinet edges (flush = side_thickness).
        inner_overlay:        Face overhang on interior bay dividers (leaves 2 mm gap
                              when both adjacent faces each claim inner_overlay on an
                              18 mm divider: 18 - 17 - 17 + 36 = 2 mm).
        face_v_gap:           Vertical gap between adjacent drawer faces (mm).
        face_bottom_overhang: How far the bottom face extends below the top surface of
                              the bottom panel (default 0 = starts at top of bottom panel).
        face_top_overhang:    How far the top face extends above the underside of the top
                              panel (default 0 = ends at underside of top panel).
        include_drawers:      Build and add drawer box assemblies.
        include_faces:        Build and add drawer face panels.
        include_feet:         Build and add adjustable-foot cylinders.

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
    x_offsets: list[float] = []
    x = 0.0
    for cfg in bay_configs:
        x_offsets.append(x)
        x += cfg.width
    total_width = x

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
        bay_assy, bay_parts = build_cabinet(cfg)
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

    # ── Drawer boxes ───────────────────────────────────────────────────────────
    if include_drawers:
        for bay_idx, (cfg, bx) in enumerate(zip(bay_configs, x_offsets)):
            if not cfg.drawer_config:
                continue

            slide = get_slide(cfg.drawer_slide)
            z = cfg.bottom_thickness  # drawers sit above the bottom panel

            for drw_idx, (opening_h, slot_type) in enumerate(cfg.drawer_config):
                if slot_type == "drawer":
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
                    drw_z = z

                    assy.add(drw_assy, name=f"bay{bay_idx}_drawer{drw_idx}",
                             loc=cq.Location((drw_x, drw_y, drw_z)),
                             color=drawer_colour)

                z += opening_h

    # ── Drawer faces ───────────────────────────────────────────────────────────
    if include_faces:
        for bay_idx, (cfg, bx) in enumerate(zip(bay_configs, x_offsets)):
            if not cfg.drawer_config:
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

            # Collect drawer slots with their cumulative Z position within the
            # carcass interior (measured from the top of the bottom panel).
            drawer_slots: list[tuple[int, int, float]] = []  # (drw_idx, opening_h, opening_z)
            z_acc = cfg.bottom_thickness
            for drw_idx, (opening_h, slot_type) in enumerate(cfg.drawer_config):
                if slot_type == "drawer":
                    drawer_slots.append((drw_idx, opening_h, z_acc))
                z_acc += opening_h

            n_faces = len(drawer_slots)
            for face_num, (drw_idx, opening_h, opening_z) in enumerate(drawer_slots):
                is_first = face_num == 0
                is_last  = face_num == n_faces - 1

                # Bottom edge of this face
                if is_first:
                    face_z_bot = z_face_start
                else:
                    face_z_bot = opening_z + face_v_gap

                # Top edge of this face
                if is_last:
                    face_z_top = z_face_end
                else:
                    face_z_top = opening_z + opening_h - face_v_gap

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

    # ── Feet ───────────────────────────────────────────────────────────────────
    if include_feet:
        depth      = bay_configs[0].depth
        foot_inset = 30.0

        # X positions: outer edges + under each bay divider
        foot_xs = [foot_inset, total_width - foot_inset] + list(x_offsets[1:])
        foot_ys = [foot_inset, depth - foot_inset]

        foot_shape = (
            cq.Workplane("XY")
            .cylinder(foot_height, foot_diameter / 2, centered=(True, True, False))
        )
        fi = 0
        for fx in foot_xs:
            for fy in foot_ys:
                assy.add(foot_shape, name=f"foot_{fi}",
                         loc=cq.Location((fx, fy, -foot_height)),
                         color=foot_colour)
                fi += 1

    return assy, all_parts
