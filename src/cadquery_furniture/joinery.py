"""
Joinery specifications and geometry for drawer boxes and cabinet carcasses.

Drawer corner joints
--------------------
Four styles are supported, selectable via ``DrawerJoineryStyle``:

  BUTT         — plain butt joint (current default); sides butt against
                 the front and back sub-panels, fastened with glue + staples
                 or pocket screws.  No interlocking geometry.

  QQQ          — Quarter-Quarter-Quarter locking rabbet, coined by Stephen
                 Phipps (thisiscarpentry.com, 2014).  A dado is crosscut near
                 each end of the side piece (inside face down), creating a
                 tongue equal to half the stock thickness.  A matching channel
                 (rabbet) is cut on the outside edges of the front/back pieces.
                 All three table-saw settings equal material_thickness ÷ 2:
                 blade width, blade height, fence-to-blade distance.
                 Wood Magazine torture tests found this stronger than dovetail.
                 Requires true ½″ (12.7 mm) stock; works with any thickness
                 using the ½-stock rule throughout.

  HALF_LAP     — Half-lap at each corner.  Each mating face loses half its
                 thickness; the overlapping glue area doubles vs. a butt joint.
                 No mechanical interlock, but simple to cut (one rabbet per
                 piece end on the table saw).  No change to box exterior dims.

  DRAWER_LOCK  — Stepped router-bit joint (single bit, one setup per piece
                 type).  The side gets an L-shaped tongue; the front/back
                 gets a matching L-shaped socket.  Highest shear resistance of
                 the four styles.  Tongue proportions follow the ⅓-thickness
                 convention used by most dedicated drawer-lock router bits.

Carcass joinery
---------------
Five methods are supported via ``CarcassJoinery``:

  DADO_RABBET    — current default (dados for shelves/bottom, rabbet for back)
  FLOATING_TENON — Festool Domino oval loose tenon; parametric mortise layout
  POCKET_SCREW   — Kreg-style angled pocket; parametric count and positioning
  BISCUIT        — #0 / #10 / #20 biscuit; primarily for alignment in plywood
  DOWEL          — 8 mm or 10 mm dowels; compatible with the 32 mm grid system

All dimensions in millimeters.  CadQuery geometry functions are gated behind
``_require_cq()`` so pure-parametric planning works without the CAD kernel.

Sources
-------
QQQ system  : Stephen Phipps, "The Quarter-Quarter-Quarter Drawer System",
              thisiscarpentry.com, 2014-09-19.
Domino tenon sizes : Festool catalog (DF 500 and DF 700 machines), 2023.
              Mortise dimensions confirmed via Festool technical datasheet
              "Domino Joining System" (EN, Rev. 2022).
Pocket screw : Kreg Tool Company, "Pocket-Hole Joinery Guide", 2023.
              Drill angle 15°; pocket and screw dimensions from Kreg Jig
              settings chart for wood thickness 12–38 mm.
Biscuit sizes: Porter-Cable / DeWalt biscuit dimension standard (ANSI 1986);
              #0, #10, #20 are the three standard sizes in universal use.
Dowel system : 32 mm European cabinet standard (Hettich/Grass technical
              docs); 8 mm is the most common diameter for carcass alignment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

try:
    import cadquery as cq
except ImportError:
    cq = None


# ─── Enumerations ─────────────────────────────────────────────────────────────


class DrawerJoineryStyle(Enum):
    """Corner-joint style for drawer boxes."""
    BUTT        = "butt"         # plain butt joint
    QQQ         = "qqq"          # quarter-quarter-quarter locking rabbet
    HALF_LAP    = "half_lap"     # half-lap overlap
    DRAWER_LOCK = "drawer_lock"  # stepped router-bit lock joint


class CarcassJoinery(Enum):
    """Method for joining cabinet carcass panels."""
    DADO_RABBET    = "dado_rabbet"
    FLOATING_TENON = "floating_tenon"
    POCKET_SCREW   = "pocket_screw"
    BISCUIT        = "biscuit"
    DOWEL          = "dowel"


# ─── Drawer joint geometry ────────────────────────────────────────────────────


@dataclass(frozen=True)
class DrawerJoinerySpec:
    """Computed dimensions for one drawer corner joint style.

    All dimensions in mm.  The spec is derived from stock thicknesses via
    ``from_stock()``.  Do not instantiate directly.

    Coordinate conventions (follows drawer.py orientation):
      X = width  (left → right)
      Y = depth  (front → back)
      Z = height (bottom → top)

    The LEFT SIDE panel occupies x = 0 … side_thickness, spanning full depth.
    The SUB-FRONT occupies y = 0 … front_back_thickness, spanning interior_width.

    Joint cuts on the SIDE panel (at its front end, y = 0):
      ``side_dado_x``   — start x of the dado cut from the INSIDE face
      ``side_dado_y``   — how far the dado penetrates into the side end (y direction)
      ``side_dado_z``   — always 0 (dado runs full height)
      The tongue that remains is the outer portion: x = 0 … side_tongue_width

    Joint cuts on the FRONT/BACK panel (at its left end, x = 0):
      ``fb_channel_x``  — depth of channel from outside edge (in x direction)
      ``fb_channel_y``  — width of channel from front face (in y direction)

    For BUTT: all cut dimensions are 0 (no joinery geometry, just glue face).
    For HALF_LAP: overlapping rabbet on each piece; no mechanical interlock.
    For DRAWER_LOCK: L-shaped tongue/socket; see attribute comments.
    """
    style: DrawerJoineryStyle

    side_thickness: float       # thickness of side panels (mm)
    front_back_thickness: float # thickness of front/back sub-panels (mm)

    # SIDE panel cuts (at each end, Y direction)
    side_dado_depth_x: float    # how deep the dado cuts into side (x direction, from inside face)
    side_dado_depth_y: float    # how far into the end of the side (y direction)

    # FRONT/BACK panel cuts (at each end, X direction)
    fb_channel_depth_x: float   # how deep the channel is from the outer edge (x)
    fb_channel_depth_y: float   # how wide the channel is from the front face (y)

    # For DRAWER_LOCK only: second step of the L-tongue
    lock_step_depth_x: float = 0.0  # inner step (x)
    lock_step_depth_y: float = 0.0  # inner step (y)

    # Does the joint require a router bit (True) or a saw blade setup (False)?
    requires_router_bit: bool = False

    # For QQQ: is exact-thickness stock required?
    requires_true_thickness: bool = False
    nominal_thickness: float = 0.0  # mm — 0 means "any thickness works"

    @property
    def side_tongue_width(self) -> float:
        """Width of the tongue left on the side after the dado cut (x direction)."""
        return self.side_thickness - self.side_dado_depth_x

    @property
    def engagement_x(self) -> float:
        """How far the sub-front/back must extend past the carcass interior edge
        to engage the side panel.

        For BUTT this is 0 — the sub-front sits flush between the sides.
        For HALF_LAP / DRAWER_LOCK the sub-front fills a full-thickness rabbet
        (``side_dado_depth_x`` deep × ``front_back_thickness`` wide) on the
        side, edge-to-edge.  For QQQ the same value is the depth into the
        side that the front piece's inside-face tongue protrudes — into a
        set-in dado pocket on the side's inner face.  The side carries a
        full-thickness lip at the very end (Y `0…t_s/2`) that wraps around
        the corner and hides the joint from outside the box.
        """
        if self.style == DrawerJoineryStyle.BUTT:
            return 0.0
        return self.side_dado_depth_x

    @property
    def glue_area_corner(self) -> float:
        """Approximate glue contact area at one corner (mm²).

        Used for rough structural comparison between styles.
        Butt joint: just the end-grain face of the front/back against the side.
        QQQ / half-lap: the interlocking faces add long-grain area.
        """
        if self.style == DrawerJoineryStyle.BUTT:
            # End face of front/back against side inside face
            return self.front_back_thickness * 1  # per-mm of height; caller scales by height
        elif self.style == DrawerJoineryStyle.QQQ:
            # Tongue face (long grain) + shoulder face (cross grain)
            return self.side_dado_depth_x * self.side_dado_depth_y * 2
        elif self.style == DrawerJoineryStyle.HALF_LAP:
            return self.side_dado_depth_x * self.front_back_thickness
        elif self.style == DrawerJoineryStyle.DRAWER_LOCK:
            # L-tongue has two contact faces
            return (self.side_dado_depth_x + self.lock_step_depth_x) * self.side_dado_depth_y
        return 0.0

    @classmethod
    def from_stock(
        cls,
        style: DrawerJoineryStyle,
        side_thickness: float,
        front_back_thickness: float,
    ) -> "DrawerJoinerySpec":
        """Create a spec with dimensions computed from stock thicknesses.

        QQQ:
          All cut depths = side_thickness / 2  (the ¼-¼-¼ rule scaled to stock).
        HALF_LAP:
          Each piece loses half its own thickness at the corner.
        DRAWER_LOCK:
          Tongue proportions: ⅓ of front_back_thickness for each step.
          (Matches the geometry produced by most commercial drawer-lock bits.)
        BUTT:
          No cuts; all zero.
        """
        t_s = side_thickness
        t_fb = front_back_thickness

        if style == DrawerJoineryStyle.BUTT:
            return cls(
                style=style,
                side_thickness=t_s,
                front_back_thickness=t_fb,
                side_dado_depth_x=0.0,
                side_dado_depth_y=0.0,
                fb_channel_depth_x=0.0,
                fb_channel_depth_y=0.0,
                requires_router_bit=False,
                requires_true_thickness=False,
            )

        elif style == DrawerJoineryStyle.QQQ:
            half = t_s / 2
            return cls(
                style=style,
                side_thickness=t_s,
                front_back_thickness=t_fb,
                # Dado on side end: inner half of thickness, half deep into end
                side_dado_depth_x=half,      # cuts from inside face inward
                side_dado_depth_y=half,      # penetrates half-thickness into the end
                # Channel on front/back end: matching the side tongue
                fb_channel_depth_x=half,    # channel depth from outer edge
                fb_channel_depth_y=half,    # channel height from front face
                requires_router_bit=False,
                requires_true_thickness=True,
                nominal_thickness=t_s,
            )

        elif style == DrawerJoineryStyle.HALF_LAP:
            return cls(
                style=style,
                side_thickness=t_s,
                front_back_thickness=t_fb,
                # Side: rabbet from inside face, full front_back_thickness wide
                side_dado_depth_x=t_s / 2,
                side_dado_depth_y=t_fb,
                # Front/back: rabbet from outside face, full side_thickness wide
                fb_channel_depth_x=t_s,
                fb_channel_depth_y=t_fb / 2,
                requires_router_bit=False,
                requires_true_thickness=False,
            )

        elif style == DrawerJoineryStyle.DRAWER_LOCK:
            # L-tongue: the side gets a stepped tongue of ⅓ / ⅓ proportions
            step = t_fb / 3
            return cls(
                style=style,
                side_thickness=t_s,
                front_back_thickness=t_fb,
                side_dado_depth_x=t_s / 2,   # outer step of L (from inside face)
                side_dado_depth_y=step,        # depth of first step (into end)
                fb_channel_depth_x=t_s / 2,   # matching socket outer step
                fb_channel_depth_y=step,       # matching socket depth
                lock_step_depth_x=t_s / 2,    # inner step of L
                lock_step_depth_y=step * 2,    # extends further into end
                requires_router_bit=True,
                requires_true_thickness=False,
            )

        raise ValueError(f"Unknown DrawerJoineryStyle: {style}")


def drawer_joinery_spec(
    style: DrawerJoineryStyle,
    side_thickness: float,
    front_back_thickness: float,
) -> DrawerJoinerySpec:
    """Convenience wrapper for DrawerJoinerySpec.from_stock()."""
    return DrawerJoinerySpec.from_stock(style, side_thickness, front_back_thickness)


# ─── Festool Domino floating tenon ────────────────────────────────────────────


@dataclass(frozen=True)
class DominoSize:
    """Dimensions for a single Domino tenon size.

    The tenon is nominally tenon_length × tenon_thickness (oval cross-section).
    The machine cuts an oval mortise slightly larger than the tenon for fit.

    Source: Festool "Domino Joining System" technical datasheet, 2022.
    Mortise dims are for the "fixed" (tight) fit setting on the DF 500/700.
    The DF 500 machine handles tenons up to 8 mm thick;
    the DF 700 handles 10 mm and 14 mm tenons.
    """
    tenon_length: float          # longer dimension (mm) — runs along the panel face
    tenon_thickness: float       # shorter dimension (mm) — penetrates into each piece
    mortise_length: float        # slot length cut by machine (tenon_length + 0.5 mm)
    mortise_width: float         # slot width (tenon_thickness + 0.5 mm)
    mortise_depth_per_side: float  # how deep the mortise goes into each piece
    min_edge_distance: float     # centre of mortise to nearest panel edge
    machine: str                 # "DF 500" or "DF 700"
    part_number: str             # Festool catalog number for the tenon pack


# All sizes from Festool catalog 2023; mortise depths are at the "fixed" fit setting.
DOMINO_SIZES: dict[str, DominoSize] = {
    "4x17": DominoSize(
        tenon_length=17, tenon_thickness=4,
        mortise_length=17.5, mortise_width=4.5, mortise_depth_per_side=12,
        min_edge_distance=8, machine="DF 500", part_number="498879",
    ),
    "5x19": DominoSize(
        tenon_length=19, tenon_thickness=5,
        mortise_length=19.5, mortise_width=5.5, mortise_depth_per_side=15,
        min_edge_distance=9, machine="DF 500", part_number="498880",
    ),
    "5x30": DominoSize(
        tenon_length=30, tenon_thickness=5,
        mortise_length=30.5, mortise_width=5.5, mortise_depth_per_side=15,
        min_edge_distance=9, machine="DF 500", part_number="498889",
    ),
    "6x40": DominoSize(
        tenon_length=40, tenon_thickness=6,
        mortise_length=40.5, mortise_width=6.5, mortise_depth_per_side=18,
        min_edge_distance=10, machine="DF 500", part_number="498881",
    ),
    "8x40": DominoSize(
        # Mortise depth set to 15 mm per side — the recommended depth for
        # 18–19 mm (3/4″) plywood per Festool DF 500 settings chart.
        # The machine maximum is 20 mm; 15 mm leaves a safe 3 mm wall in
        # 18 mm stock.  Use the deeper setting only in panels ≥ 23 mm thick.
        tenon_length=40, tenon_thickness=8,
        mortise_length=40.5, mortise_width=8.5, mortise_depth_per_side=15,
        min_edge_distance=11, machine="DF 500", part_number="498882",
    ),
    "8x50": DominoSize(
        tenon_length=50, tenon_thickness=8,
        mortise_length=50.5, mortise_width=8.5, mortise_depth_per_side=15,
        min_edge_distance=11, machine="DF 500", part_number="498883",
    ),
    "10x24": DominoSize(
        tenon_length=24, tenon_thickness=10,
        mortise_length=24.5, mortise_width=10.5, mortise_depth_per_side=22,
        min_edge_distance=12, machine="DF 700", part_number="498884",
    ),
    "10x50": DominoSize(
        tenon_length=50, tenon_thickness=10,
        mortise_length=50.5, mortise_width=10.5, mortise_depth_per_side=22,
        min_edge_distance=12, machine="DF 700", part_number="498885",
    ),
    "14x28": DominoSize(
        tenon_length=28, tenon_thickness=14,
        mortise_length=28.5, mortise_width=14.5, mortise_depth_per_side=27,
        min_edge_distance=15, machine="DF 700", part_number="498886",
    ),
    "14x56": DominoSize(
        tenon_length=56, tenon_thickness=14,
        mortise_length=56.5, mortise_width=14.5, mortise_depth_per_side=27,
        min_edge_distance=15, machine="DF 700", part_number="498887",
    ),
}


def get_domino_size(key: str) -> DominoSize:
    """Look up a DominoSize by key. Raises KeyError on unknown key."""
    if key not in DOMINO_SIZES:
        raise KeyError(f"Unknown Domino size '{key}'. Available: {list(DOMINO_SIZES)}")
    return DOMINO_SIZES[key]


@dataclass(frozen=True)
class DominoSpec:
    """Layout specification for Domino floating tenons along a panel joint.

    Parameters
    ----------
    size_key :
        Key into DOMINO_SIZES (e.g. ``"8x40"``).
    max_spacing :
        Maximum on-centre spacing between adjacent tenons (mm).
        Use 150 mm for structural joints (shelf-to-side, bottom-to-side).
        Use 250 mm for alignment-only joints.
    """
    size_key: str = "8x40"
    max_spacing: float = 150.0   # structural; use 250.0 for alignment only

    @property
    def size(self) -> DominoSize:
        return get_domino_size(self.size_key)

    def count_for_span(self, span: float) -> int:
        """Minimum number of tenons needed for a panel edge of ``span`` mm.

        At least 2 tenons are always used (one near each end).  Beyond that,
        one tenon is added for every ``max_spacing`` mm of span.
        """
        if span <= 0:
            return 0
        s = self.size
        # Usable span between the two end tenons
        usable = span - 2 * s.min_edge_distance
        if usable <= 0:
            return 2
        extra = math.ceil(usable / self.max_spacing) - 1
        return 2 + max(0, extra)

    def positions_for_span(self, span: float) -> list[float]:
        """Centred positions (from panel edge) for each tenon along the span.

        The first and last tenons are placed at ``min_edge_distance`` from each
        end.  Remaining tenons are evenly distributed between them.
        """
        n = self.count_for_span(span)
        s = self.size
        if n == 0:
            return []
        if n == 1:
            return [span / 2]
        start = s.min_edge_distance
        end = span - s.min_edge_distance
        if n == 2:
            return [start, end]
        step = (end - start) / (n - 1)
        return [start + i * step for i in range(n)]


# ─── Pocket screw (Kreg-style) ────────────────────────────────────────────────


# Screw length by stock thickness (mm → mm).
# Source: Kreg Tool "Pocket-Hole Joinery Guide", 2023 edition.
POCKET_SCREW_LENGTH_BY_THICKNESS: dict[float, float] = {
    10: 19,   # 3/8" stock → 3/4" screw
    12: 19,   # 1/2" stock → 3/4" screw
    16: 25,   # 5/8" stock → 1" screw
    18: 32,   # 3/4" stock → 1-1/4" screw
    22: 38,   # 7/8" stock → 1-1/2" screw
    25: 38,   # 1" stock   → 1-1/2" screw
    32: 51,   # 1-1/4" stock → 2" screw
    38: 64,   # 1-1/2" stock → 2-1/2" screw
}


def pocket_screw_length(thickness_mm: float) -> float:
    """Return the recommended screw length for the given stock thickness.

    Looks up the nearest thickness in the Kreg chart and returns the
    corresponding screw length in mm.
    """
    if not POCKET_SCREW_LENGTH_BY_THICKNESS:
        return 32.0
    nearest = min(POCKET_SCREW_LENGTH_BY_THICKNESS, key=lambda t: abs(t - thickness_mm))
    return POCKET_SCREW_LENGTH_BY_THICKNESS[nearest]


@dataclass(frozen=True)
class PocketScrewSpec:
    """Layout spec for Kreg-style pocket-screw joints.

    The pocket is drilled at 15° through the thinner (or weaker) panel into
    the face of the mating panel.  No mortise is cut in the mating panel.

    Source: Kreg Tool Co., pocket-hole joinery guide (2023);
            drill angle and pocket dimensions from the Kreg Jig K5 settings.
    """
    drill_angle_deg: float = 15.0     # standard Kreg jig angle
    pocket_diameter: float = 9.5      # 3/8" pocket hole
    min_edge_distance: float = 19.0   # pocket centre → panel edge (Kreg minimum)
    max_spacing: float = 200.0        # on-centre spacing between pockets

    def screw_length(self, stock_thickness: float) -> float:
        """Return recommended screw length for the given stock thickness (mm)."""
        return pocket_screw_length(stock_thickness)

    def count_for_span(self, span: float) -> int:
        """Minimum pockets for a panel edge of ``span`` mm.

        Always at least 2 (one near each end); one more per ``max_spacing`` mm.
        """
        if span <= 0:
            return 0
        usable = span - 2 * self.min_edge_distance
        if usable <= 0:
            return 2
        extra = math.ceil(usable / self.max_spacing) - 1
        return 2 + max(0, extra)

    def positions_for_span(self, span: float) -> list[float]:
        """Pocket-centre positions (from panel edge) along ``span`` mm."""
        n = self.count_for_span(span)
        if n == 0:
            return []
        if n == 1:
            return [span / 2]
        start = self.min_edge_distance
        end = span - self.min_edge_distance
        if n == 2:
            return [start, end]
        step = (end - start) / (n - 1)
        return [start + i * step for i in range(n)]


# ─── Biscuit joinery ──────────────────────────────────────────────────────────


# ANSI standard biscuit dimensions: (slot_length, slot_width, slot_depth_per_side)
# Source: Porter-Cable / DeWalt biscuit dimension standard (ANSI 1986).
BISCUIT_DIMS: dict[str, tuple[float, float, float]] = {
    "#0":  (47.0, 15.0, 8.0),
    "#10": (53.0, 19.0, 8.0),
    "#20": (56.0, 23.0, 10.0),
}


@dataclass(frozen=True)
class BiscuitSpec:
    """Layout spec for biscuit joints.

    Biscuits are primarily used for alignment in plywood carcasses.
    They add relatively little structural strength across the panel face.

    Parameters
    ----------
    size :
        ``"#0"``, ``"#10"``, or ``"#20"``.
    max_spacing :
        Maximum on-centre spacing (mm).  100 mm is typical for alignment;
        75 mm for locations where some shear strength is needed.
    """
    size: str = "#10"
    max_spacing: float = 100.0
    min_edge_distance: float = 50.0   # biscuit centre → panel end

    @property
    def dims(self) -> tuple[float, float, float]:
        """(slot_length, slot_width, slot_depth_per_side)"""
        if self.size not in BISCUIT_DIMS:
            raise KeyError(f"Unknown biscuit size '{self.size}'. Use #0, #10, or #20.")
        return BISCUIT_DIMS[self.size]

    @property
    def slot_length(self) -> float:
        return self.dims[0]

    @property
    def slot_width(self) -> float:
        return self.dims[1]

    @property
    def slot_depth_per_side(self) -> float:
        return self.dims[2]

    def count_for_span(self, span: float) -> int:
        """Minimum biscuits for a panel edge of ``span`` mm."""
        if span <= 0:
            return 0
        usable = span - 2 * self.min_edge_distance
        if usable <= 0:
            return 2
        extra = math.ceil(usable / self.max_spacing) - 1
        return 2 + max(0, extra)

    def positions_for_span(self, span: float) -> list[float]:
        """Biscuit-centre positions (from panel edge) along ``span`` mm."""
        n = self.count_for_span(span)
        if n == 0:
            return []
        if n == 1:
            return [span / 2]
        start = self.min_edge_distance
        end = span - self.min_edge_distance
        if n == 2:
            return [start, end]
        step = (end - start) / (n - 1)
        return [start + i * step for i in range(n)]


# ─── Dowel joinery ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DownelSpec:
    """Layout spec for round wood dowels.

    Dowels are compatible with the 32 mm European cabinet system — the same
    5 mm shelf-pin holes drilled on the 32 mm grid can serve as alignment
    dowels.  For structural joints, 8 mm or 10 mm dowels are standard.

    Source: 32 mm European cabinet standard; Hettich/Grass technical guides.
    """
    diameter: float = 8.0         # dowel diameter (mm); 8 or 10 for carcass
    depth_per_side: float = 15.0  # how deep each hole goes into the panel
    max_spacing: float = 96.0     # on-centre spacing (3 × 32 mm = 96 mm typical)
    min_edge_distance: float = 16.0  # dowel centre → panel end

    def count_for_span(self, span: float) -> int:
        """Minimum dowels for a panel edge of ``span`` mm."""
        if span <= 0:
            return 0
        usable = span - 2 * self.min_edge_distance
        if usable <= 0:
            return 2
        extra = math.ceil(usable / self.max_spacing) - 1
        return 2 + max(0, extra)

    def positions_for_span(self, span: float) -> list[float]:
        """Dowel-centre positions (from panel edge) along ``span`` mm.

        Positions are snapped to the nearest 32 mm grid increment when
        ``snap_to_32mm`` would be True, but the raw version just distributes
        evenly between the two end positions.
        """
        n = self.count_for_span(span)
        if n == 0:
            return []
        if n == 1:
            return [span / 2]
        start = self.min_edge_distance
        end = span - self.min_edge_distance
        if n == 2:
            return [start, end]
        step = (end - start) / (n - 1)
        return [start + i * step for i in range(n)]


# ─── Default spec instances ───────────────────────────────────────────────────

#: Default Domino spec for structural carcass joints (8×40, 150 mm spacing)
DEFAULT_DOMINO = DominoSpec(size_key="8x40", max_spacing=150.0)

#: Default pocket-screw spec
DEFAULT_POCKET_SCREW = PocketScrewSpec()

#: Default biscuit spec (#10, 100 mm spacing)
DEFAULT_BISCUIT = BiscuitSpec(size="#10", max_spacing=100.0)

#: Default dowel spec (8 mm, 96 mm spacing)
DEFAULT_DOWEL = DownelSpec(diameter=8.0, max_spacing=96.0)


# ─── CadQuery geometry (gated behind _require_cq) ────────────────────────────


def _require_cq() -> None:
    if cq is None:
        raise ImportError("cadquery is required for 3D geometry. pip install cadquery")


def apply_drawer_joinery_to_side(
    panel: "cq.Workplane",
    spec: DrawerJoinerySpec,
    box_depth: float,
    box_height: float,
    side: str = "left",
) -> "cq.Workplane":
    """Cut the inner-face dado / rabbet that receives the sub-front / back panels.

    The panel is assumed to start at the origin (0, 0, 0) with:
      X = 0 … side_thickness
      Y = 0 … box_depth
      Z = 0 … box_height

    For BUTT: no cut.

    For HALF_LAP / DRAWER_LOCK: a uniform inner-face rabbet — ``engagement_x``
    deep in X, full ``front_back_thickness`` deep in Y — at the very end of the
    panel (Y = 0 / Y = box_depth).  The sub-front / back is widened by
    ``2 × engagement_x`` and seats into the rabbet edge-to-edge.

    For QQQ: a *set-in* dado pocket on the inner face at each end.  The pocket
    is ``side_dado_depth_x`` deep in X (= t_s/2) and ``side_dado_depth_y`` long
    in Y (= t_s/2), but its near edge sits ``side_dado_depth_y`` from the panel
    end.  This leaves a full-thickness **lip** at Y `0…t_s/2` (and the
    mirroring lip at the back end) that wraps around the front-corner of the
    box, hiding the joint from outside.  The sub-front's inside-face tongue —
    cut by ``apply_drawer_joinery_to_front_back`` — protrudes into the pocket.

    ``side="left"`` puts the inner face at panel-local X = side_thickness;
    ``side="right"`` puts it at X = 0.
    """
    _require_cq()

    if spec.style == DrawerJoineryStyle.BUTT:
        return panel

    if side not in ("left", "right"):
        raise ValueError(f"side must be 'left' or 'right', got {side!r}")

    t_s = spec.side_thickness
    dx = spec.engagement_x
    if spec.style == DrawerJoineryStyle.QQQ:
        dy = spec.side_dado_depth_y
        cut_y_inset = dy  # dado set in by t_s/2 from each end
    else:
        dy = spec.front_back_thickness
        cut_y_inset = 0.0

    cut_x_start = (t_s - dx) if side == "left" else 0.0

    front_cut = (
        cq.Workplane("XY")
        .transformed(offset=(cut_x_start, cut_y_inset, 0))
        .box(dx, dy, box_height, centered=False)
    )
    panel = panel.cut(front_cut)

    back_cut = (
        cq.Workplane("XY")
        .transformed(offset=(cut_x_start, box_depth - dy - cut_y_inset, 0))
        .box(dx, dy, box_height, centered=False)
    )
    panel = panel.cut(back_cut)

    return panel


def apply_drawer_joinery_to_front_back(
    panel: "cq.Workplane",
    spec: DrawerJoinerySpec,
    interior_width: float,
    box_height: float,
    position: str = "back",
) -> "cq.Workplane":
    """Cut the QQQ outer-face rabbet on the sub-front / back panel.

    For BUTT / HALF_LAP / DRAWER_LOCK this is a no-op — the sub-front's solid
    body fills the side's rabbet directly.

    For QQQ each end of the front/back gets an outer-face rabbet that removes
    the corner (panel-local X = 0…fb_channel_depth_x, Y = 0…(t_fb − tongue_y),
    full Z, on the outer-face side).  What remains at each end is a
    ``tongue_y``-thick **inside-face tongue** that protrudes into the side
    panel's set-in dado pocket.  The matching cut on the side is in
    ``apply_drawer_joinery_to_side``.

    The "outer face" depends on ``position``: for a sub-front the outer face
    is panel-local Y = 0 (the front of the drawer faces the user), so the
    rabbet starts at Y = 0; for the back panel the outer face is Y = t_fb,
    so the rabbet starts at Y = tongue_y.  In both cases the tongue ends up
    on the inside-face half of the panel.
    """
    _require_cq()
    if position not in ("front", "back"):
        raise ValueError(f"position must be 'front' or 'back', got {position!r}")

    if spec.style != DrawerJoineryStyle.QQQ:
        return panel

    t_fb = spec.front_back_thickness
    dx = spec.fb_channel_depth_x
    tongue_y = spec.fb_channel_depth_y
    rabbet_dy = t_fb - tongue_y

    rabbet_y_start = 0.0 if position == "front" else tongue_y

    left_cut = (
        cq.Workplane("XY")
        .transformed(offset=(0, rabbet_y_start, 0))
        .box(dx, rabbet_dy, box_height, centered=False)
    )
    panel = panel.cut(left_cut)

    right_cut = (
        cq.Workplane("XY")
        .transformed(offset=(interior_width - dx, rabbet_y_start, 0))
        .box(dx, rabbet_dy, box_height, centered=False)
    )
    panel = panel.cut(right_cut)

    return panel


def apply_domino_mortises(
    panel: "cq.Workplane",
    spec: DominoSpec,
    span: float,
    edge_y: float,
    panel_thickness_z: float,
) -> "cq.Workplane":
    """Cut Domino mortises into a panel face along an edge.

    Mortises are cut from the face at z = panel_thickness_z (top face for a
    horizontal panel) down to z = panel_thickness_z - mortise_depth_per_side.
    Positions are along the X axis starting at x = 0.

    Args:
        panel: CadQuery workplane of the panel.
        spec: DominoSpec with size and spacing configuration.
        span: Panel edge length (mm); mortises are distributed along this span.
        edge_y: Y-coordinate of the panel edge where the joint is made.
                Mortise centres are placed at this Y offset.
        panel_thickness_z: Z height of the panel face where mortises are cut.
    """
    _require_cq()
    s = spec.size
    positions = spec.positions_for_span(span)
    depth = s.mortise_depth_per_side

    for x_pos in positions:
        mortise = (
            cq.Workplane("XY")
            .transformed(offset=(
                x_pos - s.mortise_length / 2,
                edge_y - s.mortise_width / 2,
                panel_thickness_z - depth,
            ))
            .box(s.mortise_length, s.mortise_width, depth, centered=False)
        )
        panel = panel.cut(mortise)

    return panel


def apply_pocket_screw_pockets(
    panel: "cq.Workplane",
    spec: PocketScrewSpec,
    span: float,
    stock_thickness: float,
    pocket_face_y: float,
    panel_z: float = 0.0,
) -> "cq.Workplane":
    """Cut angled pocket-screw pockets into a panel face.

    The pocket is modelled as a simplified angled cylinder (approximated as an
    angled box cut for compatibility).  The drill enters at pocket_face_y on
    the back face of the panel and exits at an angle toward the mating panel.

    Note: The full angled geometry requires the panel to be thick enough to
    accommodate the pocket depth.  This implementation uses an approximation
    that is sufficient for interference detection; the actual jig setup governs
    the real cut path.
    """
    _require_cq()
    angle_rad = math.radians(spec.drill_angle_deg)
    pocket_len = stock_thickness / math.sin(angle_rad)  # approximate pocket length

    positions = spec.positions_for_span(span)

    for x_pos in positions:
        # Simplified angled pocket: a box cut at the drill angle
        pocket = (
            cq.Workplane("YZ")
            .transformed(offset=(pocket_face_y, panel_z + stock_thickness / 2, x_pos),
                          rotate=(spec.drill_angle_deg, 0, 0))
            .box(pocket_len, spec.pocket_diameter, spec.pocket_diameter, centered=True)
        )
        panel = panel.cut(pocket)

    return panel
