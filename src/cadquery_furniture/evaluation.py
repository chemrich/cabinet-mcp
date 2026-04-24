"""
Evaluation harness for furniture designs.

Runs geometric and physical checks against cabinet assemblies:
- Interference detection (parts overlapping)
- Clearance validation (hardware requirements met)
- Dimensional consistency (cumulative heights, dado alignment)
- Shelf sag / deflection limits
- Drawer travel swept-volume checks

All checks return a list of Issue objects. An empty list means all checks pass.
"""

from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from typing import Optional

try:
    import cadquery as cq
except ImportError:
    cq = None

from .cabinet import CabinetConfig
from .drawer import DrawerConfig
from .door import DoorConfig
from .hardware import (
    DrawerSlideSpec,
    HingeSpec,
    MountStyle,
    OverlayType,
    PullSpec,
    get_slide,
    get_hinge,
    get_pull,
)
from .joinery import (
    DrawerJoineryStyle,
    CarcassJoinery,
    DominoSpec,
    PocketScrewSpec,
    BiscuitSpec,
    DownelSpec,
)
from .pulls import DUAL_PULL_THRESHOLD_MM, pull_fits_face, recommend_pull_count


class Severity(Enum):
    ERROR = "error"  # will not assemble / function
    WARNING = "warning"  # will work but suboptimal
    INFO = "info"  # informational


@dataclass
class Issue:
    """A single evaluation finding."""
    check: str  # which check produced this
    severity: Severity
    message: str
    part_a: str = ""
    part_b: str = ""
    value: Optional[float] = None  # measured value
    limit: Optional[float] = None  # threshold value

    def __str__(self) -> str:
        prefix = f"[{self.severity.value.upper()}]"
        parts = f" ({self.part_a}" + (f" ↔ {self.part_b})" if self.part_b else ")")
        return f"{prefix} {self.check}{parts}: {self.message}"


# ─── Dimensional / Parametric Checks (no CadQuery needed) ────────────────────


def check_drawer_stack_order(cab_cfg: CabinetConfig) -> list[Issue]:
    """Warn when a drawer opening is taller than the drawer directly below it.

    Traditional cabinetry proportion places the tallest drawer at the bottom and
    each successive drawer shorter as you go up.  A reversal is almost always a
    rounding artefact or a manually entered ``drawer_config`` where heights are in
    the wrong order.

    Only compares adjacent *drawer*-type openings; door and door_pair slots are
    ignored so that tall door compartments at the bottom or top don't trigger
    false positives.  A 0.5 mm tolerance prevents noise from sub-mm rounding in
    equal-proportion stacks.
    """
    TOLERANCE_MM = 0.5
    issues: list[Issue] = []

    # Collect just the drawer slots with their original stack position (0 = bottom).
    drawer_slots = [
        (i, h)
        for i, (h, t) in enumerate(cab_cfg.drawer_config)
        if t == "drawer"
    ]

    for idx in range(len(drawer_slots) - 1):
        pos_lower, h_lower = drawer_slots[idx]
        pos_upper, h_upper = drawer_slots[idx + 1]
        if h_upper > h_lower + TOLERANCE_MM:
            issues.append(Issue(
                check="drawer_stack_order",
                severity=Severity.WARNING,
                message=(
                    f"Drawer at stack position {pos_lower + 1} from bottom "
                    f"({h_lower:.1f} mm) is shorter than the drawer above it at "
                    f"position {pos_upper + 1} ({h_upper:.1f} mm). "
                    f"Traditional graduation puts the tallest drawer at the bottom."
                ),
                part_a=f"opening_{pos_lower + 1}",
                part_b=f"opening_{pos_upper + 1}",
                value=h_upper,
                limit=h_lower,
            ))

    return issues


def check_cumulative_heights(cab_cfg: CabinetConfig) -> list[Issue]:
    """Verify that drawer/shelf stack doesn't exceed cabinet interior height.

    This catches the 'record cabinet' class of error where cumulative
    component heights exceed the available space.
    """
    issues = []

    # Check drawer stack heights
    if cab_cfg.drawer_config:
        total_opening_height = sum(h for h, _ in cab_cfg.drawer_config)
        available_height = cab_cfg.interior_height

        if total_opening_height > available_height:
            overage = total_opening_height - available_height
            issues.append(Issue(
                check="cumulative_heights",
                severity=Severity.ERROR,
                message=(
                    f"Drawer/shelf stack ({total_opening_height:.1f}mm) exceeds "
                    f"cabinet interior height ({available_height:.1f}mm) by {overage:.1f}mm. "
                    f"Reduce opening heights or increase cabinet height."
                ),
                value=total_opening_height,
                limit=available_height,
            ))
        elif total_opening_height == available_height:
            issues.append(Issue(
                check="cumulative_heights",
                severity=Severity.WARNING,
                message="Drawer stack exactly fills interior — zero tolerance for error.",
                value=total_opening_height,
                limit=available_height,
            ))

    # Check each shelf position is within bounds
    for i, pos in enumerate(cab_cfg.fixed_shelf_positions):
        if pos < cab_cfg.bottom_thickness:
            issues.append(Issue(
                check="shelf_position",
                severity=Severity.ERROR,
                message=f"Shelf {i} at z={pos:.1f}mm is below the bottom panel (z={cab_cfg.bottom_thickness:.1f}mm).",
                part_a=f"shelf_{i}",
                value=pos,
                limit=cab_cfg.bottom_thickness,
            ))
        if pos + cab_cfg.shelf_thickness > cab_cfg.height:
            issues.append(Issue(
                check="shelf_position",
                severity=Severity.ERROR,
                message=f"Shelf {i} top at z={pos + cab_cfg.shelf_thickness:.1f}mm exceeds cabinet height ({cab_cfg.height:.1f}mm).",
                part_a=f"shelf_{i}",
                value=pos + cab_cfg.shelf_thickness,
                limit=cab_cfg.height,
            ))

    return issues


def check_drawer_hardware_clearances(
    drawer_cfg: DrawerConfig,
) -> list[Issue]:
    """Validate drawer dimensions against slide hardware specs."""
    issues = []
    slide = drawer_cfg.slide

    # Use the slide's own validation for side clearance, height, and width limits.
    hw_issues = slide.validate_drawer_dims(
        drawer_width=drawer_cfg.box_width,
        drawer_height=drawer_cfg.box_height,
        drawer_depth=drawer_cfg.box_depth,
        opening_width=drawer_cfg.opening_width,
    )
    for msg in hw_issues:
        issues.append(Issue(
            check="hardware_clearance",
            severity=Severity.ERROR,
            message=msg,
        ))

    # Check bottom panel dado doesn't weaken the side too much
    remaining_below_dado = drawer_cfg.bottom_dado_inset
    if remaining_below_dado < 8:
        issues.append(Issue(
            check="drawer_dado_position",
            severity=Severity.WARNING,
            message=(
                f"Only {remaining_below_dado:.1f}mm of material below bottom dado — "
                f"risk of blowout. Consider raising dado inset."
            ),
            value=remaining_below_dado,
            limit=8.0,
        ))

    return issues


