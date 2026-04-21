"""
BOM extraction and cutlist optimiser.

Extracts a bill of materials from cabinet assemblies and formats it for
cutlist optimisation. Supports output to:
- JSON (panel list for external tools or further processing)
- CSV (for manual reference / spreadsheet import)
- Console table

Also produces hardware BOMs (pulls, hinges, slides, legs) as
``HardwareLine`` records with pack-quantity procurement math.

In-process sheet optimisation is available via :func:`optimize_cutlist` when
``rectpack`` is installed (``uv pip install -e '.[cutlist]'``).  The
optimiser uses a **guillotine algorithm** (GuillotineBssfSas) which models
real table-saw and track-saw cuts: every cut runs straight across the full
remaining width or height of the sheet, so the resulting layout is always
physically executable at the saw.

All dimensions in millimeters.
"""

import csv
import json
import io
import math
from dataclasses import dataclass, field, asdict
from typing import Optional

try:
    import rectpack as _rectpack
    _RECTPACK_AVAILABLE = True
except ImportError:
    _rectpack = None  # type: ignore[assignment]
    _RECTPACK_AVAILABLE = False

from .cabinet import PartInfo


@dataclass
class CutlistPanel:
    """A single panel to be cut from sheet stock."""
    name: str
    length: float  # along grain
    width: float  # across grain
    thickness: float
    quantity: int = 1
    grain_direction: str = "length"
    material: str = "baltic_birch"
    edge_band: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class SheetStock:
    """Available sheet stock for optimization."""
    name: str
    length: float
    width: float
    thickness: float
    quantity: int = 1  # number of sheets available
    material: str = "baltic_birch"
    cost: float = 0.0  # cost per sheet


# ─── Standard Sheet Sizes ─────────────────────────────────────────────────────

SHEET_4x8_3_4 = SheetStock(
    name="4x8 3/4 Baltic Birch",
    length=2440,
    width=1220,
    thickness=18,
    material="baltic_birch",
)

SHEET_4x8_1_2 = SheetStock(
    name="4x8 1/2 Baltic Birch",
    length=2440,
    width=1220,
    thickness=12,
    material="baltic_birch",
)

SHEET_4x8_1_4 = SheetStock(
    name="4x8 1/4 Baltic Birch",
    length=2440,
    width=1220,
    thickness=6,
    material="baltic_birch",
)

SHEET_5x5_3_4 = SheetStock(
    name="5x5 3/4 Baltic Birch",
    length=1525,
    width=1525,
    thickness=18,
    material="baltic_birch",
)


# ─── BOM Extraction ──────────────────────────────────────────────────────────


def extract_bom(parts: list[PartInfo]) -> list[CutlistPanel]:
    """Extract a cutlist-ready BOM from PartInfo list.

    Determines panel length/width from the CadQuery shape bounding box,
    orienting based on grain_direction metadata.
    """
    panels = []

    for part in parts:
        try:
            bb = part.shape.val().BoundingBox()
        except AttributeError:
            try:
                bb = part.shape.BoundingBox()
            except Exception:
                # Fallback: skip if we can't get dimensions
                continue

        # Get the three dimensions, sorted largest to smallest
        dims = sorted([bb.xlen, bb.ylen, bb.zlen], reverse=True)

        # For sheet goods, the two largest dimensions are length and width,
        # the smallest is thickness (should match material_thickness)
        if part.grain_direction == "length":
            panel_length = dims[0]
            panel_width = dims[1]
        else:  # "width" — grain runs along the shorter dimension
            panel_length = dims[1]
            panel_width = dims[0]

        panels.append(CutlistPanel(
            name=part.name,
            length=round(panel_length, 1),
            width=round(panel_width, 1),
            thickness=round(part.material_thickness, 1),
            grain_direction=part.grain_direction,
            edge_band=part.edge_band,
            notes=part.notes,
        ))

    return panels


