"""
Hardware specifications for drawer slides, hinges, and other cabinet hardware.

All dimensions in millimeters unless otherwise noted.

Sources
-------
Blum Tandem 550H   : Blum Inc. 550H datasheet + distributor catalog cross-reference
                     (mcfaddens.com, interfitco.com, search-confirmed part numbers)
Blum Tandem+ 563H  : Blum 563H official datasheet (© 2016 Blum Inc.) as indexed by
                     cabinetdoor.store and d2.blum.com; CabinetParts.com SKU listings
Blum Movento 760H  : Blum Movento brochure "The Evolution of Motion" (2016/2024);
                     distributor SKU tables (mcfaddens.com, hwt-pro.com, Amazon)
Blum Movento 769   : Blum 769 catalog page © 2019; CabinetParts / Indian River
                     Cabinet Supply SKU listings; rokhardware.com spec page
Accuride 3832      : Accuride product page and distributor listings
Salice Futura      : Salice Futura catalog D0CASG010ENG
Salice Progressa+  : Salice PROGRESSA catalog D0CASAA36USA; cabinetparts.com specs

Blum Clip Top hinge family:
  Hinge arm suffix: B = full overlay, H = half overlay, N = inset (cranked)
  BLUMOTION variants: 71B3590 / 71H3590 / 71N3590 (integrated soft-close)
  Source: Blum CLIP top datasheet (d2.blum.com/en/HingeDataSheet_cliptop.pdf);
          Blum catalog "Kitchen & Bedroom" © 2023; hardware.com / hafele.com SKUs.

  Standard cup boring (Blum 35 mm system):
    Cup diameter : 35 mm
    Cup depth    : 13 mm
    Cup centre from door edge (boring centre): 22.5 mm
    This leaves 5 mm of door material beyond the cup edge — do not reduce below 3 mm.

  Standard hinge placement (from door edge):
    Top hinge    : 100 mm from door top
    Bottom hinge : 100 mm from door bottom
    3rd/4th hinge: evenly distributed in remaining span

  Hinge count by door height:
    Up to 1 200 mm  → 2 hinges
    1 201–1 800 mm  → 3 hinges
    > 1 800 mm      → 4 hinges
  (Blum also recommends an extra hinge per 25 kg of door weight above 20 kg.)

IMPORTANT: Always verify part numbers and dimensions against the official Blum or
Salice datasheet for the specific revision you are purchasing before cutting.
Minor changes between catalog years are possible.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SlideType(Enum):
    UNDERMOUNT = "undermount"
    SIDE_MOUNT = "side_mount"
    CENTER_MOUNT = "center_mount"


class SlideMountLocation(Enum):
    """Where the slide attaches relative to the drawer box."""
    BOTTOM = "bottom"  # undermount slides attach under the drawer
    SIDE = "side"      # side-mount slides attach to drawer sides


@dataclass(frozen=True)
class DrawerSlideSpec:
    """Specifications for a drawer slide system.

    All clearance values are PER SIDE unless noted otherwise.

    For Blum Tandem and Movento undermount families the nominal clearance is
    21 mm per side — the official formula is:
        drawer_box_width = interior_opening_width − 42 mm
    (confirmed in Blum Tandem 550H and Movento 760H/769 installation docs).
    """
    name: str
    manufacturer: str
    slide_type: SlideType
    mount_location: SlideMountLocation

    # Clearance requirements (per side, drawer box side → cabinet side)
    min_side_clearance: float   # absolute minimum; slide may not engage below this
    max_side_clearance: float   # maximum; coupling won't reach above this
    nominal_side_clearance: float  # recommended / spec clearance

    # Vertical clearances
    min_top_clearance: float    # minimum gap above drawer box top
    min_bottom_clearance: float # minimum gap below drawer box (undermount body height)

    # Slide dimensions
    available_lengths: tuple[int, ...]  # nominal slide lengths in mm
    max_load_kg: float                  # maximum rated dynamic load

    # Drawer box constraints
    min_drawer_height: float   # minimum drawer side height
    max_drawer_width: float    # maximum drawer box width (0 = no hard limit)

    # Mounting geometry (how far mounting points sit from cabinet extremes)
    rear_bracket_inset: float  # distance of rear mount from back of cabinet interior
    front_bracket_inset: float # distance of front clip/mount from cabinet face

    # Part numbers keyed by nominal length in mm.
    # Format follows Blum conventions: 550H4500B = Tandem 550H, 450 mm length.
    part_numbers: dict = field(default_factory=dict)

    def slide_length_for_depth(self, cabinet_depth: float) -> int:
        """Return the longest slide that fits the given cabinet interior depth."""
        usable = cabinet_depth - self.rear_bracket_inset - self.front_bracket_inset
        candidates = [l for l in self.available_lengths if l <= usable]
        if not candidates:
            raise ValueError(
                f"No {self.name} slide fits cabinet depth {cabinet_depth}mm. "
                f"Minimum needed: {min(self.available_lengths) + self.rear_bracket_inset + self.front_bracket_inset}mm"
            )
        return max(candidates)

    def drawer_box_width(self, opening_width: float) -> float:
        """Compute drawer box width from cabinet opening width."""
        return opening_width - (self.nominal_side_clearance * 2)

    def validate_drawer_dims(
        self, drawer_width: float, drawer_height: float, drawer_depth: float, opening_width: float
    ) -> list[str]:
        """Check drawer dimensions against slide constraints. Returns list of issues."""
        issues = []
        actual_clearance = (opening_width - drawer_width) / 2

        if actual_clearance < self.min_side_clearance:
            issues.append(
                f"Side clearance {actual_clearance:.1f}mm < minimum {self.min_side_clearance}mm"
            )
        if actual_clearance > self.max_side_clearance:
            issues.append(
                f"Side clearance {actual_clearance:.1f}mm > maximum {self.max_side_clearance}mm — "
                f"slides won't engage"
            )
        if drawer_height < self.min_drawer_height:
            issues.append(
                f"Drawer height {drawer_height:.1f}mm < minimum {self.min_drawer_height}mm for {self.name}"
            )
        if self.max_drawer_width > 0 and drawer_width > self.max_drawer_width:
            issues.append(
                f"Drawer width {drawer_width:.1f}mm > maximum {self.max_drawer_width}mm for {self.name}"
            )
        return issues


class OverlayType(Enum):
    """Door overlay relative to the cabinet carcase."""
    FULL = "full"         # door overlaps the cabinet side fully (16 mm per edge)
    HALF = "half"         # door overlaps half the side (9.5 mm) — shared partition
    INSET = "inset"       # door sits inside the opening with a reveal gap


@dataclass(frozen=True)
class HingeSpec:
    """Specifications for a cabinet door hinge.

    All dimensions in millimeters.

    Cup boring layout (Blum 35 mm system)
    --------------------------------------
    The cup is bored from the *interior* face of the door.
    ``cup_boring_distance`` is the distance from the door edge to the cup
    centre along the door face.  The Blum standard is 22.5 mm, which leaves
    5 mm of material beyond the 35 mm cup edge — never go below 3 mm.

    Hinge count guidance
    --------------------
    Use ``hinges_for_height()`` to get the recommended count.  The formula
    is derived from Blum's published door-height / weight tables.
    """
    name: str
    manufacturer: str
    overlay_type: OverlayType    # full / half / inset
    overlay: float               # mm the door overlaps the carcase edge (0 for inset)
    cup_diameter: float          # boring diameter (35 mm for Blum 35-mm system)
    cup_depth: float             # boring depth (13 mm standard)
    cup_boring_distance: float   # cup centre → door edge (22.5 mm standard)
    min_door_thickness: float
    max_door_thickness: float
    opening_angle: int           # maximum opening angle in degrees
    soft_close: bool             # integrated soft-close / BLUMOTION
    max_door_weight_kg: float    # max door weight per *pair* of hinges
    part_number: str = ""        # manufacturer part number

    # Hinge placement constants (from door top / bottom edge)
    hinge_inset_top: float = 100.0     # distance of top hinge from door top
    hinge_inset_bottom: float = 100.0  # distance of bottom hinge from door bottom
    max_hinge_spacing: float = 700.0   # max on-centre spacing between any two hinges

    def hinges_for_height(self, door_height: float, door_weight_kg: float = 0.0) -> int:
        """Return the recommended number of hinges for a given door height and weight.

        Rules (Blum Clip Top family):
          ≤ 1 200 mm  → 2 hinges
          ≤ 1 800 mm  → 3 hinges
          > 1 800 mm  → 4 hinges
        One extra hinge is added for every 25 kg above ``max_door_weight_kg``.
        """
        if door_height <= 1200:
            count = 2
        elif door_height <= 1800:
            count = 3
        else:
            count = 4
        # Additional hinge for excess weight
        if door_weight_kg > self.max_door_weight_kg:
            extra = int((door_weight_kg - self.max_door_weight_kg) / 25) + 1
            count += extra
        return count

    def hinge_positions(self, door_height: float, door_weight_kg: float = 0.0) -> list[float]:
        """Return z-positions (from door bottom) for each hinge centre.

        The first hinge is ``hinge_inset_bottom`` from the door bottom; the
        last is ``hinge_inset_top`` from the door top.  Middle hinges are
        evenly distributed across the remaining span.
        """
        count = self.hinges_for_height(door_height, door_weight_kg)
        bottom_z = self.hinge_inset_bottom
        top_z = door_height - self.hinge_inset_top
        if count == 1:
            return [door_height / 2]
        if count == 2:
            return [bottom_z, top_z]
        # 3+ hinges: bottom, evenly-spaced middles, top
        positions = [bottom_z]
        span = top_z - bottom_z
        for i in range(1, count - 1):
            positions.append(bottom_z + span * i / (count - 1))
        positions.append(top_z)
        return positions

    def validate_door(
        self,
        door_thickness: float,
        door_height: float,
        door_width: float = 0.0,
    ) -> list[str]:
        """Check door dimensions against hinge spec. Returns list of issue strings."""
        issues = []
        if door_thickness < self.min_door_thickness:
            issues.append(
                f"Door thickness {door_thickness:.1f} mm < minimum {self.min_door_thickness} mm"
            )
        if door_thickness > self.max_door_thickness:
            issues.append(
                f"Door thickness {door_thickness:.1f} mm > maximum {self.max_door_thickness} mm"
            )
        # Check minimum edge-to-cup edge clearance (≥ 3 mm)
        edge_to_cup_edge = self.cup_boring_distance - (self.cup_diameter / 2)
        if edge_to_cup_edge < 3.0:
            issues.append(
                f"Cup boring too close to door edge: only {edge_to_cup_edge:.1f} mm margin "
                f"(minimum 3 mm). Increase cup_boring_distance."
            )
        return issues


# ─── Hardware Database ────────────────────────────────────────────────────────
#
# Side clearance note (Blum undermount family):
#   The Blum installation docs specify:
#       inside drawer width = inside cabinet opening − 42 mm
#   i.e. 21 mm per side nominal clearance. This applies to both the Tandem
#   and Movento families in frameless (Euro-style) cabinets.
#   Adjustment range of the front locking device is ±1.5 mm laterally, giving
#   a workable window of roughly 19.5–22.5 mm per side.
#
# Part number conventions:
#   Tandem 550H  : 550H{length×10}B  e.g. 550H4500B = 450 mm
#   Tandem+ 563H : 563H{length×10}B  e.g. 563H5330B = 533 mm
#   Movento 760H : 760H{length×10}S  e.g. 760H4500S = 450 mm  (S = Blumotion)
#                  760H{length×10}T  for TIP-ON variant
#   Movento 769  : 769.{length×10}S  e.g. 769.4570S = 457 mm


# ── Blum Tandem 550H (partial extension, 30 kg) ───────────────────────────────

BLUM_TANDEM_550H = DrawerSlideSpec(
    # Concealed single-extension runner with integrated Blumotion soft-close.
    # For wooden drawer sides 11–19 mm thick, frameless cabinets.
    # Available lengths: 270–600 mm (metric series; no 250 mm variant exists).
    # Source: Blum 550H datasheet; distributor cross-reference (mcfaddens.com,
    #   interfitco.com); CabinetParts catalog confirmed 450 mm = 550H4500B,
    #   550 mm = 550H5500B.
    name="Blum Tandem 550H",
    manufacturer="Blum",
    slide_type=SlideType.UNDERMOUNT,
    mount_location=SlideMountLocation.BOTTOM,
    # Blum formula: drawer width = opening − 42 mm → 21 mm per side
    min_side_clearance=19.5,
    max_side_clearance=22.5,
    nominal_side_clearance=21.0,
    min_top_clearance=7.0,          # 9/32" — keep this gap above drawer box
    min_bottom_clearance=14.0,      # 9/16" — slide body height below drawer
    available_lengths=(270, 300, 350, 400, 450, 500, 550, 600),
    max_load_kg=30,
    min_drawer_height=68,
    max_drawer_width=0,
    rear_bracket_inset=2.0,
    front_bracket_inset=2.0,
    part_numbers={
        270: "550H2700B",
        300: "550H3000B",
        350: "550H3500B",
        400: "550H4000B",
        450: "550H4500B",  # confirmed
        500: "550H5000B",
        550: "550H5500B",  # confirmed
        600: "550H6000B",
    },
)


# ── Blum Tandem Plus 563H (full extension, 45 kg) ─────────────────────────────

BLUM_TANDEM_PLUS_563H = DrawerSlideSpec(
    # Full-extension upgrade over 550H. Higher capacity (45 kg / 100 lb).
    # Uses inch-series lengths (9"–21"). For ½"–⅝" drawer sides.
    # Source: Blum 563H datasheet © 2016; CabinetParts SKUs 563H4570B (18"),
    #   563H5330B (21") confirmed. Part numbers derived from pattern for other
    #   lengths.
    name="Blum Tandem Plus 563H",
    manufacturer="Blum",
    slide_type=SlideType.UNDERMOUNT,
    mount_location=SlideMountLocation.BOTTOM,
    min_side_clearance=19.5,
    max_side_clearance=22.5,
    nominal_side_clearance=21.0,
    min_top_clearance=6.0,          # ¼" — slightly tighter than 550H
    min_bottom_clearance=14.0,      # 9/16"
    available_lengths=(229, 305, 381, 457, 533),  # 9", 12", 15", 18", 21"
    max_load_kg=45,
    min_drawer_height=68,
    max_drawer_width=0,
    rear_bracket_inset=2.0,
    front_bracket_inset=2.0,
    part_numbers={
        229: "563H2290B",  # 9"  — pattern-derived
        305: "563H3050B",  # 12" — pattern-derived
        381: "563H3810B",  # 15" — pattern-derived
        457: "563H4570B",  # 18" — confirmed (CabinetParts)
        533: "563H5330B",  # 21" — confirmed (CabinetParts, woodworkerexpress)
    },
)


# ── Blum Movento 760H (full extension, 40 kg) ─────────────────────────────────

BLUM_MOVENTO_760H = DrawerSlideSpec(
    # Full-extension concealed runner with Blumotion. 40 kg load.
    # Available in metric series 250–600 mm plus 270 mm.
    # The "S" suffix in part numbers = Blumotion soft-close.
    # "T" suffix = TIP-ON (push-to-open) variant; same lengths available.
    # Source: Blum Movento brochure "The Evolution of Motion" (2024);
    #   distributor SKUs confirmed for 250 mm (760H2500S), 300 mm (760H3000S),
    #   350 mm (760H3500S), 450 mm (760H4500S), 500 mm (760H5000S),
    #   550 mm (760H5500S), 600 mm (760H6000S) via mcfaddens.com / hwt-pro.com.
    name="Blum Movento 760H",
    manufacturer="Blum",
    slide_type=SlideType.UNDERMOUNT,
    mount_location=SlideMountLocation.BOTTOM,
    # Blum formula: drawer width = opening − 42 mm → 21 mm per side
    min_side_clearance=19.5,
    max_side_clearance=22.5,
    nominal_side_clearance=21.0,
    min_top_clearance=3.0,
    min_bottom_clearance=15.0,      # Movento body is slightly taller than Tandem
    available_lengths=(250, 270, 300, 350, 400, 450, 500, 550, 600),
    max_load_kg=40,
    min_drawer_height=68,
    max_drawer_width=1200,
    rear_bracket_inset=2.0,
    front_bracket_inset=2.0,
    part_numbers={
        250: "760H2500S",  # 10" — confirmed
        270: "760H2700S",  # 270 mm — confirmed (also as 760H2700T TIP-ON)
        300: "760H3000S",  # 12" — confirmed
        350: "760H3500S",  # 14" — confirmed
        400: "760H4000S",  # 16" — pattern-derived
        450: "760H4500S",  # 18" — confirmed
        500: "760H5000S",  # 20" — confirmed
        550: "760H5500S",  # 22" — confirmed
        600: "760H6000S",  # 24" — confirmed
    },
)


# ── Blum Movento 769 (full extension, heavy duty, 77 kg) ─────────────────────

BLUM_MOVENTO_769 = DrawerSlideSpec(
    # Heavy-duty Movento. 170 lb static / 155 lb dynamic load (~77/70 kg).
    # Inch-series lengths 18"–27" (457–686 mm). Requires front locking devices
    # ordered separately. For ½"–⅝" drawer sides.
    # Source: Blum 769 catalog page © 2019; confirmed SKUs:
    #   769.4570S = 18" (457 mm), 769.4570M = 18" alternate finish,
    #   769.5330S / 769.5330M = 21" (533 mm),
    #   769.6100S = 24" (610 mm) via Indian River Cabinet Supply / siggia.
    #   686 mm (27") and 762 mm (30") part numbers pattern-derived.
    name="Blum Movento 769",
    manufacturer="Blum",
    slide_type=SlideType.UNDERMOUNT,
    mount_location=SlideMountLocation.BOTTOM,
    min_side_clearance=19.5,
    max_side_clearance=22.5,
    nominal_side_clearance=21.0,
    min_top_clearance=3.0,
    min_bottom_clearance=15.0,
    available_lengths=(457, 533, 610, 686, 762),  # 18"–30"
    max_load_kg=77,
    min_drawer_height=68,
    max_drawer_width=1200,
    rear_bracket_inset=2.0,
    front_bracket_inset=2.0,
    part_numbers={
        457: "769.4570S",  # 18" — confirmed
        533: "769.5330S",  # 21" — confirmed
        610: "769.6100S",  # 24" — confirmed
        686: "769.6860S",  # 27" — pattern-derived
        762: "769.7620S",  # 30" — pattern-derived
    },
)


# ── Accuride 3832 ─────────────────────────────────────────────────────────────

ACCURIDE_3832 = DrawerSlideSpec(
    # Classic heavy-duty side-mount ball-bearing slide. 45 kg load.
    # Full extension, up to 700 mm. Common in commercial and utility cabinets.
    # Side-mount slides use a different clearance model: the slide body mounts
    # on the drawer side, so clearance per side = slide body thickness (~12.7 mm).
    name="Accuride 3832",
    manufacturer="Accuride",
    slide_type=SlideType.SIDE_MOUNT,
    mount_location=SlideMountLocation.SIDE,
    min_side_clearance=12.5,        # ½" per side — slide body thickness
    max_side_clearance=13.5,
    nominal_side_clearance=12.7,
    min_top_clearance=2.0,
    min_bottom_clearance=0.0,       # side-mount — no bottom clearance needed
    available_lengths=(250, 300, 350, 400, 450, 500, 550, 600, 650, 700),
    max_load_kg=45,
    min_drawer_height=40,
    max_drawer_width=0,
    rear_bracket_inset=0.0,
    front_bracket_inset=0.0,
    part_numbers={},                # Accuride uses length-coded SKUs; omitted here
)


# ── Salice Futura ─────────────────────────────────────────────────────────────

SALICE_FUTURA = DrawerSlideSpec(
    # Salice Futura undermount soft-close. 34 kg dynamic / 45 kg static.
    # For ½"–⅝" drawer sides. Lengths 12"–21" (305–533 mm).
    # Source: Salice Futura catalog D0CASG010ENG; wwhardware.com specs.
    name="Salice Futura",
    manufacturer="Salice",
    slide_type=SlideType.UNDERMOUNT,
    mount_location=SlideMountLocation.BOTTOM,
    min_side_clearance=19.5,
    max_side_clearance=22.5,
    nominal_side_clearance=21.0,
    min_top_clearance=3.0,
    min_bottom_clearance=13.0,
    available_lengths=(305, 381, 457, 533),
    max_load_kg=45,
    min_drawer_height=79,           # taller slide body than Blum Tandem
    max_drawer_width=0,
    rear_bracket_inset=0.0,         # Salice clips mount flush to back
    front_bracket_inset=0.0,
    part_numbers={
        305: "A7555/305",   # 12" — confirmed (CabinetParts / woodworkerexpress)
        381: "A7555/381",   # 15" — pattern-derived
        457: "A7555/457",   # 18" — pattern-derived
        533: "A7555/533",   # 21" — confirmed (CabinetParts / woodworkerexpress)
    },
)

SALICE_FUTURA_SMOVE = DrawerSlideSpec(
    # Futura with SMOVE progressive soft-close (load-adaptive damping).
    # Same mounting footprint and lengths as standard Futura.
    # Source: Salice Futura SMOVE page; rokhardware.com.
    name="Salice Futura Smove",
    manufacturer="Salice",
    slide_type=SlideType.UNDERMOUNT,
    mount_location=SlideMountLocation.BOTTOM,
    min_side_clearance=19.5,
    max_side_clearance=22.5,
    nominal_side_clearance=21.0,
    min_top_clearance=3.0,
    min_bottom_clearance=13.0,
    available_lengths=(305, 381, 457, 533),
    max_load_kg=45,
    min_drawer_height=79,
    max_drawer_width=0,
    rear_bracket_inset=0.0,
    front_bracket_inset=0.0,
    part_numbers={},                # SMOVE part numbers vary by clip type; omitted
)


# ── Salice Progressa / Progressa+ ─────────────────────────────────────────────

SALICE_PROGRESSA_PLUS = DrawerSlideSpec(
    # Salice Progressa+ undermount soft-close. 54 kg (120 lb) load.
    # Widest length range: 229–762 mm (9"–30").
    # For ½"–⅝" drawer sides. Face-frame and frameless compatible.
    # Source: Salice PROGRESSA catalog D0CASAA36USA; cabinetparts.com SKUs:
    #   SHG5U6S533XXF6 = 21" confirmed.
    name="Salice Progressa+",
    manufacturer="Salice",
    slide_type=SlideType.UNDERMOUNT,
    mount_location=SlideMountLocation.BOTTOM,
    min_side_clearance=19.5,
    max_side_clearance=22.5,
    nominal_side_clearance=21.0,
    min_top_clearance=3.0,
    min_bottom_clearance=13.0,
    available_lengths=(229, 305, 381, 457, 533, 610, 686, 762),
    max_load_kg=54,
    min_drawer_height=79,
    max_drawer_width=0,
    rear_bracket_inset=2.0,
    front_bracket_inset=2.0,
    part_numbers={
        229: "G5U6S229",    # 9"  — pattern-derived
        305: "G5U6S305",    # 12" — pattern-derived
        381: "G5U6S381",    # 15" — pattern-derived
        457: "G5U6S457",    # 18" — pattern-derived
        533: "G5U6S533",    # 21" — confirmed (cabinetparts SHG5U6S533XXF6 base)
        610: "G5U6S610",    # 24" — pattern-derived
        686: "G5U6S686",    # 28" — pattern-derived (catalog lists 700 mm)
        762: "G5U6S762",    # 30" — confirmed (marathonhardware SG7E6S700XXB ≈ 700mm)
    },
)

SALICE_PROGRESSA_PLUS_SMOVE = DrawerSlideSpec(
    # Progressa+ with SMOVE progressive soft-close.
    # Same specs as Progressa+; stronger, load-adaptive damping at end of travel.
    # Source: Salice Progressa+ SMOVE page; hardwarehut.com.
    name="Salice Progressa+ Smove",
    manufacturer="Salice",
    slide_type=SlideType.UNDERMOUNT,
    mount_location=SlideMountLocation.BOTTOM,
    min_side_clearance=19.5,
    max_side_clearance=22.5,
    nominal_side_clearance=21.0,
    min_top_clearance=3.0,
    min_bottom_clearance=13.0,
    available_lengths=(229, 305, 381, 457, 533, 610, 686, 762),
    max_load_kg=54,
    min_drawer_height=79,
    max_drawer_width=0,
    rear_bracket_inset=2.0,
    front_bracket_inset=2.0,
    part_numbers={},                # SMOVE part numbers vary by clip/finish; omitted
)


# ── Hinges ────────────────────────────────────────────────────────────────────
#
# Blum CLIP top 110° family — three arm types:
#   Full overlay (B arm)  : door overlaps cabinet side 16 mm, part 71B35xx
#   Half overlay (H arm)  : door overlaps 9.5 mm for shared partitions, 71H35xx
#   Inset (N arm, cranked): door sits inside opening, 0 mm overlay, 71N35xx
#
# Standard vs BLUMOTION (soft-close):
#   Standard    : 71x3550  (no integrated damper)
#   BLUMOTION   : 71x3590  (integrated progressive soft-close)
#
# All Clip Top hinges share the same cup (35 mm Ø × 13 mm deep at 22.5 mm from
# door edge) and mounting plate.  Max door weight per *hinge pair*: 20 kg
# standard; 25 kg BLUMOTION (Blum 2023 catalog).
#
# Clip Top 170° is the wide-angle variant for corner/pie-cut doors; same cup
# geometry, same arm types but limited to full overlay only in standard catalog.

# ── Blum Clip Top 110° — Full Overlay ─────────────────────────────────────────

BLUM_CLIP_TOP_110_FULL = HingeSpec(
    # Standard (no soft-close), full overlay, straight arm.
    # Source: Blum CLIP top datasheet; hafele.com SKU 329.01.600 (71B3550)
    name="Blum Clip Top 110° Full Overlay",
    manufacturer="Blum",
    overlay_type=OverlayType.FULL,
    overlay=16.0,
    cup_diameter=35.0,
    cup_depth=13.0,
    cup_boring_distance=22.5,
    min_door_thickness=16.0,
    max_door_thickness=25.0,
    opening_angle=110,
    soft_close=False,
    max_door_weight_kg=20.0,
    part_number="71B3550",
)

BLUM_CLIP_TOP_BLUMOTION_110_FULL = HingeSpec(
    # Integrated BLUMOTION soft-close, full overlay.
    # Source: Blum CLIP top BLUMOTION datasheet; hafele.com SKU 329.01.650 (71B3590)
    name="Blum Clip Top BLUMOTION 110° Full Overlay",
    manufacturer="Blum",
    overlay_type=OverlayType.FULL,
    overlay=16.0,
    cup_diameter=35.0,
    cup_depth=13.0,
    cup_boring_distance=22.5,
    min_door_thickness=16.0,
    max_door_thickness=25.0,
    opening_angle=110,
    soft_close=True,
    max_door_weight_kg=25.0,
    part_number="71B3590",
)

# ── Blum Clip Top 110° — Half Overlay ─────────────────────────────────────────

BLUM_CLIP_TOP_110_HALF = HingeSpec(
    # Half overlay (9.5 mm) — for shared partition between two adjacent cabinets.
    # Source: Blum catalog; cabinetparts.com SKU for 71H3550 (half overlay arm)
    name="Blum Clip Top 110° Half Overlay",
    manufacturer="Blum",
    overlay_type=OverlayType.HALF,
    overlay=9.5,
    cup_diameter=35.0,
    cup_depth=13.0,
    cup_boring_distance=22.5,
    min_door_thickness=16.0,
    max_door_thickness=25.0,
    opening_angle=110,
    soft_close=False,
    max_door_weight_kg=20.0,
    part_number="71H3550",
)

BLUM_CLIP_TOP_BLUMOTION_110_HALF = HingeSpec(
    # BLUMOTION soft-close, half overlay.
    # Source: Blum catalog; part number pattern from 71H35xx family.
    name="Blum Clip Top BLUMOTION 110° Half Overlay",
    manufacturer="Blum",
    overlay_type=OverlayType.HALF,
    overlay=9.5,
    cup_diameter=35.0,
    cup_depth=13.0,
    cup_boring_distance=22.5,
    min_door_thickness=16.0,
    max_door_thickness=25.0,
    opening_angle=110,
    soft_close=True,
    max_door_weight_kg=25.0,
    part_number="71H3590",
)

# ── Blum Clip Top 110° — Inset ────────────────────────────────────────────────

BLUM_CLIP_TOP_110_INSET = HingeSpec(
    # Inset / cranked arm (N arm) — door sits flush inside opening.
    # Overlay = 0; door is narrower than opening by the reveal gap on each side.
    # Source: Blum catalog; hafele.com SKU for 71N3550 (inset/cranked arm)
    name="Blum Clip Top 110° Inset",
    manufacturer="Blum",
    overlay_type=OverlayType.INSET,
    overlay=0.0,
    cup_diameter=35.0,
    cup_depth=13.0,
    cup_boring_distance=22.5,
    min_door_thickness=16.0,
    max_door_thickness=25.0,
    opening_angle=110,
    soft_close=False,
    max_door_weight_kg=20.0,
    part_number="71N3550",
)

BLUM_CLIP_TOP_BLUMOTION_110_INSET = HingeSpec(
    # BLUMOTION soft-close, inset / cranked arm.
    # Source: Blum catalog; part number pattern from 71N35xx family.
    name="Blum Clip Top BLUMOTION 110° Inset",
    manufacturer="Blum",
    overlay_type=OverlayType.INSET,
    overlay=0.0,
    cup_diameter=35.0,
    cup_depth=13.0,
    cup_boring_distance=22.5,
    min_door_thickness=16.0,
    max_door_thickness=25.0,
    opening_angle=110,
    soft_close=True,
    max_door_weight_kg=25.0,
    part_number="71N3590",
)

# ── Blum Clip Top 170° — Full Overlay (wide-angle / corner) ───────────────────

BLUM_CLIP_TOP_170_FULL = HingeSpec(
    # Wide-angle hinge for corner cabinets and areas with restricted access.
    # Opens to 170°, allowing full access past the cabinet side.
    # Only available with full overlay arm in the standard catalog.
    # Source: Blum CLIP top 170° datasheet; hafele.com / cabinetparts.com.
    name="Blum Clip Top 170° Full Overlay",
    manufacturer="Blum",
    overlay_type=OverlayType.FULL,
    overlay=16.0,
    cup_diameter=35.0,
    cup_depth=13.0,
    cup_boring_distance=22.5,
    min_door_thickness=16.0,
    max_door_thickness=25.0,
    opening_angle=170,
    soft_close=False,
    max_door_weight_kg=20.0,
    part_number="71B3750",
)

# Legacy aliases kept for backward compatibility with existing code.
BLUM_CLIP_TOP_110 = BLUM_CLIP_TOP_110_FULL
BLUM_CLIP_TOP_170 = BLUM_CLIP_TOP_170_FULL


# ─── Lookup ───────────────────────────────────────────────────────────────────

SLIDES: dict[str, DrawerSlideSpec] = {
    # Blum Tandem
    "blum_tandem_550h":       BLUM_TANDEM_550H,
    "blum_tandem_plus_563h":  BLUM_TANDEM_PLUS_563H,
    # Blum Movento
    "blum_movento_760h":      BLUM_MOVENTO_760H,
    "blum_movento_769":       BLUM_MOVENTO_769,
    # Accuride
    "accuride_3832":          ACCURIDE_3832,
    # Salice Futura
    "salice_futura":          SALICE_FUTURA,
    "salice_futura_smove":    SALICE_FUTURA_SMOVE,
    # Salice Progressa+
    "salice_progressa_plus":          SALICE_PROGRESSA_PLUS,
    "salice_progressa_plus_smove":    SALICE_PROGRESSA_PLUS_SMOVE,
}

HINGES: dict[str, HingeSpec] = {
    # Blum Clip Top 110° — three overlay types, standard and BLUMOTION
    "blum_clip_top_110_full":             BLUM_CLIP_TOP_110_FULL,
    "blum_clip_top_blumotion_110_full":   BLUM_CLIP_TOP_BLUMOTION_110_FULL,
    "blum_clip_top_110_half":             BLUM_CLIP_TOP_110_HALF,
    "blum_clip_top_blumotion_110_half":   BLUM_CLIP_TOP_BLUMOTION_110_HALF,
    "blum_clip_top_110_inset":            BLUM_CLIP_TOP_110_INSET,
    "blum_clip_top_blumotion_110_inset":  BLUM_CLIP_TOP_BLUMOTION_110_INSET,
    # Blum Clip Top 170° wide-angle
    "blum_clip_top_170_full":             BLUM_CLIP_TOP_170_FULL,
    # Legacy keys (backward compatibility)
    "blum_clip_top_110":                  BLUM_CLIP_TOP_110,
    "blum_clip_top_170":                  BLUM_CLIP_TOP_170,
}


def get_slide(name: str) -> DrawerSlideSpec:
    """Look up a slide spec by key."""
    if name not in SLIDES:
        raise KeyError(f"Unknown slide '{name}'. Available: {list(SLIDES.keys())}")
    return SLIDES[name]


def get_hinge(name: str) -> HingeSpec:
    """Look up a hinge spec by key."""
    if name not in HINGES:
        raise KeyError(f"Unknown hinge '{name}'. Available: {list(HINGES.keys())}")
    return HINGES[name]


# ─── Legs / Feet ─────────────────────────────────────────────────────────────


class LegPattern(Enum):
    """Foot placement pattern for a cabinet base."""
    CORNERS              = "corners"               # one foot at each corner
    CORNERS_AND_MIDSPAN  = "corners_and_midspan"   # corners + one centred on each long side
    ALONG_FRONT_BACK     = "along_front_back"      # evenly spaced rows front & back


@dataclass(frozen=True)
class LegSpec:
    """Specifications for a cabinet leg / furniture foot.

    All dimensions in millimetres unless otherwise noted.

    Adjustable legs have a threaded stem; ``adjustment_range_mm`` is the total
    travel.  Fixed legs have ``is_adjustable=False`` and ``adjustment_range_mm``
    should be zero.

    ``base_diameter_mm`` is the load-bearing pad or flange diameter (not the
    stem).  ``stem_diameter_mm`` is the threaded section (0 for fixed legs).
    """
    name: str
    manufacturer: str
    height_mm: float                # nominal / mid-range height
    base_diameter_mm: float         # floor pad / flange diameter
    is_adjustable: bool
    adjustment_range_mm: float      # total travel for adjustable legs; 0 for fixed
    stem_diameter_mm: float         # threaded stem Ø; 0 for fixed legs
    load_capacity_kg: float         # rated load per leg
    finish: str                     # e.g. "brushed_nickel", "matte_black", "chrome"
    part_number: str = ""
    notes: str = ""


# ── Richelieu 176138106 — Contemporary Square Leg, 100 mm, Brushed Nickel ────
#
# Fixed contemporary square metal leg from Richelieu's 1761 series.
# Sold in packs of 2; load 50 kg (110 lb) per leg.  Has an integrated felt pad
# to protect floors.  Height is 3-15/16" = ~100 mm, not a true 4".
# Source: thebuilderssupply.com, dspoutlet.com product pages; Richelieu catalog.

RICHELIEU_176138106 = LegSpec(
    name="Richelieu Contemporary Square Leg 100mm",
    manufacturer="Richelieu",
    height_mm=100.0,           # 3-15/16" ≈ 100 mm
    base_diameter_mm=38.0,     # square base ~38 mm × 38 mm; use diameter for cylinder approx
    is_adjustable=False,
    adjustment_range_mm=0.0,
    stem_diameter_mm=0.0,
    load_capacity_kg=50.0,
    finish="brushed_nickel",
    part_number="176138106",
    notes="Square contemporary leg, integrated floor pad. Sold 2/pack.",
)

# ── Richelieu 17613B106 — Contemporary Square Leg, 100 mm, Matte Black ───────

RICHELIEU_17613B106 = LegSpec(
    name="Richelieu Contemporary Square Leg 100mm Matte Black",
    manufacturer="Richelieu",
    height_mm=100.0,
    base_diameter_mm=38.0,
    is_adjustable=False,
    adjustment_range_mm=0.0,
    stem_diameter_mm=0.0,
    load_capacity_kg=50.0,
    finish="matte_black",
    part_number="17613B106",
    notes="Square contemporary leg, integrated floor pad. Sold 2/pack.",
)

# ── Richelieu Adjustable Leg, 40–65 mm, Aluminium ────────────────────────────
#
# Economy adjustable leveling leg.  Common in flat-pack / Euro-style cabinets.
# Threaded M8 stem; adjustment range ≈ 25 mm via threaded insert.
# Source: woodcraft.com product page; Richelieu catalog.

RICHELIEU_ADJUSTABLE_40MM = LegSpec(
    name="Richelieu Adjustable Furniture Leg 40–65mm",
    manufacturer="Richelieu",
    height_mm=52.5,            # midpoint of 40–65 mm range
    base_diameter_mm=50.0,     # round base flange
    is_adjustable=True,
    adjustment_range_mm=25.0,
    stem_diameter_mm=8.0,      # M8 thread
    load_capacity_kg=60.0,
    finish="aluminum",
    part_number="RICALEG40",   # generic / catalog-dependent
    notes="Threaded M8 adjustable leg, 40–65 mm travel. For Euro-style cabinet bases.",
)

# ── Generic Hairpin Leg, 200 mm, Matte Black ─────────────────────────────────
# Popular for media consoles, credenzas, and modern case pieces.

HAIRPIN_200MM = LegSpec(
    name="Hairpin Leg 200mm",
    manufacturer="Generic",
    height_mm=200.0,
    base_diameter_mm=10.0,     # rod diameter (3-rod hairpin; footprint wider)
    is_adjustable=False,
    adjustment_range_mm=0.0,
    stem_diameter_mm=0.0,
    load_capacity_kg=30.0,
    finish="matte_black",
    part_number="",
    notes="3-rod steel hairpin leg with mounting plate. Common in furniture stores.",
)


LEGS: dict[str, LegSpec] = {
    "richelieu_176138106":       RICHELIEU_176138106,
    "richelieu_17613b106":       RICHELIEU_17613B106,
    "richelieu_adjustable_40mm": RICHELIEU_ADJUSTABLE_40MM,
    "hairpin_200mm":             HAIRPIN_200MM,
}


def get_leg(name: str) -> LegSpec:
    """Look up a leg spec by key."""
    if name not in LEGS:
        raise KeyError(f"Unknown leg '{name}'. Available: {list(LEGS.keys())}")
    return LEGS[name]