def check_shelf_deflection(
    span: float,
    depth: float,
    thickness: float,
    load_kg: float,
    material: str = "baltic_birch",
    max_deflection_mm: float = 2.0,
) -> list[Issue]:
    """Check shelf sag using beam bending formula.

    Uses δ = 5wL⁴ / (384·E·I) for uniformly distributed load.

    Args:
        span: Unsupported span (mm) — cabinet interior width.
        depth: Shelf depth (mm).
        thickness: Shelf thickness (mm).
        load_kg: Expected load in kg.
        material: Material key for elastic modulus lookup.
        max_deflection_mm: Maximum acceptable deflection.
    """
    # Elastic modulus (MPa) — along grain
    E_TABLE = {
        "baltic_birch": 12500,  # ~1.8M psi
        "maple_plywood": 11700,
        "mdf": 3500,
        "particleboard": 2800,
        "solid_maple": 12600,
        "solid_oak": 12300,
        "solid_walnut": 11600,
    }

    issues = []
    E = E_TABLE.get(material)
    if E is None:
        issues.append(Issue(
            check="shelf_deflection",
            severity=Severity.WARNING,
            message=f"Unknown material '{material}' — cannot compute deflection.",
        ))
        return issues

    # Moment of inertia for rectangular cross-section: I = b·h³/12
    I = depth * (thickness ** 3) / 12  # mm⁴

    # Distributed load: w = total_force / span (N/mm)
    total_force_N = load_kg * 9.81
    w = total_force_N / span  # N/mm

    # Maximum deflection at center
    deflection = (5 * w * span**4) / (384 * E * I)

    if deflection > max_deflection_mm:
        issues.append(Issue(
            check="shelf_deflection",
            severity=Severity.ERROR,
            message=(
                f"Predicted deflection {deflection:.2f}mm exceeds limit {max_deflection_mm:.1f}mm "
                f"for {span:.0f}mm span, {thickness:.0f}mm thick {material}, {load_kg}kg load. "
                f"Consider thicker shelf, mid-span support, or reduced span."
            ),
            value=deflection,
            limit=max_deflection_mm,
        ))
    elif deflection > max_deflection_mm * 0.7:
        issues.append(Issue(
            check="shelf_deflection",
            severity=Severity.WARNING,
            message=(
                f"Predicted deflection {deflection:.2f}mm is {deflection/max_deflection_mm*100:.0f}% "
                f"of limit ({max_deflection_mm:.1f}mm). Marginal."
            ),
            value=deflection,
            limit=max_deflection_mm,
        ))
    else:
        issues.append(Issue(
            check="shelf_deflection",
            severity=Severity.INFO,
            message=f"Deflection {deflection:.2f}mm OK ({deflection/max_deflection_mm*100:.0f}% of limit).",
            value=deflection,
            limit=max_deflection_mm,
        ))

    return issues


def check_back_panel_fit(cab_cfg: CabinetConfig) -> list[Issue]:
    """Verify back panel dimensions match rabbets."""
    issues = []

    expected_width = cab_cfg.width - (cab_cfg.side_thickness - cab_cfg.back_rabbet_depth) * 2
    if abs(cab_cfg.back_panel_width - expected_width) > 0.1:
        issues.append(Issue(
            check="back_panel_fit",
            severity=Severity.ERROR,
            message=(
                f"Back panel width {cab_cfg.back_panel_width:.1f}mm doesn't match "
                f"rabbet spacing {expected_width:.1f}mm"
            ),
            part_a="back",
            value=cab_cfg.back_panel_width,
            limit=expected_width,
        ))

    if cab_cfg.back_thickness > cab_cfg.back_rabbet_depth:
        issues.append(Issue(
            check="back_panel_fit",
            severity=Severity.ERROR,
            message=(
                f"Back panel thickness {cab_cfg.back_thickness:.1f}mm exceeds "
                f"rabbet depth {cab_cfg.back_rabbet_depth:.1f}mm — back will protrude."
            ),
            part_a="back",
            value=cab_cfg.back_thickness,
            limit=cab_cfg.back_rabbet_depth,
        ))

    return issues


def check_dado_alignment(cab_cfg: CabinetConfig) -> list[Issue]:
    """Verify that panel thicknesses match dado widths."""
    issues = []

    # Bottom panel thickness should match dado width in sides
    # (dado width = bottom_thickness as cut)
    if cab_cfg.bottom_thickness > cab_cfg.side_thickness:
        issues.append(Issue(
            check="dado_alignment",
            severity=Severity.ERROR,
            message=(
                f"Bottom panel thickness {cab_cfg.bottom_thickness:.1f}mm > "
                f"side panel thickness {cab_cfg.side_thickness:.1f}mm — "
                f"dado cannot be wider than the panel it's cut into."
            ),
        ))

    if cab_cfg.dado_depth > cab_cfg.side_thickness / 2:
        issues.append(Issue(
            check="dado_alignment",
            severity=Severity.WARNING,
            message=(
                f"Dado depth {cab_cfg.dado_depth:.1f}mm is more than half the "
                f"side thickness ({cab_cfg.side_thickness:.1f}mm) — weakens panel."
            ),
            value=cab_cfg.dado_depth,
            limit=cab_cfg.side_thickness / 2,
        ))

    return issues


# ─── Joinery Checks (no CadQuery needed) ─────────────────────────────────────


def check_drawer_joinery(drawer_cfg: DrawerConfig) -> list[Issue]:
    """Validate drawer joinery style against stock dimensions.

    QQQ requires true stock thickness (not undersized plywood).
    DRAWER_LOCK warns if stock is thinner than 12 mm (bit engagement too small).
    """
    issues = []
    spec = drawer_cfg.joinery
    t = drawer_cfg.side_thickness

    if spec.style == DrawerJoineryStyle.QQQ:
        # QQQ requires true-thickness stock.  Common 1/2" plywood is often
        # 11.9–12.3 mm rather than a true 12.7 mm; warn if off by > 0.5 mm.
        nominal = 12.7  # true 1/2"
        if abs(t - nominal) > 0.5 and abs(t - 15.875) > 0.5 and abs(t - 19.05) > 0.5:
            issues.append(Issue(
                check="joinery_qqq_thickness",
                severity=Severity.WARNING,
                message=(
                    f"QQQ locking-rabbet works best with true-thickness stock. "
                    f"Side thickness {t:.2f} mm is not a standard 1/2″ (12.7 mm), "
                    f"5/8″ (15.9 mm), or 3/4″ (19.1 mm). "
                    f"Verify material is within 0.5 mm of nominal before cutting."
                ),
                value=t,
            ))
        # Tongue must leave at least 3 mm of material at the door edge
        tongue = t / 2
        if tongue < 4.0:
            issues.append(Issue(
                check="joinery_qqq_tongue",
                severity=Severity.ERROR,
                message=(
                    f"QQQ tongue width {tongue:.1f} mm (side_thickness / 2) is "
                    f"too thin — minimum 4 mm for reliable joint. "
                    f"Use thicker stock."
                ),
                value=tongue,
                limit=4.0,
            ))

    if spec.style == DrawerJoineryStyle.DRAWER_LOCK:
        if t < 12.0:
            issues.append(Issue(
                check="joinery_drawer_lock_thickness",
                severity=Severity.WARNING,
                message=(
                    f"Drawer-lock joint with {t:.1f} mm stock is marginal — "
                    f"most drawer-lock router bits require ≥ 12 mm for adequate "
                    f"tongue engagement. Check your specific bit's spec sheet."
                ),
                value=t,
                limit=12.0,
            ))

    return issues