def extract_bom_parametric(parts: list[PartInfo]) -> list[CutlistPanel]:
    """Extract BOM from PartInfo without requiring CadQuery geometry.

    Attempts full bounding-box extraction first (requires CadQuery shapes).
    Falls back to zero-dimension placeholder panels if geometry is unavailable
    (e.g. CadQuery not installed, or shapes are None), so the caller always
    receives exactly one CutlistPanel per input PartInfo.
    """
    try:
        result = extract_bom(parts)
        # extract_bom silently skips parts whose shapes are unavailable rather
        # than raising, so check that we got a complete result before returning.
        if len(result) == len(parts):
            return result
    except Exception:
        pass

    # Geometry not available for all parts — return zero-dimension fallback panels.
    return [
        CutlistPanel(
            name=part.name,
            length=0,
            width=0,
            thickness=part.material_thickness,
            grain_direction=part.grain_direction,
            edge_band=part.edge_band,
            notes=(part.notes + " " if part.notes else "") +
                  "[dimensions not computed — CadQuery not available]",
        )
        for part in parts
    ]


def consolidate_bom(panels: list[CutlistPanel]) -> list[CutlistPanel]:
    """Merge identical panels into single entries with quantity > 1."""
    consolidated: dict[tuple, CutlistPanel] = {}

    for panel in panels:
        key = (
            round(panel.length, 1),
            round(panel.width, 1),
            round(panel.thickness, 1),
            panel.grain_direction,
            panel.material,
            tuple(panel.edge_band),
        )
        if key in consolidated:
            consolidated[key].quantity += panel.quantity
            # Track which part names were merged into this entry
            consolidated[key].notes += f", {panel.name}"
        else:
            # Preserve original notes; track part names separately in a leading tag
            new_panel = CutlistPanel(
                name=panel.name,
                length=panel.length,
                width=panel.width,
                thickness=panel.thickness,
                quantity=panel.quantity,
                grain_direction=panel.grain_direction,
                material=panel.material,
                edge_band=list(panel.edge_band),
                notes=panel.notes,
            )
            consolidated[key] = new_panel

    return list(consolidated.values())


# ─── Output Formats ──────────────────────────────────────────────────────────


def to_json(
    panels: list[CutlistPanel],
    stock: list[SheetStock] | None = None,
    kerf: float = 3.2,  # table saw blade kerf
) -> str:
    """Export cutlist as JSON.

    The output structure mirrors the cut-optimizer-2d crate's input schema
    (panels + optional stock array with cut_width) and is suitable as a
    record of the panel list or for import into external tools.

    In-process optimisation is handled by :func:`optimize_cutlist` — this
    function is purely a serialisation step.
    """
    output = {
        "cut_width": kerf,
        "panels": [
            {
                "name": p.name,
                "length": p.length,
                "width": p.width,
                "quantity": p.quantity,
                "can_rotate": p.grain_direction == "",  # no grain = can rotate
            }
            for p in panels
        ],
    }

    if stock:
        output["stock"] = [
            {
                "name": s.name,
                "length": s.length,
                "width": s.width,
                "quantity": s.quantity,
            }
            for s in stock
        ]

    return json.dumps(output, indent=2)