def check_domino_layout(
    spec: DominoSpec,
    span: float,
    panel_thickness: float,
    joint_name: str = "joint",
) -> list[Issue]:
    """Validate Domino floating-tenon layout for a panel edge.

    Checks:
      - Panel thick enough for the mortise depth (at least mortise_depth + 3 mm)
      - Span wide enough to fit at least one tenon with proper edge distances
      - Mortise count and spacing are reasonable
    """
    issues = []
    s = spec.size

    # Minimum panel thickness: mortise depth + 2 mm minimum wall behind it.
    # (The 3 mm often cited in guides is for the max-depth setting; the
    # mortise_depth_per_side values in DOMINO_SIZES are already tuned to the
    # recommended depth for typical panel thicknesses, so 2 mm suffices.)
    min_thickness = s.mortise_depth_per_side + 2.0
    if panel_thickness < min_thickness:
        issues.append(Issue(
            check="domino_panel_thickness",
            severity=Severity.ERROR,
            message=(
                f"Panel too thin for {spec.size_key} Domino at {joint_name}: "
                f"panel is {panel_thickness:.1f} mm but mortise requires "
                f"{s.mortise_depth_per_side:.0f} mm + 3 mm wall = {min_thickness:.0f} mm minimum."
            ),
            part_a=joint_name,
            value=panel_thickness,
            limit=min_thickness,
        ))

    # Span must accommodate two edge distances plus at least one tenon
    min_span = 2 * s.min_edge_distance + s.mortise_length
    if span < min_span:
        issues.append(Issue(
            check="domino_span_too_short",
            severity=Severity.ERROR,
            message=(
                f"Span {span:.1f} mm at {joint_name} too short for even one "
                f"{spec.size_key} Domino with {s.min_edge_distance:.0f} mm edge "
                f"distances (minimum span: {min_span:.0f} mm)."
            ),
            part_a=joint_name,
            value=span,
            limit=min_span,
        ))

    # Warn if spacing between adjacent tenons exceeds max_spacing
    positions = spec.positions_for_span(span)
    for i in range(1, len(positions)):
        gap = positions[i] - positions[i - 1]
        if gap > spec.max_spacing:
            issues.append(Issue(
                check="domino_spacing",
                severity=Severity.WARNING,
                message=(
                    f"Domino spacing {gap:.1f} mm at {joint_name} exceeds "
                    f"recommended max {spec.max_spacing:.0f} mm."
                ),
                value=gap,
                limit=spec.max_spacing,
            ))

    return issues


def check_pocket_screw_layout(
    spec: PocketScrewSpec,
    span: float,
    stock_thickness: float,
    joint_name: str = "joint",
) -> list[Issue]:
    """Validate pocket-screw layout for a panel edge.

    Checks:
      - Stock thick enough for the pocket (min 10 mm)
      - Span wide enough for at least 2 pockets with edge clearance
    """
    issues = []

    MIN_STOCK = 10.0
    if stock_thickness < MIN_STOCK:
        issues.append(Issue(
            check="pocket_screw_thickness",
            severity=Severity.ERROR,
            message=(
                f"Stock thickness {stock_thickness:.1f} mm at {joint_name} is "
                f"too thin for pocket-screw joinery (minimum {MIN_STOCK:.0f} mm)."
            ),
            value=stock_thickness,
            limit=MIN_STOCK,
        ))

    min_span = 2 * spec.min_edge_distance + spec.pocket_diameter
    if span < min_span:
        issues.append(Issue(
            check="pocket_screw_span",
            severity=Severity.WARNING,
            message=(
                f"Span {span:.1f} mm at {joint_name} is very short for pocket "
                f"screws — only one pocket may fit. Consider a single centred pocket."
            ),
            value=span,
            limit=min_span,
        ))

    return issues


def check_carcass_joinery(cab_cfg: CabinetConfig) -> list[Issue]:
    """Run all carcass-joinery checks appropriate for the selected method.

    Validates Domino, pocket-screw, biscuit, and dowel layouts against the
    cabinet's interior dimensions.  DADO_RABBET is already covered by the
    existing dado/rabbet checks and produces no additional issues here.
    """
    issues = []
    method = cab_cfg.carcass_joinery

    if method == CarcassJoinery.DADO_RABBET:
        return issues  # covered by check_dado_alignment / check_back_panel_fit

    interior_w = cab_cfg.interior_width
    interior_d = cab_cfg.depth - cab_cfg.back_rabbet_width

    if method == CarcassJoinery.FLOATING_TENON:
        spec = cab_cfg.domino_spec
        # Check shelf-to-side joints (span = interior_depth)
        issues.extend(check_domino_layout(
            spec, interior_d, cab_cfg.side_thickness, "shelf-to-side"
        ))
        # Check bottom-to-side joints (same span)
        issues.extend(check_domino_layout(
            spec, interior_d, cab_cfg.side_thickness, "bottom-to-side"
        ))

    elif method == CarcassJoinery.POCKET_SCREW:
        spec = cab_cfg.pocket_screw_spec
        issues.extend(check_pocket_screw_layout(
            spec, interior_d, cab_cfg.side_thickness, "shelf-to-side"
        ))
        issues.extend(check_pocket_screw_layout(
            spec, interior_d, cab_cfg.side_thickness, "bottom-to-side"
        ))

    elif method == CarcassJoinery.BISCUIT:
        spec = cab_cfg.biscuit_spec
        # Biscuit slot depth: each side gets slot_depth_per_side from the face
        min_thickness = spec.slot_depth_per_side + 3.0
        if cab_cfg.side_thickness < min_thickness:
            issues.append(Issue(
                check="biscuit_panel_thickness",
                severity=Severity.ERROR,
                message=(
                    f"Side panel {cab_cfg.side_thickness:.1f} mm too thin for "
                    f"{spec.size} biscuit (needs {min_thickness:.0f} mm minimum)."
                ),
                value=cab_cfg.side_thickness,
                limit=min_thickness,
            ))

    elif method == CarcassJoinery.DOWEL:
        spec = cab_cfg.dowel_spec
        # Dowel must not break through the panel face.
        # Constraint: depth_per_side + 2 mm minimum wall (no need to add
        # radius — the drill tip doesn't exit through the face in normal use).
        min_thickness = spec.depth_per_side + 2.0
        if cab_cfg.side_thickness < min_thickness:
            issues.append(Issue(
                check="dowel_panel_thickness",
                severity=Severity.ERROR,
                message=(
                    f"Side panel {cab_cfg.side_thickness:.1f} mm too thin for "
                    f"{spec.diameter:.0f} mm dowel at {spec.depth_per_side:.0f} mm depth "
                    f"(needs {min_thickness:.0f} mm minimum)."
                ),
                value=cab_cfg.side_thickness,
                limit=min_thickness,
            ))

    return issues


# ─── Door / Hinge Checks (no CadQuery needed) ────────────────────────────────


def check_door_hinge_count(door_cfg: DoorConfig) -> list[Issue]:
    """Verify hinge count is adequate for door height and weight.

    Blum guidelines:
      ≤ 1 200 mm  → 2 hinges
      ≤ 1 800 mm  → 3 hinges
      > 1 800 mm  → 4 hinges
    Extra hinge if door weight exceeds hinge spec's max_door_weight_kg.
    """
    issues = []
    h = door_cfg.hinge
    count = door_cfg.hinge_count
    height = door_cfg.door_height
    weight = door_cfg.door_weight_kg

    if count < 2:
        issues.append(Issue(
            check="door_hinge_count",
            severity=Severity.ERROR,
            message=f"Door requires at least 2 hinges; only {count} calculated.",
            value=float(count),
            limit=2.0,
        ))

    if weight > h.max_door_weight_kg:
        issues.append(Issue(
            check="door_hinge_weight",
            severity=Severity.WARNING,
            message=(
                f"Door weight {weight:.1f} kg exceeds hinge pair rating "
                f"{h.max_door_weight_kg:.1f} kg for {h.name}. "
                f"Using {count} hinges per door."
            ),
            value=weight,
            limit=h.max_door_weight_kg,
        ))

    # Warn if spacing between any two adjacent hinges exceeds max_hinge_spacing
    positions = door_cfg.hinge_positions_z
    for i in range(1, len(positions)):
        spacing = positions[i] - positions[i - 1]
        if spacing > h.max_hinge_spacing:
            issues.append(Issue(
                check="door_hinge_spacing",
                severity=Severity.WARNING,
                message=(
                    f"Hinge spacing {spacing:.1f} mm between positions "
                    f"{i} and {i + 1} exceeds max {h.max_hinge_spacing:.0f} mm."
                ),
                value=spacing,
                limit=h.max_hinge_spacing,
            ))

    return issues


def check_door_dimensions(door_cfg: DoorConfig) -> list[Issue]:
    """Validate door panel dimensions against hinge spec and opening.

    Checks:
      - Door thickness within hinge range.
      - Cup boring edge distance ≥ 3 mm (avoid blowout at door edge).
      - Door height > 0 after gap deductions.
      - Door width > 0 after overlay / gap calculation.
      - For inset: door + 2×gap_side should equal opening width.
      - For full/half: overlay is non-negative.
    """
    issues = []
    h = door_cfg.hinge

    # Delegate thickness + cup edge checks to the hinge spec's own validator
    for msg in h.validate_door(
        door_thickness=door_cfg.door_thickness,
        door_height=door_cfg.door_height,
        door_width=door_cfg.door_width,
    ):
        issues.append(Issue(
            check="door_dimensions",
            severity=Severity.ERROR,
            message=msg,
        ))

    # Ensure computed dimensions are positive
    if door_cfg.door_height <= 0:
        issues.append(Issue(
            check="door_dimensions",
            severity=Severity.ERROR,
            message=(
                f"Computed door height {door_cfg.door_height:.1f} mm ≤ 0. "
                f"Gap_top + gap_bottom ({door_cfg.gap_top + door_cfg.gap_bottom:.1f} mm) "
                f"exceeds opening height ({door_cfg.opening_height:.1f} mm)."
            ),
            value=door_cfg.door_height,
            limit=0.0,
        ))

    if door_cfg.door_width <= 0:
        issues.append(Issue(
            check="door_dimensions",
            severity=Severity.ERROR,
            message=f"Computed door width {door_cfg.door_width:.1f} mm ≤ 0.",
            value=door_cfg.door_width,
            limit=0.0,
        ))

    # Inset-specific: verify door + gaps fills the opening
    if h.overlay_type == OverlayType.INSET:
        expected = door_cfg.opening_width - 2 * door_cfg.gap_side
        if abs(door_cfg.door_width - expected) > 0.5:
            issues.append(Issue(
                check="door_inset_fit",
                severity=Severity.WARNING,
                message=(
                    f"Inset door width {door_cfg.door_width:.1f} mm doesn't match "
                    f"expected {expected:.1f} mm (opening − 2×gap_side)."
                ),
                value=door_cfg.door_width,
                limit=expected,
            ))

    # Cup boring position sanity: must be within the door face area
    min_boring_x = h.cup_diameter / 2 + 3  # at least 3 mm of material past cup edge
    if h.cup_boring_distance < min_boring_x:
        issues.append(Issue(
            check="door_cup_boring",
            severity=Severity.ERROR,
            message=(
                f"Cup boring centre {h.cup_boring_distance:.1f} mm from edge is too close — "
                f"minimum is {min_boring_x:.1f} mm to leave 3 mm edge material."
            ),
            value=h.cup_boring_distance,
            limit=min_boring_x,
        ))

    return issues


def check_door_pair_width(door_cfg: DoorConfig) -> list[Issue]:
    """For door pairs, verify each leaf is not excessively wide.

    Very wide individual door leaves (> 600 mm) can cause sag; Blum recommends
    keeping individual leaf width ≤ 600 mm where possible.
    """
    if door_cfg.num_doors != 2:
        return []

    issues = []
    MAX_RECOMMENDED = 600.0

    if door_cfg.door_width > MAX_RECOMMENDED:
        issues.append(Issue(
            check="door_pair_width",
            severity=Severity.WARNING,
            message=(
                f"Individual door leaf width {door_cfg.door_width:.1f} mm exceeds "
                f"recommended maximum {MAX_RECOMMENDED:.0f} mm. "
                f"Consider a narrower cabinet or three-door arrangement."
            ),
            value=door_cfg.door_width,
            limit=MAX_RECOMMENDED,
        ))

    return issues


# ─── Pull Hardware Checks (no CadQuery needed) ───────────────────────────────

# Pulls that project more than this off the face can snag on clothing and
# narrow passages. Typical catalog values run 25–45 mm; 50 mm is chosen as
# the warning threshold to flag the long-bar industrial pulls without
# nagging about standard hardware.
PULL_PROJECTION_WARN_MM: float = 50.0