def to_csv(panels: list[CutlistPanel]) -> str:
    """Export cutlist as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Name", "Length (mm)", "Width (mm)", "Thickness (mm)",
        "Quantity", "Grain", "Material", "Edge Band", "Notes",
    ])
    for p in panels:
        writer.writerow([
            p.name, p.length, p.width, p.thickness,
            p.quantity, p.grain_direction, p.material,
            ", ".join(p.edge_band), p.notes,
        ])
    return output.getvalue()


def print_bom(panels: list[CutlistPanel]) -> None:
    """Print a formatted BOM table to console."""
    print()
    print(f"{'Name':<25} {'L (mm)':>8} {'W (mm)':>8} {'T (mm)':>8} {'Qty':>4} {'Grain':<8} {'Edge Band':<12}")
    print("-" * 85)
    for p in panels:
        eb = ", ".join(p.edge_band) if p.edge_band else "—"
        print(f"{p.name:<25} {p.length:>8.1f} {p.width:>8.1f} {p.thickness:>8.1f} {p.quantity:>4} {p.grain_direction:<8} {eb:<12}")
    print()

    # Summary by thickness
    thickness_groups: dict[float, list[CutlistPanel]] = {}
    for p in panels:
        thickness_groups.setdefault(p.thickness, []).append(p)

    print("Sheet stock needed:")
    for t, group in sorted(thickness_groups.items()):
        total_area = sum(p.length * p.width * p.quantity for p in group)
        sheet_area = 2440 * 1220  # 4x8 sheet
        sheets_needed = total_area / sheet_area
        print(f"  {t:.0f}mm: {len(group)} parts, ~{total_area/1e6:.2f}m² total, ~{sheets_needed:.1f} sheets (4×8)")
    print()


# ─── Sheet-goods optimisation ────────────────────────────────────────────────


@dataclass
class Placement:
    """Position of one panel piece on a specific sheet as packed by rectpack."""
    panel_name: str
    sheet_index: int    # 0-based sheet number
    x: float            # mm from bottom-left corner of sheet
    y: float
    placed_length: float  # dimension along x-axis as placed (may differ from
    placed_width: float   #   nominal if rotated — see ``rotated`` flag)
    rotated: bool         # True when piece was rotated 90° from nominal orientation


@dataclass
class OptimizationResult:
    """Sheet-goods bin-packing result produced by :func:`optimize_cutlist`.

    Attributes
    ----------
    sheets_used:
        Number of stock sheets that contain at least one placed piece.
    waste_pct:
        Percentage of consumed sheet area that is unused (off-cuts + gaps).
        Computed as ``(sheet_area - panel_area) / sheet_area * 100``.
    placements:
        One entry per placed piece (a panel with quantity=3 produces 3 entries).
    unplaced:
        Panel *names* whose pieces could not be placed — either because they
        are larger than the stock sheet, or because the packer ran out of bins.
        Empty list means everything fits.
    stock_sheet:
        The :class:`SheetStock` used for this optimisation run.
    """
    sheets_used: int
    waste_pct: float
    placements: list[Placement]
    unplaced: list[str]
    stock_sheet: SheetStock

    @property
    def is_complete(self) -> bool:
        """True when every requested piece was successfully placed."""
        return len(self.unplaced) == 0


def optimize_cutlist(
    panels: list[CutlistPanel],
    stock_sheet: SheetStock | None = None,
    kerf: float = 3.2,
) -> OptimizationResult:
    """Pack *panels* onto sheets of *stock_sheet* and return layout results.

    Uses rectpack's **GuillotineBssfSas** algorithm, which models real
    table-saw and track-saw cuts: every cut goes straight across the full
    remaining width or height of the sheet (a "guillotine" cut), so the
    resulting layout can always be executed at the saw without repositioning.

    *Bssf* (Best Short Side Fit) places each piece where the shorter leftover
    dimension is minimised, keeping off-cuts as usable as possible.  *Sas*
    (Short Axis Split) splits the remaining free rectangle along its shorter
    axis after each placement, which tends to preserve wider off-cuts for
    subsequent pieces.

    Panels are expanded from their ``quantity`` field into individual pieces
    and sorted largest-area-first before packing, which improves bin-fill
    efficiency.  Grain direction is always respected: rotation is disabled
    globally because woodworking panels almost always carry a grain constraint.

    Each piece has ``kerf`` mm added to both dimensions so that saw-blade
    width is accounted for in the sheet layout.

    Parameters
    ----------
    panels:
        Consolidated (or raw) list of :class:`CutlistPanel` objects.  Panels
        with ``quantity > 1`` are expanded internally.
    stock_sheet:
        Sheet to pack onto.  Defaults to :data:`SHEET_4x8_3_4` (2440 × 1220 mm,
        18 mm thick).
    kerf:
        Saw-blade kerf in mm added to each panel's length and width.

    Returns
    -------
    OptimizationResult

    Raises
    ------
    ImportError
        When rectpack is not installed.  Install with::

            uv pip install -e '.[cutlist]'
    """
    if not _RECTPACK_AVAILABLE:
        raise ImportError(
            "rectpack is required for in-process sheet optimisation. "
            "Install with: uv pip install -e '.[cutlist]'"
        )

    if stock_sheet is None:
        stock_sheet = SHEET_4x8_3_4

    # Effective sheet interior after one kerf margin on each edge.
    sheet_l = stock_sheet.length - kerf
    sheet_w = stock_sheet.width - kerf

    # Expand each panel's quantity into individual (length, width, name, idx)
    # tuples, then sort largest-area first for better bin-fill.
    expanded: list[tuple[float, float, str, int]] = [
        (panel.length, panel.width, panel.name, i)
        for panel in panels
        for i in range(panel.quantity)
    ]
    expanded.sort(key=lambda e: e[0] * e[1], reverse=True)

    # Pre-flight: separate panels that are simply too large for the sheet.
    # We only flag the panel *name* once even if multiple pieces are oversized.
    oversized: list[str] = []
    packable: list[tuple[float, float, str, int]] = []
    piece_dims: dict[tuple[str, int], tuple[float, float]] = {}

    for length, width, name, idx in expanded:
        if length + kerf > sheet_l or width + kerf > sheet_w:
            if name not in oversized:
                oversized.append(name)
        else:
            packable.append((length, width, name, idx))
            piece_dims[(name, idx)] = (length, width)

    # --- Run rectpack (guillotine algorithm) ---------------------------------
    # GuillotineBssfSas: Best Short Side Fit + Short Axis Split.
    # Every cut is a full-width guillotine cut — matches table-saw workflow.
    packer = _rectpack.newPacker(
        pack_algo=_rectpack.GuillotineBssfSas,
        rotation=False,
    )

    # Upper bound on bins: worst case every piece on its own sheet.
    packer.add_bin(sheet_l, sheet_w, count=max(1, len(packable)))

    for length, width, name, idx in packable:
        packer.add_rect(length + kerf, width + kerf, rid=(name, idx))

    packer.pack()

    # --- Collect placements --------------------------------------------------
    placements: list[Placement] = []
    placed_rids: set[tuple[str, int]] = set()

    for bin_idx, abin in enumerate(packer):
        for rect in abin:
            rid: tuple[str, int] = rect.rid
            placed_rids.add(rid)
            orig_l, orig_w = piece_dims[rid]
            # Detect rotation: rectpack swaps width/height when rotating.
            rotated = abs(rect.width - (orig_l + kerf)) > 0.01
            placements.append(Placement(
                panel_name=rid[0],
                sheet_index=bin_idx,
                x=round(rect.x, 1),
                y=round(rect.y, 1),
                placed_length=round(rect.width, 1),
                placed_width=round(rect.height, 1),
                rotated=rotated,
            ))

    # Any packable piece not in placed_rids was dropped by the packer (should
    # not happen with count=len(packable) but guard anyway).
    unplaced: list[str] = list(oversized)
    for _, _, name, idx in packable:
        if (name, idx) not in placed_rids and name not in unplaced:
            unplaced.append(name)

    # --- Waste calculation ---------------------------------------------------
    sheets_used = len({p.sheet_index for p in placements})
    if sheets_used == 0:
        waste_pct = 0.0
    else:
        total_sheet_area = sheets_used * stock_sheet.length * stock_sheet.width
        placed_area = sum(
            (piece_dims[rid][0] + kerf) * (piece_dims[rid][1] + kerf)
            for rid in placed_rids
        )
        waste_pct = max(0.0, (total_sheet_area - placed_area) / total_sheet_area * 100)

    return OptimizationResult(
        sheets_used=sheets_used,
        waste_pct=round(waste_pct, 1),
        placements=placements,
        unplaced=unplaced,
        stock_sheet=stock_sheet,
    )


# ─── Hardware BOM ────────────────────────────────────────────────────────────
#
# Hardware lines track the procurement side of the bill of materials: how many
# *pieces* of a given SKU are needed, what the pack size is, and therefore how
# many packs to order. They are produced alongside the panel cutlist but do
# not flow through the sheet-goods optimizer.


@dataclass
class HardwareLine:
    """A single hardware SKU with procurement math.

    ``pieces_needed`` is the actual quantity required by the design.
    ``pack_quantity`` is how many pieces ship per SKU pack (e.g. IKEA HACKÅS
    pulls sell in 2-packs, so pack_quantity=2). The derived properties turn
    that into the number of packs to order and the resulting leftover pieces.
    """
    sku: str               # stable key, e.g. "topknobs-hb-128"
    category: str          # "pull" | "hinge" | "slide" | "leg"
    name: str
    brand: str
    model_number: str
    pieces_needed: int
    pack_quantity: int = 1
    notes: str = ""

    @property
    def packs_to_order(self) -> int:
        """Smallest pack count that covers pieces_needed."""
        if self.pieces_needed <= 0:
            return 0
        pq = max(1, int(self.pack_quantity))
        return math.ceil(self.pieces_needed / pq)

    @property
    def pieces_ordered(self) -> int:
        """Total pieces received given packs_to_order × pack_quantity."""
        return self.packs_to_order * max(1, int(self.pack_quantity))

    @property
    def leftover(self) -> int:
        """Pieces remaining after installation (always ≥ 0)."""
        return self.pieces_ordered - self.pieces_needed


# ─── Pull BOM extractors ─────────────────────────────────────────────────────
#
# These functions inspect a DrawerConfig / DoorConfig / CabinetConfig and
# return ``HardwareLine`` objects describing the pulls needed.  They rely on
# the per-config ``pull_placements`` machinery added in Phase 3, so placement
# rules (single vs dual, applied_face=False suppression, door-pair doubling)
# stay in one place.


def _pull_line(sku: str, pieces: int, notes: str = "") -> Optional[HardwareLine]:
    """Build a HardwareLine from a pull catalog key.

    Returns ``None`` for zero pieces or unknown keys — unknown keys are the
    responsibility of the evaluator, not the BOM extractor.
    """
    if pieces <= 0 or not sku:
        return None
    # Import here to avoid a hard dependency at module-import time if the
    # catalog somehow failed to load (tests exercise that path via monkey-
    # patching PULLS).
    from .hardware import get_pull
    try:
        spec = get_pull(sku)
    except KeyError:
        return None
    return HardwareLine(
        sku=sku,
        category="pull",
        name=spec.name,
        brand=spec.brand,
        model_number=spec.model_number,
        pieces_needed=pieces,
        pack_quantity=spec.pack_quantity,
        notes=notes,
    )


def pull_line_from_drawer(drawer_cfg) -> Optional[HardwareLine]:
    """Return the HardwareLine for this drawer's pulls, or None.

    Returns None when the drawer has no pull_key, no applied face, or the
    key refers to a pull missing from the catalog.
    """
    if drawer_cfg.pull_key is None:
        return None
    try:
        placements = drawer_cfg.pull_placements
    except KeyError:
        return None
    n = len(placements)
    return _pull_line(drawer_cfg.pull_key, n)


def pull_line_from_door(door_cfg) -> Optional[HardwareLine]:
    """Return the HardwareLine for this door config's pulls, or None.

    Uses ``total_pull_count``, which already accounts for door pairs.
    """
    if door_cfg.pull_key is None:
        return None
    try:
        _ = door_cfg.pull_placements  # force resolve so unknown keys raise
    except KeyError:
        return None
    n = door_cfg.total_pull_count
    return _pull_line(door_cfg.pull_key, n)


def pull_lines_for_cabinet_config(cab_cfg) -> list[HardwareLine]:
    """Walk a CabinetConfig's drawer_config and return a consolidated list of
    pull ``HardwareLine`` entries.

    Mirrors ``drawers_from_cabinet_config`` / ``doors_from_cabinet_config``:
    one drawer pull per "drawer" slot, one door pull per "door" slot, two
    door pulls per "door_pair" slot. Multi-column layouts (``cab_cfg.columns``)
    are walked per column.
    """
    # Deferred imports: DrawerConfig / DoorConfig import cadquery lazily, but
    # their parametric paths (the ones we use here) don't require it.
    from .drawer import DrawerConfig
    from .door import DoorConfig

    lines: list[HardwareLine] = []

    def _walk_stack(stack, interior_width: float, interior_depth: float) -> None:
        for opening_h, slot_type in stack:
            if slot_type == "drawer":
                dcfg = DrawerConfig(
                    opening_width=interior_width,
                    opening_height=opening_h,
                    opening_depth=interior_depth,
                    slide_key=cab_cfg.drawer_slide,
                    pull_key=cab_cfg.drawer_pull,
                )
                line = pull_line_from_drawer(dcfg)
                if line is not None:
                    lines.append(line)
            elif slot_type in ("door", "door_pair"):
                num_doors = 2 if slot_type == "door_pair" else 1
                dcfg = DoorConfig(
                    opening_width=interior_width,
                    opening_height=opening_h,
                    num_doors=num_doors,
                    hinge_key=cab_cfg.door_hinge,
                    pull_key=cab_cfg.door_pull,
                )
                line = pull_line_from_door(dcfg)
                if line is not None:
                    lines.append(line)
            # other slot_types (shelf, open) contribute no pulls

    if getattr(cab_cfg, "columns", None):
        for col in cab_cfg.columns:
            _walk_stack(col.drawer_config, col.width_mm, cab_cfg.interior_depth)
    else:
        _walk_stack(cab_cfg.drawer_config, cab_cfg.interior_width, cab_cfg.interior_depth)

    return consolidate_hardware_lines(lines)


# ─── Consolidation + output ──────────────────────────────────────────────────


def consolidate_hardware_lines(lines: list[HardwareLine]) -> list[HardwareLine]:
    """Merge HardwareLines that share the same SKU, summing pieces_needed.

    Notes are concatenated (comma-separated) for traceability. Input order
    is preserved for the first occurrence of each SKU.
    """
    out: dict[str, HardwareLine] = {}
    order: list[str] = []
    for line in lines:
        if line.sku in out:
            merged = out[line.sku]
            merged.pieces_needed += line.pieces_needed
            if line.notes:
                merged.notes = (
                    f"{merged.notes}, {line.notes}" if merged.notes else line.notes
                )
        else:
            out[line.sku] = HardwareLine(
                sku=line.sku,
                category=line.category,
                name=line.name,
                brand=line.brand,
                model_number=line.model_number,
                pieces_needed=line.pieces_needed,
                pack_quantity=line.pack_quantity,
                notes=line.notes,
            )
            order.append(line.sku)
    return [out[sku] for sku in order]


def to_hardware_csv(lines: list[HardwareLine]) -> str:
    """Export a hardware BOM as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "SKU", "Category", "Name", "Brand", "Model #",
        "Pieces Needed", "Pack Qty", "Packs to Order",
        "Pieces Ordered", "Leftover", "Notes",
    ])
    for line in lines:
        writer.writerow([
            line.sku, line.category, line.name, line.brand, line.model_number,
            line.pieces_needed, line.pack_quantity, line.packs_to_order,
            line.pieces_ordered, line.leftover, line.notes,
        ])
    return buf.getvalue()