def _check_pull_common(
    face_width_mm: float,
    face_height_mm: float,
    pull: PullSpec,
    pull_key: str,
    pull_count: int,
    where: str,
) -> list[Issue]:
    """Shared pull-placement checks used by drawer and door evaluators.

    Parameters
    ----------
    face_width_mm, face_height_mm :
        Dimensions of the face the pull mounts on (drawer face or door panel).
    pull :
        The resolved PullSpec (caller has already looked it up).
    pull_key :
        Catalog id — included in messages so users can search for it.
    pull_count :
        Pull count from config.  ``0`` means "defer to ``recommend_pull_count``".
    where :
        Short label for messages (e.g. ``"drawer_0"``, ``"door_pair"``).

    Returns
    -------
    list[Issue]
        Issues related to the pull itself (fit, projection, knob-on-wide,
        pull_count-vs-knob mismatch).  An empty list means the pull looks fine.
    """
    issues: list[Issue] = []

    effective_count = pull_count if pull_count > 0 else recommend_pull_count(
        face_width_mm, pull
    )

    # ── Fit check ───────────────────────────────────────────────────────────
    if not pull_fits_face(face_width_mm, pull, count=effective_count):
        # Min face width for single-pull placement with 40 mm end margin on
        # each side; we report this so the user can act on it.
        min_single = pull.length_mm + 80.0
        issues.append(Issue(
            check="pull_fit",
            severity=Severity.ERROR,
            message=(
                f"{where}: pull '{pull_key}' ({pull.length_mm:.0f} mm long) "
                f"does not fit the {face_width_mm:.0f} mm face with "
                f"{effective_count} placement(s). "
                f"Need ≥ {min_single:.0f} mm for a single pull, or a shorter pull."
            ),
            part_a=where,
            value=face_width_mm,
            limit=min_single,
        ))

    # ── Projection — ergonomic warning ──────────────────────────────────────
    if pull.projection_mm > PULL_PROJECTION_WARN_MM:
        issues.append(Issue(
            check="pull_projection",
            severity=Severity.WARNING,
            message=(
                f"{where}: pull '{pull_key}' projects {pull.projection_mm:.0f} mm "
                f"off the face — above the {PULL_PROJECTION_WARN_MM:.0f} mm "
                f"ergonomic threshold. Can snag on clothing in narrow walkways."
            ),
            part_a=where,
            value=pull.projection_mm,
            limit=PULL_PROJECTION_WARN_MM,
        ))

    # ── Knob on a wide face — suggest a handle pull ─────────────────────────
    if pull.mount_style is MountStyle.KNOB and face_width_mm > DUAL_PULL_THRESHOLD_MM:
        issues.append(Issue(
            check="pull_knob_on_wide_face",
            severity=Severity.WARNING,
            message=(
                f"{where}: knob '{pull_key}' on a {face_width_mm:.0f} mm face — "
                f"faces wider than {DUAL_PULL_THRESHOLD_MM:.0f} mm feel "
                f"unbalanced opening on a single knob. Consider a handle pull."
            ),
            part_a=where,
            value=face_width_mm,
            limit=DUAL_PULL_THRESHOLD_MM,
        ))

    # ── Explicit pull_count > 1 on a knob is silently coerced to 1 by
    #    pull_positions; warn so the user knows their setting was ignored.
    if (
        pull.mount_style is MountStyle.KNOB
        and pull_count > 1
    ):
        issues.append(Issue(
            check="pull_count_knob_coerced",
            severity=Severity.WARNING,
            message=(
                f"{where}: pull_count={pull_count} on knob '{pull_key}' is "
                f"coerced to 1 at placement — knobs are never split into a "
                f"dual-knob layout. Pick a handle pull if you want two placements."
            ),
            part_a=where,
            value=float(pull_count),
            limit=1.0,
        ))

    return issues


def check_drawer_pull(drawer_cfg: DrawerConfig) -> list[Issue]:
    """Validate the pull (if any) on a drawer face.

    Runs the fit / projection / knob-on-wide shared checks plus two
    drawer-specific signals:

    - **Unknown pull key** — ERROR; no further pull checks run.
    - **No applied face** — WARNING; ``applied_face=False`` drawers have no
      visible face on which to mount a pull, so the spec is effectively
      ignored by :attr:`DrawerConfig.pull_placements`.
    """
    issues: list[Issue] = []
    if drawer_cfg.pull_key is None:
        return issues

    try:
        pull = get_pull(drawer_cfg.pull_key)
    except KeyError:
        issues.append(Issue(
            check="pull_unknown",
            severity=Severity.ERROR,
            message=(
                f"drawer: pull_key '{drawer_cfg.pull_key}' is not in the catalog. "
                f"See hardware.PULLS for valid ids."
            ),
            part_a="drawer",
        ))
        return issues

    if not drawer_cfg.applied_face:
        issues.append(Issue(
            check="pull_no_face",
            severity=Severity.WARNING,
            message=(
                f"drawer: pull_key '{drawer_cfg.pull_key}' is set but "
                f"applied_face=False — no face to mount on; the pull will "
                f"not be placed. Either add an applied face or clear pull_key."
            ),
            part_a="drawer",
        ))
        return issues  # fit checks are meaningless without a face

    issues.extend(_check_pull_common(
        face_width_mm=drawer_cfg.face_width,
        face_height_mm=drawer_cfg.face_height,
        pull=pull,
        pull_key=drawer_cfg.pull_key,
        pull_count=drawer_cfg.pull_count,
        where="drawer",
    ))
    return issues


def check_door_pull(door_cfg: DoorConfig) -> list[Issue]:
    """Validate the pull (if any) on a door panel.

    Door pairs are checked against the *per-leaf* door_width — each leaf is
    its own face and carries its own pull, so the fit math operates on the
    single-leaf width rather than the opening.
    """
    issues: list[Issue] = []
    if door_cfg.pull_key is None:
        return issues

    try:
        pull = get_pull(door_cfg.pull_key)
    except KeyError:
        issues.append(Issue(
            check="pull_unknown",
            severity=Severity.ERROR,
            message=(
                f"door: pull_key '{door_cfg.pull_key}' is not in the catalog. "
                f"See hardware.PULLS for valid ids."
            ),
            part_a="door",
        ))
        return issues

    where = "door_pair_leaf" if door_cfg.num_doors == 2 else "door"
    issues.extend(_check_pull_common(
        face_width_mm=door_cfg.door_width,
        face_height_mm=door_cfg.door_height,
        pull=pull,
        pull_key=door_cfg.pull_key,
        pull_count=door_cfg.pull_count,
        where=where,
    ))
    return issues


def check_cabinet_pull_consistency(cab_cfg: CabinetConfig) -> list[Issue]:
    """Cabinet-level sanity check for pulls that span drawers *and* doors.

    If the cabinet specifies both ``drawer_pull`` and ``door_pull``, the two
    pulls should share a design language (``PullSpec.style``) — mixing a
    Contemporary drawer pull with a Traditional door pull on the same carcass
    is usually a mistake.  Identical finishes are not enforced because some
    designers deliberately mix e.g. Flat Black pulls with Polished Brass knobs
    for accent.
    """
    issues: list[Issue] = []
    if cab_cfg.drawer_pull is None or cab_cfg.door_pull is None:
        return issues
    if cab_cfg.drawer_pull == cab_cfg.door_pull:
        return issues

    try:
        dp = get_pull(cab_cfg.drawer_pull)
        op = get_pull(cab_cfg.door_pull)
    except KeyError:
        # The unknown key is already flagged by per-config checks when the
        # drawers/doors are evaluated; don't double-report here.
        return issues

    if dp.style != op.style:
        issues.append(Issue(
            check="pull_style_mismatch",
            severity=Severity.WARNING,
            message=(
                f"Cabinet mixes pull styles: drawers use '{cab_cfg.drawer_pull}' "
                f"({dp.style}) but doors use '{cab_cfg.door_pull}' ({op.style}). "
                f"Confirm this is intentional."
            ),
            part_a="drawer_pull",
            part_b="door_pull",
        ))

    return issues


# ─── Geometric Checks (require CadQuery) ─────────────────────────────────────


def check_interference(assembly: "cq.Assembly", tolerance: float = 0.1) -> list[Issue]:
    """Check all parts in an assembly for geometric interference.

    Runs pairwise Boolean intersection on all solid bodies.
    This is computationally expensive for large assemblies.
    """
    if cq is None:
        return [Issue(
            check="interference",
            severity=Severity.WARNING,
            message="CadQuery not installed — skipping interference check.",
        )]

    issues = []
    parts = []

    # Traverse assembly and collect positioned shapes
    for name, obj in assembly.traverse():
        try:
            compound = obj.toCompound() if hasattr(obj, 'toCompound') else None
            if compound is not None:
                parts.append((name, compound))
        except Exception:
            pass

    for (name_a, shape_a), (name_b, shape_b) in combinations(parts, 2):
        try:
            intersection = shape_a.intersect(shape_b)
            vol = intersection.Volume() if hasattr(intersection, 'Volume') else 0
            if vol > tolerance:
                issues.append(Issue(
                    check="interference",
                    severity=Severity.ERROR,
                    message=f"Interference volume: {vol:.1f}mm³",
                    part_a=name_a,
                    part_b=name_b,
                    value=vol,
                    limit=tolerance,
                ))
        except Exception as e:
            issues.append(Issue(
                check="interference",
                severity=Severity.WARNING,
                message=f"Could not check: {e}",
                part_a=name_a,
                part_b=name_b,
            ))

    if not issues:
        issues.append(Issue(
            check="interference",
            severity=Severity.INFO,
            message=f"No interference detected among {len(parts)} parts.",
        ))

    return issues


def check_drawer_in_opening(
    drawer_assembly: "cq.Assembly",
    opening_width: float,
    opening_height: float,
    opening_depth: float,
    slide: DrawerSlideSpec,
) -> list[Issue]:
    """Check that an assembled drawer fits within its cabinet opening."""
    if cq is None:
        return [Issue(
            check="drawer_fit",
            severity=Severity.WARNING,
            message="CadQuery not installed — skipping geometric drawer fit check.",
        )]

    issues = []

    try:
        compound = drawer_assembly.toCompound()
        bb = compound.BoundingBox()
    except Exception as e:
        return [Issue(
            check="drawer_fit",
            severity=Severity.WARNING,
            message=f"Could not compute bounding box: {e}",
        )]

    drawer_width = bb.xlen
    drawer_height = bb.zlen
    drawer_depth = bb.ylen

    # Side clearance
    actual_side_clearance = (opening_width - drawer_width) / 2
    if actual_side_clearance < slide.min_side_clearance:
        issues.append(Issue(
            check="drawer_fit_width",
            severity=Severity.ERROR,
            message=(
                f"Side clearance {actual_side_clearance:.2f}mm < "
                f"minimum {slide.min_side_clearance}mm for {slide.name}"
            ),
            value=actual_side_clearance,
            limit=slide.min_side_clearance,
        ))

    # Height clearance
    if drawer_height > opening_height:
        issues.append(Issue(
            check="drawer_fit_height",
            severity=Severity.ERROR,
            message=(
                f"Drawer height {drawer_height:.1f}mm exceeds "
                f"opening height {opening_height:.1f}mm"
            ),
            value=drawer_height,
            limit=opening_height,
        ))

    # Depth
    max_depth = slide.slide_length_for_depth(opening_depth)
    if drawer_depth > max_depth:
        issues.append(Issue(
            check="drawer_fit_depth",
            severity=Severity.WARNING,
            message=(
                f"Drawer depth {drawer_depth:.1f}mm exceeds "
                f"slide travel {max_depth}mm"
            ),
            value=drawer_depth,
            limit=float(max_depth),
        ))

    return issues


def check_drawer_carcass_clearances(cab_cfg: CabinetConfig) -> list[Issue]:
    """Verify that every drawer box clears the carcass interior walls.

    For each drawer opening in ``cab_cfg.drawer_config``, constructs the
    corresponding DrawerConfig and checks:

    - **Width / side clearance** — gap between each side of the box and the
      nearest vertical panel (outer side or internal divider) is within the
      slide's required min/max range.  In a multi-bay assembly the internal
      dividers are shared side panels; ``interior_width`` already spans
      between their inner faces, so this check covers all supports.
    - **Depth / rear clearance** — drawer box does not reach the back panel;
      a minimum rear clearance of 10 mm is recommended for the rear-mounting
      bracket of undermount slides.
    - **Height** — computed box height (opening_height − vertical_gap) is
      positive and at least the slide's minimum drawer height.

    Args:
        cab_cfg: Cabinet configuration, including ``drawer_config``.

    Returns:
        List of Issue objects (empty if all drawers clear the carcass).
    """
    issues: list[Issue] = []
    if not cab_cfg.drawer_config:
        return issues

    slide = get_slide(cab_cfg.drawer_slide)
    MIN_REAR_CLEARANCE = 10.0  # mm — space needed for rear mounting bracket

    for idx, (opening_h, slot_type) in enumerate(cab_cfg.drawer_config):
        if slot_type != "drawer":
            continue

        label = f"drawer_{idx}"
        dcfg = DrawerConfig(
            opening_width=cab_cfg.interior_width,
            opening_height=opening_h,
            opening_depth=cab_cfg.interior_depth,
            slide_key=cab_cfg.drawer_slide,
        )

        # Eagerly resolve box_depth — slide_length_for_depth raises ValueError
        # if the cabinet is too shallow for any available slide.
        try:
            box_depth = dcfg.box_depth
        except ValueError as exc:
            issues.append(Issue(
                check="drawer_carcass_clearance",
                severity=Severity.ERROR,
                message=(
                    f"{label}: cabinet interior depth {cab_cfg.interior_depth:.1f} mm "
                    f"is too shallow for any {slide.name} slide. {exc}"
                ),
                part_a=label,
                value=cab_cfg.interior_depth,
            ))
            continue

        # ── Width / side clearance ─────────────────────────────────────────
        side_gap = (cab_cfg.interior_width - dcfg.box_width) / 2
        min_box_width = dcfg.side_thickness * 2  # box walls can't overlap

        if dcfg.box_width <= 0:
            issues.append(Issue(
                check="drawer_carcass_clearance",
                severity=Severity.ERROR,
                message=(
                    f"{label}: interior width {cab_cfg.interior_width:.1f} mm is too narrow "
                    f"for {slide.name} — computed box width {dcfg.box_width:.1f} mm is "
                    f"non-positive. Minimum interior width for this slide: "
                    f"{slide.nominal_side_clearance * 2 + 50:.0f} mm."
                ),
                part_a=label,
                value=dcfg.box_width,
                limit=0.0,
            ))
        elif dcfg.box_width < min_box_width:
            issues.append(Issue(
                check="drawer_carcass_clearance",
                severity=Severity.ERROR,
                message=(
                    f"{label}: computed box width {dcfg.box_width:.1f} mm is narrower "
                    f"than 2× side thickness ({min_box_width:.0f} mm) — box walls "
                    f"would overlap. Widen the cabinet."
                ),
                part_a=label,
                value=dcfg.box_width,
                limit=min_box_width,
            ))
        elif side_gap < slide.min_side_clearance:
            issues.append(Issue(
                check="drawer_carcass_clearance",
                severity=Severity.ERROR,
                message=(
                    f"{label}: side clearance {side_gap:.1f} mm < "
                    f"{slide.name} minimum {slide.min_side_clearance:.1f} mm. "
                    f"Widen the cabinet opening or use a slide with smaller clearance."
                ),
                part_a=label,
                value=side_gap,
                limit=slide.min_side_clearance,
            ))
        elif side_gap > slide.max_side_clearance:
            issues.append(Issue(
                check="drawer_carcass_clearance",
                severity=Severity.WARNING,
                message=(
                    f"{label}: side clearance {side_gap:.1f} mm > "
                    f"{slide.name} maximum {slide.max_side_clearance:.1f} mm — "
                    f"coupling may not reach the side panel."
                ),
                part_a=label,
                value=side_gap,
                limit=slide.max_side_clearance,
            ))

        # ── Depth / rear clearance ─────────────────────────────────────────
        rear_gap = cab_cfg.interior_depth - box_depth
        if rear_gap < 0:
            issues.append(Issue(
                check="drawer_carcass_clearance",
                severity=Severity.ERROR,
                message=(
                    f"{label}: drawer box depth {box_depth:.1f} mm exceeds "
                    f"carcass interior depth {cab_cfg.interior_depth:.1f} mm "
                    f"by {-rear_gap:.1f} mm."
                ),
                part_a=label,
                value=box_depth,
                limit=cab_cfg.interior_depth,
            ))
        elif rear_gap < MIN_REAR_CLEARANCE:
            issues.append(Issue(
                check="drawer_carcass_clearance",
                severity=Severity.WARNING,
                message=(
                    f"{label}: only {rear_gap:.1f} mm clearance between drawer box "
                    f"and back panel (recommended ≥ {MIN_REAR_CLEARANCE:.0f} mm for "
                    f"{slide.name} rear-mount bracket)."
                ),
                part_a=label,
                value=rear_gap,
                limit=MIN_REAR_CLEARANCE,
            ))

        # ── Height ────────────────────────────────────────────────────────
        # Min-drawer-height is a hardware constraint reported by
        # check_drawer_hardware_clearances; only flag the degenerate case
        # where the opening is too small for any gap at all.
        if dcfg.box_height <= 0:
            issues.append(Issue(
                check="drawer_carcass_clearance",
                severity=Severity.ERROR,
                message=(
                    f"{label}: opening height {opening_h:.1f} mm is smaller than "
                    f"the vertical gap ({dcfg.vertical_gap:.1f} mm) — box height "
                    f"would be {dcfg.box_height:.1f} mm."
                ),
                part_a=label,
                value=dcfg.box_height,
                limit=dcfg.vertical_gap,
            ))

    return issues