def to_hardware_json(lines: list[HardwareLine]) -> str:
    """Export a hardware BOM as JSON.

    Each line includes the derived procurement fields so downstream consumers
    (MCP clients, spreadsheets) don't have to replicate the math.
    """
    payload = {
        "lines": [
            {
                "sku": l.sku,
                "category": l.category,
                "name": l.name,
                "brand": l.brand,
                "model_number": l.model_number,
                "pieces_needed": l.pieces_needed,
                "pack_quantity": l.pack_quantity,
                "packs_to_order": l.packs_to_order,
                "pieces_ordered": l.pieces_ordered,
                "leftover": l.leftover,
                "notes": l.notes,
            }
            for l in lines
        ],
        "totals": {
            "line_count": len(lines),
            "pieces_needed": sum(l.pieces_needed for l in lines),
            "packs_to_order": sum(l.packs_to_order for l in lines),
        },
    }
    return json.dumps(payload, indent=2)


def print_hardware_bom(lines: list[HardwareLine]) -> None:
    """Print a formatted hardware BOM table to console."""
    if not lines:
        print("(no hardware lines)")
        return
    print()
    print(f"{'SKU':<28} {'Cat':<6} {'Name':<32} "
          f"{'Need':>5} {'Pack':>5} {'Order':>6} {'Left':>5}")
    print("-" * 92)
    for l in lines:
        print(
            f"{l.sku:<28} {l.category:<6} {l.name[:32]:<32} "
            f"{l.pieces_needed:>5} {l.pack_quantity:>5} "
            f"{l.packs_to_order:>6} {l.leftover:>5}"
        )
    print()
    tot_pieces = sum(l.pieces_needed for l in lines)
    tot_packs  = sum(l.packs_to_order for l in lines)
    print(f"  {len(lines)} lines, {tot_pieces} pieces, {tot_packs} packs to order")
    print()