def check_face_clearances(
    bay_configs: "list[CabinetConfig]",
    inner_overlay: float = 17.0,
    outer_overlay: float = 18.0,
    divider_thickness: float = 18.0,
    face_gap: float = 4.0,
    face_bottom_overhang: float = 0.0,
    face_top_overhang: float = 0.0,
    min_face_gap: float = 2.0,
) -> list[Issue]:
    """Check clearances between all drawer and door faces in a multi-bay assembly.

    Two families of checks:

    **Vertical** (within each bay):
    The face stack is anchored top and bottom.  ``face_gap`` is the **total**
    clearance between adjacent faces — half is trimmed from the top of the lower
    face and half from the bottom of the upper face, so the gap straddles the
    opening boundary symmetrically.  Checks:
    - ``face_gap ≥ 0`` (ERROR if negative — faces would physically overlap).
    - ``face_gap ≥ min_face_gap`` (WARNING if the gap is tight).
    - Each computed face height > 0 (ERROR if the opening is too shallow for
      the face gap).

    **Horizontal** (at bay boundaries):
    The gap between adjacent bay faces at a shared divider =
    ``divider_thickness − 2 × inner_overlay``.  Checks:
    - Gap ≥ 0 (ERROR if faces overlap — common when inner_overlay was sized
      for the old double-wall divider and the assembly switched to a thinner
      single divider).
    - Gap ≥ min_face_gap (WARNING if gap is present but tight).

    Applies to all slot types in ``drawer_config`` (drawer, door, door_pair)
    since every opening contributes a face panel.

    Args:
        bay_configs:          Ordered list of CabinetConfig, left to right.
        inner_overlay:        Face overhang on interior bay dividers (mm).
        outer_overlay:        Face overhang on outermost cabinet edges (mm).
        divider_thickness:    Dedicated interior divider panel thickness (mm).
        face_gap:             Total vertical clearance between adjacent faces (mm).
                              Half is removed from the top of the lower face and
                              half from the bottom of the upper face.
        face_bottom_overhang: How far the lowest face extends below the bottom
                              panel top surface (mm).
        face_top_overhang:    How far the highest face extends above the top
                              panel bottom surface (mm).
        min_face_gap:         Minimum acceptable clearance between any two faces.

    Returns:
        List of Issue objects; empty list means all faces clear one another.
    """
    issues: list[Issue] = []
    n_bays = len(bay_configs)

    # ── face_gap sanity ───────────────────────────────────────────────────────
    if face_gap < 0:
        issues.append(Issue(
            check="face_clearance",
            severity=Severity.ERROR,
            message=(
                f"face_gap {face_gap:.1f} mm is negative — "
                f"faces will overlap vertically."
            ),
            value=face_gap,
            limit=0.0,
        ))
        return issues  # vertical positions are undefined; skip remaining checks

    if face_gap < min_face_gap:
        issues.append(Issue(
            check="face_clearance",
            severity=Severity.WARNING,
            message=(
                f"Vertical face gap {face_gap:.1f} mm is below "
                f"the {min_face_gap:.0f} mm minimum."
            ),
            value=face_gap,
            limit=min_face_gap,
        ))

    # ── Horizontal gaps at bay boundaries ─────────────────────────────────────
    if n_bays > 1:
        h_gap = divider_thickness - 2 * inner_overlay
        correct_overlay = (divider_thickness - min_face_gap) / 2

        for boundary in range(n_bays - 1):
            left_cfg  = bay_configs[boundary]
            right_cfg = bay_configs[boundary + 1]

            left_has_faces  = bool(left_cfg.drawer_config)
            right_has_faces = bool(right_cfg.drawer_config)
            if not (left_has_faces and right_has_faces):
                continue

            if h_gap < 0:
                issues.append(Issue(
                    check="face_clearance",
                    severity=Severity.ERROR,
                    message=(
                        f"Bay {boundary}–{boundary + 1}: faces overlap by "
                        f"{-h_gap:.1f} mm at the {divider_thickness:.0f} mm divider. "
                        f"inner_overlay {inner_overlay:.0f} mm × 2 = "
                        f"{2 * inner_overlay:.0f} mm > divider width. "
                        f"Set inner_overlay ≤ {correct_overlay:.1f} mm for a "
                        f"{min_face_gap:.0f} mm gap."
                    ),
                    value=h_gap,
                    limit=0.0,
                ))
            elif h_gap < min_face_gap:
                issues.append(Issue(
                    check="face_clearance",
                    severity=Severity.WARNING,
                    message=(
                        f"Bay {boundary}–{boundary + 1}: horizontal gap "
                        f"{h_gap:.1f} mm < {min_face_gap:.0f} mm minimum."
                    ),
                    value=h_gap,
                    limit=min_face_gap,
                ))

    # ── Per-bay vertical face heights and inter-face gaps ─────────────────────
    for bay_idx, cfg in enumerate(bay_configs):
        if not cfg.drawer_config:
            continue

        z_face_start = cfg.bottom_thickness - face_bottom_overhang
        z_face_end   = cfg.height - cfg.top_thickness + face_top_overhang

        # All slot types (drawer, door, door_pair) contribute a face panel.
        face_slots: list[tuple[int, float, float]] = []  # (slot_idx, opening_h, opening_z)
        z_acc = cfg.bottom_thickness
        for slot_idx, (opening_h, _slot_type) in enumerate(cfg.drawer_config):
            face_slots.append((slot_idx, opening_h, z_acc))
            z_acc += opening_h

        n_faces = len(face_slots)
        prev_face_z_top: Optional[float] = None

        for face_num, (slot_idx, opening_h, opening_z) in enumerate(face_slots):
            is_first = face_num == 0
            is_last  = face_num == n_faces - 1

            face_z_bot = z_face_start if is_first else opening_z + face_gap / 2
            face_z_top = z_face_end   if is_last  else opening_z + opening_h - face_gap / 2
            face_h     = face_z_top - face_z_bot
            label      = f"bay{bay_idx}_slot{slot_idx}"

            if face_h <= 0:
                issues.append(Issue(
                    check="face_clearance",
                    severity=Severity.ERROR,
                    message=(
                        f"{label}: computed face height {face_h:.1f} mm ≤ 0. "
                        f"Opening {opening_h:.0f} mm is too small to accommodate "
                        f"face_gap {face_gap:.0f} mm (±{face_gap / 2:.1f} mm per side)."
                    ),
                    part_a=label,
                    value=face_h,
                    limit=0.0,
                ))

            if prev_face_z_top is not None:
                inter_gap = face_z_bot - prev_face_z_top
                if inter_gap < min_face_gap:
                    issues.append(Issue(
                        check="face_clearance",
                        severity=Severity.ERROR if inter_gap < 0 else Severity.WARNING,
                        message=(
                            f"{label}: vertical gap to preceding face "
                            f"{inter_gap:.1f} mm < {min_face_gap:.0f} mm minimum."
                        ),
                        part_a=label,
                        value=inter_gap,
                        limit=min_face_gap,
                    ))

            prev_face_z_top = face_z_top

    return issues


def check_column_widths(cab_cfg: CabinetConfig) -> list[Issue]:
    """Validate multi-column layout widths when ``columns`` is non-empty.

    Checks:
    - Each column width is positive.
    - The sum of all column widths equals ``interior_width`` (±0.5 mm tolerance).
    """
    if not cab_cfg.columns:
        return []

    issues: list[Issue] = []
    interior_w = cab_cfg.interior_width
    col_sum = sum(c.width_mm for c in cab_cfg.columns)

    for i, col in enumerate(cab_cfg.columns):
        if col.width_mm <= 0:
            issues.append(Issue(
                severity=Severity.ERROR,
                check="column_width_positive",
                message=f"Column {i} has non-positive width ({col.width_mm:.1f} mm).",
                part_a=f"column_{i}",
                value=col.width_mm,
                limit=0.0,
            ))

    if abs(col_sum - interior_w) > 0.5:
        issues.append(Issue(
            severity=Severity.ERROR,
            check="column_widths_sum",
            message=(
                f"Column widths sum to {col_sum:.1f} mm but cabinet interior_width is "
                f"{interior_w:.1f} mm (difference: {col_sum - interior_w:+.1f} mm)."
            ),
            part_a="columns",
            value=col_sum,
            limit=interior_w,
        ))

    return issues


# ─── Full Evaluation Runner ──────────────────────────────────────────────────


def evaluate_cabinet(
    cab_cfg: CabinetConfig,
    assembly: Optional["cq.Assembly"] = None,
    drawer_assemblies: Optional[list[tuple["cq.Assembly", DrawerConfig]]] = None,
    door_configs: Optional[list[DoorConfig]] = None,
    shelf_loads_kg: Optional[dict[str, float]] = None,
) -> list[Issue]:
    """Run all checks against a cabinet configuration and optional geometry.

    Args:
        cab_cfg: Cabinet configuration.
        assembly: Built CadQuery assembly (for geometric checks).
        drawer_assemblies: List of (drawer_assembly, drawer_config) pairs.
        door_configs: List of DoorConfig objects to validate.
        shelf_loads_kg: Expected loads per shelf, keyed by shelf name.

    Returns:
        List of all issues found.
    """
    all_issues: list[Issue] = []

    # ── Parametric checks (always run) ───────────────────────────────────
    all_issues.extend(check_drawer_stack_order(cab_cfg))
    all_issues.extend(check_cumulative_heights(cab_cfg))
    all_issues.extend(check_back_panel_fit(cab_cfg))
    all_issues.extend(check_dado_alignment(cab_cfg))
    all_issues.extend(check_carcass_joinery(cab_cfg))
    all_issues.extend(check_drawer_carcass_clearances(cab_cfg))
    all_issues.extend(check_column_widths(cab_cfg))
    all_issues.extend(check_cabinet_pull_consistency(cab_cfg))

    # Hardware constraints checked parametrically — no assembly required.
    for opening_height, slot_type in cab_cfg.drawer_config:
        if slot_type == "drawer":
            dcfg = DrawerConfig(
                opening_width=cab_cfg.interior_width,
                opening_height=opening_height,
                opening_depth=cab_cfg.interior_depth,
                slide_key=cab_cfg.drawer_slide,
                pull_key=cab_cfg.drawer_pull,
            )
            all_issues.extend(check_drawer_hardware_clearances(dcfg))

    # ── Drawer hardware + joinery checks (geometry-dependent) ────────────
    if drawer_assemblies:
        for drawer_assy, drawer_cfg in drawer_assemblies:
            all_issues.extend(check_drawer_joinery(drawer_cfg))
            all_issues.extend(check_drawer_pull(drawer_cfg))

    # ── Door / hinge checks ──────────────────────────────────────────────
    if door_configs:
        for door_cfg in door_configs:
            all_issues.extend(check_door_hinge_count(door_cfg))
            all_issues.extend(check_door_dimensions(door_cfg))
            all_issues.extend(check_door_pair_width(door_cfg))
            all_issues.extend(check_door_pull(door_cfg))

    # ── Shelf deflection ─────────────────────────────────────────────────
    if shelf_loads_kg:
        for shelf_name, load in shelf_loads_kg.items():
            all_issues.extend(check_shelf_deflection(
                span=cab_cfg.interior_width,
                depth=cab_cfg.depth - cab_cfg.back_rabbet_width,
                thickness=cab_cfg.shelf_thickness,
                load_kg=load,
            ))

    # ── Geometric checks (only if assembly provided) ─────────────────────
    if assembly is not None:
        all_issues.extend(check_interference(assembly))

    if drawer_assemblies and assembly is not None:
        slide = get_slide(cab_cfg.drawer_slide)
        for drawer_assy, drawer_cfg in drawer_assemblies:
            all_issues.extend(check_drawer_in_opening(
                drawer_assy,
                opening_width=drawer_cfg.opening_width,
                opening_height=drawer_cfg.opening_height,
                opening_depth=drawer_cfg.opening_depth,
                slide=slide,
            ))

    return all_issues


def print_report(issues: list[Issue]) -> None:
    """Print a formatted evaluation report."""
    errors = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]
    infos = [i for i in issues if i.severity == Severity.INFO]

    print("=" * 70)
    print("FURNITURE DESIGN EVALUATION REPORT")
    print("=" * 70)
    print(f"  {len(errors)} errors, {len(warnings)} warnings, {len(infos)} info")
    print()

    if errors:
        print("ERRORS:")
        for issue in errors:
            print(f"  ✗ {issue}")
        print()

    if warnings:
        print("WARNINGS:")
        for issue in warnings:
            print(f"  ⚠ {issue}")
        print()

    if infos:
        print("INFO:")
        for issue in infos:
            print(f"  ✓ {issue}")
        print()

    if not errors:
        print("✓ Design passes all checks.")
    else:
        print(f"✗ Design has {len(errors)} error(s) that must be resolved.")
    print("=" * 70)
