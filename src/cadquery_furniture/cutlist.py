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

try:
    from opcut import common as _opcut_common, csp as _opcut_csp
    _OPCUT_AVAILABLE = True
except ImportError:
    _opcut_common = None  # type: ignore[assignment]
    _opcut_csp = None     # type: ignore[assignment]
    _OPCUT_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4, landscape as _rl_landscape
    from reportlab.lib.units import mm as _rl_mm
    from reportlab.lib.colors import HexColor as _HexColor
    from reportlab.platypus import (
        SimpleDocTemplate as _SimpleDocTemplate,
        Table as _Table,
        TableStyle as _TableStyle,
        Paragraph as _Paragraph,
        Spacer as _Spacer,
        PageBreak as _PageBreak,
        KeepTogether as _KeepTogether,
    )
    from reportlab.platypus.flowables import Flowable as _Flowable
    from reportlab.lib.styles import getSampleStyleSheet as _getSampleStyleSheet, ParagraphStyle as _ParagraphStyle
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False

from .cabinet import PartInfo


# ── Shared colour helpers (used by both HTML and PDF renderers) ───────────────

_PALETTE = [
    "#C8DFA8", "#A8C8DF", "#DFC8A8", "#A8DFC8",
    "#DFA8C8", "#C8A8DF", "#DFD8A8", "#A8D8DF",
    "#DFA8A8", "#A8A8DF", "#D8DFA8", "#A8DFD8",
    "#DFC0A8", "#B8A8DF", "#A8DFB8", "#DFA8D8",
]


def _panel_colour(name: str) -> str:
    """Return a fill colour hex string for a panel name."""
    return _PALETTE[hash(name) % len(_PALETTE)]


def _panel_colour_dark(hex_col: str, factor: float = 0.65) -> str:
    """Darken a hex colour for panel stroke / text."""
    h = hex_col.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#{:02x}{:02x}{:02x}".format(int(r * factor), int(g * factor), int(b * factor))


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
            panel.name,
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
    """Position of one panel piece on a specific sheet."""
    panel_name: str
    sheet_index: int    # 0-based sheet number
    x: float            # mm from bottom-left corner of sheet
    y: float
    placed_length: float  # dimension along x-axis as placed (may differ from
    placed_width: float   #   nominal if rotated — see ``rotated`` flag)
    rotated: bool         # True when piece was rotated 90° from nominal orientation
    cut_sequence: int = 0  # 1-based cut order within the sheet (0 = unset)


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
    grain_mismatched: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True when every requested piece was successfully placed."""
        return len(self.unplaced) == 0


def optimize_cutlist(
    panels: list[CutlistPanel],
    stock_sheet: SheetStock | None = None,
    kerf: float = 3.2,
    algorithm: str = "auto",
) -> OptimizationResult:
    """Lay out *panels* onto sheets and return placement results.

    Parameters
    ----------
    panels:
        Consolidated (or raw) list of :class:`CutlistPanel` objects.  Panels
        with ``quantity > 1`` are expanded internally.
    stock_sheet:
        Sheet to lay out onto.  Defaults to :data:`SHEET_4x8_3_4`.
    kerf:
        Saw-blade kerf in mm.
    algorithm:
        Which optimizer to use.  One of:

        ``"auto"`` (default)
            Use opcut if installed, then rectpack if installed, then strip.
        ``"opcut"``
            opcut FORWARD_GREEDY guillotine (requires ``opcut``).
        ``"rectpack"``
            rectpack GuillotineBssfSas (requires ``rectpack``).
        ``"strip"``
            Pure-Python strip-cutting fallback (always available).
    """
    if stock_sheet is None:
        stock_sheet = SHEET_4x8_3_4

    if not panels:
        return OptimizationResult(
            sheets_used=0, waste_pct=0.0, placements=[],
            unplaced=[], stock_sheet=stock_sheet, grain_mismatched=[],
        )

    if algorithm == "opcut":
        if not _OPCUT_AVAILABLE:
            raise ImportError("opcut is not installed. Install with: uv pip install opcut")
        result = _optimize_with_opcut(panels, stock_sheet, kerf)
        return result if result is not None else _optimize_strip(panels, stock_sheet, kerf)

    if algorithm == "rectpack":
        if not _RECTPACK_AVAILABLE:
            raise ImportError(
                "rectpack is not installed. Install with: uv pip install -e '.[cutlist]'"
            )
        return _optimize_with_rectpack(panels, stock_sheet, kerf)

    if algorithm == "strip":
        return _optimize_strip(panels, stock_sheet, kerf)

    # "auto": opcut → rectpack → strip
    if _OPCUT_AVAILABLE:
        result = _optimize_with_opcut(panels, stock_sheet, kerf)
        if result is not None:
            return result
    if _RECTPACK_AVAILABLE:
        return _optimize_with_rectpack(panels, stock_sheet, kerf)
    return _optimize_strip(panels, stock_sheet, kerf)


def _optimize_with_rectpack(
    panels: list[CutlistPanel],
    stock_sheet: SheetStock,
    kerf: float,
) -> OptimizationResult:
    """Guillotine layout via rectpack GuillotineBssfSas.

    Rotation is disabled globally because grain direction is assumed for all
    panels. Kerf is added to each piece dimension before packing and subtracted
    from placed dimensions in the returned Placement objects.
    """
    sheet_l = stock_sheet.length - kerf
    sheet_w = stock_sheet.width - kerf

    expanded: list[tuple[float, float, str, int]] = [
        (p.length, p.width, p.name, i)
        for p in panels
        for i in range(p.quantity)
    ]
    expanded.sort(key=lambda e: e[0] * e[1], reverse=True)

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

    packer = _rectpack.newPacker(
        pack_algo=_rectpack.GuillotineBssfSas,
        rotation=False,
    )
    packer.add_bin(sheet_l, sheet_w, count=max(1, len(packable)))
    for length, width, name, idx in packable:
        packer.add_rect(length + kerf, width + kerf, rid=(name, idx))
    packer.pack()

    placements: list[Placement] = []
    placed_rids: set[tuple[str, int]] = set()

    for bin_idx, abin in enumerate(packer):
        for rect in abin:
            rid: tuple[str, int] = rect.rid
            placed_rids.add(rid)
            orig_l, orig_w = piece_dims[rid]
            rotated = abs(rect.width - (orig_l + kerf)) > 0.01
            placements.append(Placement(
                panel_name=rid[0],
                sheet_index=bin_idx,
                x=round(rect.x, 1),
                y=round(rect.y, 1),
                placed_length=round(rect.width - kerf, 1),
                placed_width=round(rect.height - kerf, 1),
                rotated=rotated,
            ))

    unplaced: list[str] = list(oversized)
    for _, _, name, idx in packable:
        if (name, idx) not in placed_rids and name not in unplaced:
            unplaced.append(name)

    # Assign per-sheet cut sequence in placement order.
    sheet_counters: dict[int, int] = {}
    for p in placements:
        sheet_counters[p.sheet_index] = sheet_counters.get(p.sheet_index, 0) + 1
        p.cut_sequence = sheet_counters[p.sheet_index]

    sheets_used = len({p.sheet_index for p in placements})
    if sheets_used == 0:
        waste_pct = 0.0
    else:
        total_area = sheets_used * stock_sheet.length * stock_sheet.width
        placed_area = sum(piece_dims[rid][0] * piece_dims[rid][1] for rid in placed_rids)
        waste_pct = max(0.0, (total_area - placed_area) / total_area * 100)

    return OptimizationResult(
        sheets_used=sheets_used,
        waste_pct=round(waste_pct, 1),
        placements=placements,
        unplaced=unplaced,
        stock_sheet=stock_sheet,
        grain_mismatched=[],
    )


def _optimize_with_opcut(
    panels: list[CutlistPanel],
    stock_sheet: SheetStock,
    kerf: float,
) -> OptimizationResult | None:
    """Guillotine layout via opcut FORWARD_GREEDY.

    Returns None if opcut cannot place all valid items even after several
    retries (caller falls back to strip cutting).

    One kerf is subtracted from each sheet dimension so opcut models edge
    waste correctly; inter-piece kerfs are handled by opcut's cut_width.
    """
    eff_l = stock_sheet.length - kerf
    eff_w = stock_sheet.width  - kerf
    EPS = 0.05

    grain_constrained: set[str] = {
        p.name for p in panels if p.grain_direction not in ("", None)
    }

    oversized: list[str] = []
    valid: list[CutlistPanel] = []
    for p in panels:
        can_rotate = p.name not in grain_constrained
        fits = p.length <= eff_l + EPS and p.width <= eff_w + EPS
        fits_rot = can_rotate and p.width <= eff_l + EPS and p.length <= eff_w + EPS
        if not fits and not fits_rot:
            if p.name not in oversized:
                oversized.append(p.name)
        else:
            valid.append(p)

    if not valid:
        return OptimizationResult(
            sheets_used=0, waste_pct=0.0, placements=[],
            unplaced=oversized, stock_sheet=stock_sheet, grain_mismatched=[],
        )

    items: list = []
    id_to_name: dict[str, str] = {}
    counter = 0
    for p in valid:
        for _ in range(p.quantity):
            iid = f"{p.name}__{counter}"
            counter += 1
            items.append(_opcut_common.Item(
                id=iid,
                width=p.length,
                height=p.width,
                can_rotate=p.name not in grain_constrained,
            ))
            id_to_name[iid] = p.name

    total_area = sum(p.length * p.width * p.quantity for p in valid)
    base = max(1, math.ceil(total_area / (eff_l * eff_w)))

    opcut_panels: list = []
    result = None
    for n in [base, base + 1, base + 2, base + 4]:
        opcut_panels = [
            _opcut_common.Panel(id=f"s{i}", width=eff_l, height=eff_w)
            for i in range(n)
        ]
        params = _opcut_common.Params(
            cut_width=kerf, panels=opcut_panels, items=items,
        )
        try:
            result = _opcut_csp.calculate(params, _opcut_common.Method.FORWARD_GREEDY)
            break
        except _opcut_common.UnresolvableError:
            continue

    if result is None:
        return None

    idx_map = {f"s{i}": i for i in range(len(opcut_panels))}
    placements: list[Placement] = []
    grain_mismatched: list[str] = []

    for used in result.used:
        name = id_to_name[used.item.id]
        if used.rotate:
            placed_l, placed_w = used.item.height, used.item.width
        else:
            placed_l, placed_w = used.item.width, used.item.height
        if used.rotate and name in grain_constrained and name not in grain_mismatched:
            grain_mismatched.append(name)
        placements.append(Placement(
            panel_name=name,
            sheet_index=idx_map[used.panel.id],
            x=round(used.x, 1),
            y=round(used.y, 1),
            placed_length=round(placed_l, 1),
            placed_width=round(placed_w, 1),
            rotated=used.rotate,
        ))

    used_indices = sorted({p.sheet_index for p in placements})
    remap = {old: new for new, old in enumerate(used_indices)}
    for p in placements:
        p.sheet_index = remap[p.sheet_index]

    # Assign per-sheet cut sequence in the order opcut placed each piece.
    sheet_counters: dict[int, int] = {}
    for p in placements:
        sheet_counters[p.sheet_index] = sheet_counters.get(p.sheet_index, 0) + 1
        p.cut_sequence = sheet_counters[p.sheet_index]

    sheets_used = len(used_indices)
    placed_area = sum(p.placed_length * p.placed_width for p in placements)
    total_used = sheets_used * stock_sheet.length * stock_sheet.width
    waste_pct = max(0.0, (total_used - placed_area) / total_used * 100)

    return OptimizationResult(
        sheets_used=sheets_used,
        waste_pct=round(waste_pct, 1),
        placements=placements,
        unplaced=oversized,
        stock_sheet=stock_sheet,
        grain_mismatched=grain_mismatched,
    )


def _optimize_strip(
    panels: list[CutlistPanel],
    stock_sheet: SheetStock,
    kerf: float,
) -> OptimizationResult:
    """Strip-cutting fallback layout (pure Python, no extra dependencies).

    Groups panels into horizontal strips by across-grain dimension, sorted
    widest first.  Within each strip, pieces are arranged left-to-right.
    ``placed_length`` / ``placed_width`` are NET dimensions (no kerf added).
    """
    sheet_l = stock_sheet.length - kerf
    sheet_w = stock_sheet.width  - kerf
    EPS = 0.05

    grain_constrained: set[str] = {
        p.name for p in panels if p.grain_direction not in ("", None)
    }

    oversized: list[str] = []
    oriented: list[tuple[float, float, str, int, bool]] = []

    for p in panels:
        for idx in range(p.quantity):
            if p.name in grain_constrained:
                plen, pwid, rot = p.length, p.width, False
                if plen + kerf > sheet_l + EPS or pwid + kerf > sheet_w + EPS:
                    if p.name not in oversized:
                        oversized.append(p.name)
                else:
                    oriented.append((plen, pwid, p.name, idx, rot))
            else:
                if p.length >= p.width:
                    plen, pwid, rot = p.length, p.width, False
                else:
                    plen, pwid, rot = p.width, p.length, True
                if plen + kerf > sheet_l + EPS or pwid + kerf > sheet_w + EPS:
                    plen, pwid, rot = pwid, plen, not rot
                    if plen + kerf > sheet_l + EPS or pwid + kerf > sheet_w + EPS:
                        if p.name not in oversized:
                            oversized.append(p.name)
                        continue
                oriented.append((plen, pwid, p.name, idx, rot))

    oriented.sort(key=lambda e: (-e[1], -e[0]))

    placements: list[Placement] = []
    sheet_index = 0
    y = 0.0
    x = 0.0
    current_h: float | None = None

    for plen, pwid, name, idx, rotated in oriented:
        pk = plen + kerf
        wk = pwid + kerf

        if current_h is None or abs(pwid - current_h) > EPS:
            if current_h is not None:
                y += current_h + kerf
            current_h = pwid
            x = 0.0
            if y + wk > sheet_w + EPS:
                sheet_index += 1
                y = 0.0

        if x + pk > sheet_l + EPS:
            y += current_h + kerf
            x = 0.0
            if y + wk > sheet_w + EPS:
                sheet_index += 1
                y = 0.0

        placements.append(Placement(
            panel_name=name,
            sheet_index=sheet_index,
            x=round(x, 1),
            y=round(y, 1),
            placed_length=round(plen, 1),
            placed_width=round(pwid, 1),
            rotated=rotated,
        ))
        x += pk

    sheet_counters: dict[int, int] = {}
    for p in placements:
        sheet_counters[p.sheet_index] = sheet_counters.get(p.sheet_index, 0) + 1
        p.cut_sequence = sheet_counters[p.sheet_index]

    sheets_used = len({p.sheet_index for p in placements})
    placed_area = sum(p.placed_length * p.placed_width for p in placements)
    total_area = sheets_used * stock_sheet.length * stock_sheet.width
    waste_pct = max(0.0, (total_area - placed_area) / total_area * 100) if sheets_used else 0.0

    return OptimizationResult(
        sheets_used=sheets_used,
        waste_pct=round(waste_pct, 1),
        placements=placements,
        unplaced=oversized,
        stock_sheet=stock_sheet,
        grain_mismatched=[],
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


def pull_lines_for_cabinet_config(
    cab_cfg, columns_raw: list | None = None
) -> list[HardwareLine]:
    """Walk a CabinetConfig's drawer_config and return a consolidated list of
    pull ``HardwareLine`` entries.

    Mirrors ``drawers_from_cabinet_config`` / ``doors_from_cabinet_config``:
    one drawer pull per "drawer" slot, one door pull per "door" slot, two
    door pulls per "door_pair" slot. Multi-column layouts (``cab_cfg.columns``)
    are walked per column.

    ``columns_raw`` (list of dicts with ``width_mm`` / ``drawer_config`` keys)
    takes priority over ``cab_cfg.columns`` when supplied — used by the MCP
    cutlist tool which pops ``columns`` from args before building the config.
    """
    from .drawer import DrawerConfig
    from .door import DoorConfig

    lines: list[HardwareLine] = []
    interior_depth = cab_cfg.depth - getattr(cab_cfg, "back_thickness", 6.0)

    def _walk_stack(stack, interior_width: float) -> None:
        for item in stack:
            # Accept both OpeningConfig objects and raw [height, type] lists/tuples
            if hasattr(item, "opening_type"):
                opening_h, slot_type = item.height_mm, item.opening_type
                pull_key_override = item.pull_key
                hinge_key_override = item.hinge_key
            else:
                opening_h, slot_type = float(item[0]), str(item[1])
                pull_key_override = hinge_key_override = None

            if slot_type == "drawer":
                dcfg = DrawerConfig(
                    opening_width=interior_width,
                    opening_height=opening_h,
                    opening_depth=interior_depth,
                    slide_key=cab_cfg.drawer_slide,
                    pull_key=pull_key_override or cab_cfg.drawer_pull,
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
                    hinge_key=hinge_key_override or cab_cfg.door_hinge,
                    pull_key=pull_key_override or cab_cfg.door_pull,
                )
                line = pull_line_from_door(dcfg)
                if line is not None:
                    lines.append(line)

    if columns_raw:
        for col in columns_raw:
            col_w = float(col["width_mm"])
            _walk_stack(col.get("drawer_config", []), col_w)
    elif getattr(cab_cfg, "columns", None):
        for col in cab_cfg.columns:
            _walk_stack(col.openings, col.width_mm)
    else:
        _walk_stack(cab_cfg.openings, cab_cfg.interior_width)

    return consolidate_hardware_lines(lines)


# ─── Consolidation + output ──────────────────────────────────────────────────


def slide_lines_for_cabinet_config(cab_cfg, columns_raw: list | None = None) -> list[HardwareLine]:
    """Return HardwareLines for drawer slides required by the cabinet.

    Each drawer needs one slide pair (left + right = 2 pieces).  Slides are
    sold individually so pack_quantity=1.  The SKU is keyed by slide key +
    length so different-length slides on the same model stay separate.
    """
    from .hardware import get_slide
    from .drawer import DrawerConfig

    try:
        slide_spec = get_slide(cab_cfg.drawer_slide)
    except KeyError:
        return []

    interior_depth = cab_cfg.depth - getattr(cab_cfg, "back_thickness", 6.0)

    def _slides_from_stack(stack, interior_width: float) -> list[HardwareLine]:
        lines: list[HardwareLine] = []
        for item in stack:
            if hasattr(item, "opening_type"):
                opening_h, slot_type = item.height_mm, item.opening_type
            else:
                opening_h, slot_type = float(item[0]), str(item[1])
            if slot_type != "drawer":
                continue
            dcfg = DrawerConfig(
                opening_width=interior_width,
                opening_height=opening_h,
                opening_depth=interior_depth,
                slide_key=cab_cfg.drawer_slide,
            )
            length = slide_spec.slide_length_for_depth(dcfg.opening_depth)
            pn = slide_spec.part_numbers.get(length, "")
            sku = f"{cab_cfg.drawer_slide}-{length}mm"
            lines.append(HardwareLine(
                sku=sku,
                category="slide",
                name=slide_spec.name,
                brand=slide_spec.manufacturer,
                model_number=pn or cab_cfg.drawer_slide,
                pieces_needed=2,  # one pair per drawer
                pack_quantity=1,
                notes=f"{length} mm",
            ))
        return lines

    raw: list[HardwareLine] = []
    if columns_raw:
        for col in columns_raw:
            col_w = float(col["width_mm"])
            raw.extend(_slides_from_stack(col.get("drawer_config", []), col_w))
    elif getattr(cab_cfg, "columns", None):
        for col in cab_cfg.columns:
            raw.extend(_slides_from_stack(col.openings, col.width_mm))
    else:
        raw.extend(_slides_from_stack(cab_cfg.openings, cab_cfg.interior_width))

    return consolidate_hardware_lines(raw)


def hinge_lines_for_cabinet_config(cab_cfg, columns_raw: list | None = None) -> list[HardwareLine]:
    """Return HardwareLines for door hinges required by the cabinet.

    Uses ``HingeSpec.hinges_for_height()`` to count hinges per door.
    Hinges are sold individually (pack_quantity=1).
    """
    from .hardware import get_hinge
    from .door import DoorConfig

    try:
        hinge_spec = get_hinge(cab_cfg.door_hinge)
    except KeyError:
        return []

    sku = hinge_spec.part_number or cab_cfg.door_hinge

    def _hinges_from_stack(stack, interior_width: float) -> int:
        total = 0
        for item in stack:
            if hasattr(item, "opening_type"):
                opening_h, slot_type = item.height_mm, item.opening_type
                hinge_key = item.hinge_key or cab_cfg.door_hinge
            else:
                opening_h, slot_type = float(item[0]), str(item[1])
                hinge_key = cab_cfg.door_hinge
            if slot_type not in ("door", "door_pair"):
                continue
            num_doors = 2 if slot_type == "door_pair" else 1
            dcfg = DoorConfig(
                opening_width=interior_width,
                opening_height=opening_h,
                num_doors=num_doors,
                hinge_key=hinge_key,
            )
            total += dcfg.total_hinge_count
        return total

    pieces = 0
    if columns_raw:
        for col in columns_raw:
            pieces += _hinges_from_stack(col.get("drawer_config", []), float(col["width_mm"]))
    elif getattr(cab_cfg, "columns", None):
        for col in cab_cfg.columns:
            pieces += _hinges_from_stack(col.openings, col.width_mm)
    else:
        pieces += _hinges_from_stack(cab_cfg.openings, cab_cfg.interior_width)

    if pieces <= 0:
        return []
    return [HardwareLine(
        sku=sku,
        category="hinge",
        name=hinge_spec.name,
        brand=hinge_spec.manufacturer,
        model_number=sku,
        pieces_needed=pieces,
        pack_quantity=1,
    )]


def leg_lines_for_cabinet_config(cab_cfg) -> list[HardwareLine]:
    """Return a HardwareLine for the cabinet's legs/feet, or an empty list."""
    from .hardware import get_leg

    try:
        leg_spec = get_leg(cab_cfg.leg_key)
    except KeyError:
        return []

    pieces = getattr(cab_cfg, "leg_count", 4)
    if pieces <= 0:
        return []
    sku = leg_spec.part_number or cab_cfg.leg_key
    return [HardwareLine(
        sku=sku,
        category="leg",
        name=leg_spec.name,
        brand=leg_spec.manufacturer,
        model_number=sku,
        pieces_needed=pieces,
        pack_quantity=1,
        notes=f"{leg_spec.height_mm:.0f} mm",
    )]


def joinery_lines_for_cabinet_config(
    cab_cfg, columns_raw: list | None = None
) -> list[HardwareLine]:
    """Return HardwareLines for carcass joinery consumables.

    Counts every panel-to-panel edge joint in the carcass and looks up the
    fastener count using the corresponding joinery spec's ``count_for_span``.
    Returns an empty list for ``dado_rabbet`` (the dado/rabbet itself holds
    the panel — no additional fasteners are needed).

    Joints counted:
      - Top panel to each side (×2)
      - Bottom panel to each side (×2)
      - Each column divider top edge to top panel (×N dividers)
      - Each column divider bottom edge to bottom panel (×N dividers)
      - Each fixed shelf to its two bearing surfaces (×2 per shelf)

    The "span" for each joint is the panel depth (``interior_depth``), since
    fasteners run along the depth direction of the joint edge.
    """
    from .cabinet import CarcassJoinery
    from .joinery import (
        DominoSpec, DominoSize, get_domino_size,
        PocketScrewSpec, pocket_screw_length,
        BiscuitSpec,
        DownelSpec,
    )

    joinery = getattr(cab_cfg, "carcass_joinery", CarcassJoinery.DADO_RABBET)
    if joinery == CarcassJoinery.DADO_RABBET:
        return []

    interior_depth = cab_cfg.depth - getattr(cab_cfg, "back_thickness", 6.0)
    side_t = getattr(cab_cfg, "side_thickness", 18.0)

    # Count joints: top+bottom = 4, each divider adds 2, each shelf adds 2
    n_dividers = max(0, len(columns_raw) - 1) if columns_raw else 0
    global_shelves = len(getattr(cab_cfg, "fixed_shelf_positions", []))
    col_shelves = 0
    if columns_raw:
        for col in columns_raw:
            col_shelves += len(col.get("fixed_shelf_positions", []))
    n_joints = 4 + 2 * n_dividers + 2 * global_shelves + 2 * col_shelves

    if joinery == CarcassJoinery.FLOATING_TENON:
        spec = DominoSpec(size_key="8x40", max_spacing=150.0)
        per_joint = spec.count_for_span(interior_depth)
        total = n_joints * per_joint
        # Domino 8×40 mm — Festool 494869, sold in 50-piece bags
        return consolidate_hardware_lines([HardwareLine(
            sku="festool-494869",
            category="joinery",
            name="Festool Domino 8×40 mm",
            brand="Festool",
            model_number="494869",
            pieces_needed=total,
            pack_quantity=50,
            notes=f"{per_joint} per joint × {n_joints} joints",
        )])

    if joinery == CarcassJoinery.POCKET_SCREW:
        _SCREW_FRACTIONS = {19: '3/4"', 25: '1"', 32: '1-1/4"', 38: '1-1/2"', 51: '2"', 64: '2-1/2"'}
        spec = PocketScrewSpec()
        per_joint = spec.count_for_span(interior_depth)
        total = n_joints * per_joint
        screw_len_mm = int(pocket_screw_length(side_t))
        screw_len_str = _SCREW_FRACTIONS.get(screw_len_mm, f"{screw_len_mm}mm")
        return consolidate_hardware_lines([HardwareLine(
            sku=f"kreg-sml-c{screw_len_mm}-100",
            category="joinery",
            name=f"Pocket Screw {screw_len_str} coarse thread",
            brand="Kreg",
            model_number=f"SML-C{int(screw_len_mm)}-100",
            pieces_needed=total,
            pack_quantity=100,
            notes=f"{per_joint} per joint × {n_joints} joints",
        )])

    if joinery == CarcassJoinery.BISCUIT:
        spec = BiscuitSpec(size="#10", max_spacing=100.0)
        per_joint = spec.count_for_span(interior_depth)
        total = n_joints * per_joint
        return consolidate_hardware_lines([HardwareLine(
            sku="biscuit-10-100pk",
            category="joinery",
            name="Biscuit #10",
            brand="",
            model_number="",
            pieces_needed=total,
            pack_quantity=100,
            notes=f"{per_joint} per joint × {n_joints} joints",
        )])

    if joinery == CarcassJoinery.DOWEL:
        spec = DownelSpec(diameter=8.0, max_spacing=96.0)
        per_joint = spec.count_for_span(interior_depth)
        total = n_joints * per_joint
        return consolidate_hardware_lines([HardwareLine(
            sku="dowel-8x40-50pk",
            category="joinery",
            name="Hardwood Dowel 8×40 mm",
            brand="",
            model_number="",
            pieces_needed=total,
            pack_quantity=50,
            notes=f"{per_joint} per joint × {n_joints} joints",
        )])

    return []


def drawer_front_screw_lines_for_cabinet_config(
    cab_cfg, columns_raw: list | None = None
) -> list[HardwareLine]:
    """Return HardwareLines for screws that attach false fronts to drawer boxes.

    Standard practice: 2 × #8 × 1-1/4" (32 mm) pan-head screws per false
    front, driven from inside the drawer box face into the false front.
    Screws are sold in boxes of 100.
    """
    n_drawers = 0

    def _count_drawers(stack) -> int:
        return sum(
            1 for item in stack
            if (item.opening_type if hasattr(item, "opening_type") else str(item[1])) == "drawer"
        )

    if columns_raw:
        for col in columns_raw:
            n_drawers += _count_drawers(col.get("drawer_config", []))
    elif getattr(cab_cfg, "columns", None):
        for col in cab_cfg.columns:
            n_drawers += _count_drawers(col.openings)
    else:
        n_drawers = _count_drawers(getattr(cab_cfg, "openings", []))

    if n_drawers == 0:
        return []

    total = n_drawers * 2  # 2 screws per false front
    return [HardwareLine(
        sku="screw-8x32-panhead-100pk",
        category="fastener",
        name='#8 × 1-1/4" Pan Head Screw (false front)',
        brand="",
        model_number="",
        pieces_needed=total,
        pack_quantity=100,
        notes=f"2 per drawer false front × {n_drawers} drawers",
    )]


def hardware_bom_for_cabinet_config(cab_cfg, columns_raw: list | None = None) -> list[HardwareLine]:
    """Return a consolidated hardware BOM for the full cabinet.

    Aggregates pulls, slides, hinges, legs, joinery, and fasteners.
    Categories are ordered: pull → slide → hinge → leg → joinery → fastener.
    """
    lines: list[HardwareLine] = []
    lines.extend(pull_lines_for_cabinet_config(cab_cfg, columns_raw))
    lines.extend(slide_lines_for_cabinet_config(cab_cfg, columns_raw))
    lines.extend(hinge_lines_for_cabinet_config(cab_cfg, columns_raw))
    lines.extend(leg_lines_for_cabinet_config(cab_cfg))
    lines.extend(joinery_lines_for_cabinet_config(cab_cfg, columns_raw))
    lines.extend(drawer_front_screw_lines_for_cabinet_config(cab_cfg, columns_raw))
    return consolidate_hardware_lines(lines)


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


def _guillotine_cuts(
    placements: list[Placement],
    rect_x: float, rect_y: float, rect_w: float, rect_h: float,
    depth: int,
    out: list,
    EPS: float = 2.0,
) -> None:
    """Recursively find guillotine cut lines within a rectangle.

    Each entry appended to *out* is
    ``(depth, pos, orient, x0, y0, x1, y1, is_breakdown, dim_a, dim_b)`` where:

    - ``orient`` is ``'h'`` (horizontal) or ``'v'`` (vertical)
    - coordinates describe the full extent of the cut within its sub-rectangle
    - ``is_breakdown`` is True when both halves still contain multiple pieces
    - ``dim_a`` / ``dim_b`` are the resulting sub-board sizes on each side of
      the cut (in mm), useful for setting the fence
    """
    if len(placements) <= 1:
        return

    # Try horizontal cuts first (rip cuts along the sheet width).
    for cy in sorted({p.y + p.placed_width for p in placements}):
        if cy <= rect_y + EPS or cy >= rect_y + rect_h - EPS:
            continue
        above = [p for p in placements if p.y + p.placed_width <= cy + EPS]
        below = [p for p in placements if p.y >= cy - EPS]
        if above and below and len(above) + len(below) == len(placements):
            is_breakdown = len(above) > 1 and len(below) > 1
            dim_a = round(max(p.y + p.placed_width for p in above) - min(p.y for p in above))
            dim_b = round(max(p.y + p.placed_width for p in below) - min(p.y for p in below))
            out.append((depth, cy, 'h', rect_x, cy, rect_x + rect_w, cy, is_breakdown, dim_a, dim_b))
            _guillotine_cuts(above, rect_x, rect_y, rect_w, cy - rect_y, depth + 1, out, EPS)
            _guillotine_cuts(below, rect_x, cy, rect_w, rect_y + rect_h - cy, depth + 1, out, EPS)
            return

    # Try vertical cuts (crosscuts along the sheet height).
    for cx in sorted({p.x + p.placed_length for p in placements}):
        if cx <= rect_x + EPS or cx >= rect_x + rect_w - EPS:
            continue
        left  = [p for p in placements if p.x + p.placed_length <= cx + EPS]
        right = [p for p in placements if p.x >= cx - EPS]
        if left and right and len(left) + len(right) == len(placements):
            is_breakdown = len(left) > 1 and len(right) > 1
            dim_a = round(max(p.x + p.placed_length for p in left)  - min(p.x for p in left))
            dim_b = round(max(p.x + p.placed_length for p in right) - min(p.x for p in right))
            out.append((depth, cx, 'v', cx, rect_y, cx, rect_y + rect_h, is_breakdown, dim_a, dim_b))
            _guillotine_cuts(left,  rect_x, rect_y, cx - rect_x,          rect_h, depth + 1, out, EPS)
            _guillotine_cuts(right, cx,     rect_y, rect_x + rect_w - cx, rect_h, depth + 1, out, EPS)
            return


def generate_sheet_layout_html(
    groups: list[tuple[str, list["CutlistPanel"], "OptimizationResult"]],
    cabinet_name: str = "cabinet",
    kerf: float = 3.2,
    hardware_lines: "list[HardwareLine] | None" = None,
) -> str:
    """Generate a self-contained HTML page with per-sheet SVG cut layouts.

    Parameters
    ----------
    groups:
        List of ``(label, panels, opt_result)`` tuples — one per thickness
        group.  Label is the display name shown on the tab.
    cabinet_name:
        Used in the page title and ``<h1>``.

    Returns
    -------
    str
        Complete HTML document (self-contained, no external dependencies).
    """
    # ── SVG builder ────────────────────────────────────────────────────────────
    def _sheet_svg(sheet: SheetStock, placements: list[Placement]) -> str:
        sl, sw = sheet.length, sheet.width
        # Display ~760 px wide; height scaled proportionally.
        disp_w = 760
        disp_h = sw / sl * disp_w

        out: list[str] = []
        pw_stroke = max(0.5, sl * 0.001)
        rx_val = sl * 0.003

        # Placements use top-left origin with y increasing downward, matching SVG.
        # placed_length/placed_width are net panel dimensions (no kerf padding).

        # Sheet background.
        out.append(
            f'<rect x="0" y="0" width="{sl:.1f}" height="{sw:.1f}" '
            f'fill="#F5EED8" stroke="#888" stroke-width="{sl * 0.002:.1f}"/>'
        )

        # Panels.
        for p in placements:
            fill = _panel_colour(p.panel_name)
            stroke = _panel_colour_dark(fill)

            out.append(
                f'<rect x="{p.x:.1f}" y="{p.y:.1f}" '
                f'width="{p.placed_length:.1f}" height="{p.placed_width:.1f}" '
                f'fill="{fill}" stroke="{stroke}" '
                f'stroke-width="{pw_stroke:.1f}" rx="{rx_val:.1f}"/>'
            )

            label = p.panel_name[:24] + ("…" if len(p.panel_name) > 24 else "")
            if p.rotated:
                label += " ↺"
            dim_text = f"{p.placed_length:.0f}×{p.placed_width:.0f} mm"

            min_dim = min(p.placed_length, p.placed_width)
            font_mm = max(min_dim * 0.10, 12)
            dim_font = max(min_dim * 0.07, 9)

            cx = p.x + p.placed_length / 2
            cy_label = p.y + p.placed_width / 2 - font_mm * 0.4
            cy_dim   = cy_label + font_mm * 1.1

            tall = p.placed_width > p.placed_length
            rot_label = f' transform="rotate(-90,{cx:.1f},{cy_label:.1f})"' if tall else ''
            rot_dim   = f' transform="rotate(-90,{cx:.1f},{cy_dim:.1f})"'   if tall else ''

            out.append(
                f'<text x="{cx:.1f}" y="{cy_label:.1f}" '
                f'text-anchor="middle" dominant-baseline="middle" '
                f'font-family="monospace" font-size="{font_mm:.1f}" '
                f'fill="{stroke}" pointer-events="none"{rot_label}>'
                f'{_esc(label)}</text>'
            )
            out.append(
                f'<text x="{cx:.1f}" y="{cy_dim:.1f}" '
                f'text-anchor="middle" dominant-baseline="middle" '
                f'font-family="monospace" font-size="{dim_font:.1f}" '
                f'fill="{stroke}" opacity="0.7" pointer-events="none"{rot_dim}>'
                f'{_esc(dim_text)}</text>'
            )


        # Guillotine cut lines — extract tree, number breakdown cuts in BFS order.
        raw_cuts: list = []
        _guillotine_cuts(placements, 0, 0, sl, sw, depth=0, out=raw_cuts)
        raw_cuts.sort(key=lambda c: (c[0], c[1]))  # BFS: shallower first

        breakdown_stroke = sl * 0.005
        atomic_stroke    = sl * 0.002
        label_r   = sl * 0.018
        label_font = label_r * 1.0
        seq = 0

        for entry in raw_cuts:
            depth, pos, orient, x0, y0, x1, y1, is_breakdown, dim_a, dim_b = entry
            dash = sl * 0.018
            if is_breakdown:
                seq += 1
                colour  = "#c0392b"
                opacity = "0.80"
                sw_line = breakdown_stroke
            else:
                colour  = "#555"
                opacity = "0.35"
                sw_line = atomic_stroke

            out.append(
                f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                f'stroke="{colour}" stroke-width="{sw_line:.1f}" '
                f'stroke-dasharray="{dash:.0f},{dash*0.6:.0f}" opacity="{opacity}"/>'
            )

            if is_breakdown:
                lx = (x0 + x1) / 2 if orient == 'h' else x0
                ly = y0             if orient == 'h' else (y0 + y1) / 2

                # Numbered circle badge.
                out.append(
                    f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="{label_r:.1f}" '
                    f'fill="{colour}" opacity="0.9"/>'
                )
                out.append(
                    f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
                    f'dominant-baseline="middle" font-family="monospace" '
                    f'font-size="{label_font:.1f}" font-weight="bold" fill="#fff" '
                    f'pointer-events="none">{seq}</text>'
                )

                # Dimension label — short side only, placed on that side of the cut.
                dim_font = label_r * 0.9
                pad = label_r * 1.6
                if orient == 'h':
                    if dim_a <= dim_b:
                        tx, ty, anchor = lx + label_r * 1.4, ly - pad, "start"
                        dim_label = f"{dim_a} mm"
                    else:
                        tx, ty, anchor = lx + label_r * 1.4, ly + pad, "start"
                        dim_label = f"{dim_b} mm"
                else:
                    if dim_a <= dim_b:
                        tx, ty, anchor = lx - pad, ly - label_r * 1.4, "end"
                        dim_label = f"{dim_a} mm"
                    else:
                        tx, ty, anchor = lx + pad, ly - label_r * 1.4, "start"
                        dim_label = f"{dim_b} mm"
                rotate = f' transform="rotate(-90,{tx:.1f},{ty:.1f})"' if orient == 'v' else ''
                out.append(
                    f'<text x="{tx:.1f}" y="{ty:.1f}" '
                    f'text-anchor="{anchor}" dominant-baseline="middle" '
                    f'font-family="monospace" font-size="{dim_font:.1f}" '
                    f'fill="{colour}" opacity="0.9" pointer-events="none"{rotate}>'
                    f'{dim_label}</text>'
                )

        # Ruler along the bottom edge.
        tick_font = sl * 0.018
        tick_y_top = sw + sl * 0.005
        tick_y_bot = tick_y_top + sl * 0.010
        out.append(
            f'<line x1="0" y1="{sw:.1f}" x2="{sl:.1f}" y2="{sw:.1f}" '
            f'stroke="#888" stroke-width="{pw_stroke:.1f}"/>'
        )
        for mm in range(0, int(sl) + 1, 200):
            out.append(
                f'<line x1="{mm}" y1="{tick_y_top:.1f}" '
                f'x2="{mm}" y2="{tick_y_bot:.1f}" '
                f'stroke="#666" stroke-width="{pw_stroke:.1f}"/>'
            )
            if mm % 400 == 0:
                out.append(
                    f'<text x="{mm}" y="{tick_y_bot + tick_font:.1f}" '
                    f'text-anchor="middle" font-family="monospace" '
                    f'font-size="{tick_font:.1f}" fill="#666">{mm}</text>'
                )

        vb_h = sw + sl * 0.06
        body = "\n".join(out)
        return (
            f'<svg viewBox="0 0 {sl:.1f} {vb_h:.1f}" '
            f'width="{disp_w}" height="{disp_h:.0f}" '
            f'xmlns="http://www.w3.org/2000/svg" '
            f'style="border:1px solid #ccc;border-radius:4px;background:#fff;">'
            f'{body}</svg>'
        )

    def _esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # ── Build tab HTML ─────────────────────────────────────────────────────────
    tab_buttons: list[str] = []
    tab_panes: list[str] = []

    for tab_idx, (label, _panels, opt) in enumerate(groups):
        active = "active" if tab_idx == 0 else ""
        tab_buttons.append(
            f'<button class="tab-btn {active}" '
            f'onclick="showTab({tab_idx})" id="btn-{tab_idx}">'
            f'{_esc(label)}</button>'
        )

        sheets_count = opt.sheets_used
        by_sheet: dict[int, list[Placement]] = {}
        for p in opt.placements:
            by_sheet.setdefault(p.sheet_index, []).append(p)

        sheet_svgs: list[str] = []
        for si in sorted(by_sheet.keys()):
            sheet_svgs.append(
                f'<div class="sheet-card">'
                f'<h3>Sheet {si + 1} of {sheets_count} '
                f'<span class="dim">'
                f'{opt.stock_sheet.length:.0f} × {opt.stock_sheet.width:.0f} mm '
                f'— {opt.stock_sheet.name}</span></h3>'
                f'{_sheet_svg(opt.stock_sheet, by_sheet[si])}'
                f'</div>'
            )

        notes_html = ""
        if opt.unplaced:
            names = ", ".join(opt.unplaced[:5])
            extra = f" + {len(opt.unplaced) - 5} more" if len(opt.unplaced) > 5 else ""
            notes_html += f'<p class="warn">⚠ Unplaced panels: {_esc(names)}{extra}</p>'
        if opt.grain_mismatched:
            names = ", ".join(opt.grain_mismatched[:5])
            notes_html += (
                f'<p class="warn">⚠ Grain-constrained panels rotated by optimizer '
                f'(verify orientation at saw): {_esc(names)}</p>'
            )

        tab_panes.append(
            f'<div class="tab-pane {active}" id="pane-{tab_idx}">'
            f'<div class="group-stats">'
            f'{sheets_count} sheet{"s" if sheets_count != 1 else ""} · '
            f'{opt.waste_pct:.1f}% waste'
            f'</div>'
            f'{notes_html}'
            f'<div class="sheet-grid">{"".join(sheet_svgs)}</div>'
            f'</div>'
        )

    # ── Hardware BOM tab (optional) ────────────────────────────────────────────
    if hardware_lines:
        bom_idx = len(tab_buttons)
        tab_buttons.append(
            f'<button class="tab-btn" onclick="showTab({bom_idx})" id="btn-{bom_idx}">'
            f'Hardware BOM</button>'
        )
        cat_order = {"pull": 0, "slide": 1, "hinge": 2, "leg": 3}
        sorted_hw = sorted(hardware_lines, key=lambda h: (cat_order.get(h.category, 9), h.name))
        rows = "".join(
            f'<tr>'
            f'<td>{_esc(h.category.title())}</td>'
            f'<td>{_esc(h.name)}</td>'
            f'<td>{_esc(h.brand)}</td>'
            f'<td>{_esc(h.model_number)}</td>'
            f'<td style="text-align:center">{h.pieces_needed}</td>'
            f'<td style="text-align:center">{h.pack_quantity}</td>'
            f'<td style="text-align:center;font-weight:600">{h.packs_to_order}</td>'
            f'<td style="text-align:center">{h.leftover if h.leftover else "—"}</td>'
            f'<td>{_esc(h.notes)}</td>'
            f'</tr>'
            for h in sorted_hw
        )
        bom_table = (
            f'<table class="bom-tbl">'
            f'<thead><tr>'
            f'<th>Category</th><th>Name</th><th>Brand</th><th>Model #</th>'
            f'<th>Needed</th><th>Pack&nbsp;Qty</th><th>Packs&nbsp;to&nbsp;Order</th>'
            f'<th>Leftover</th><th>Notes</th>'
            f'</tr></thead>'
            f'<tbody>{rows}</tbody>'
            f'</table>'
        )
        tab_panes.append(
            f'<div class="tab-pane" id="pane-{bom_idx}">{bom_table}</div>'
        )

    tabs_html = "\n".join(tab_buttons)
    panes_html = "\n".join(tab_panes)

    # ── Legend: panel name → colour ────────────────────────────────────────────
    seen: dict[str, str] = {}
    for _, panels, opt in groups:
        for p in opt.placements:
            if p.panel_name not in seen:
                seen[p.panel_name] = _panel_colour(p.panel_name)
    legend_items = "".join(
        f'<span class="legend-item">'
        f'<span class="legend-swatch" style="background:{col};"></span>'
        f'{_esc(name)}</span>'
        for name, col in seen.items()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_esc(cabinet_name)} — Sheet Layout</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:#f0ede8;color:#222;padding:16px}}
h1{{font-size:1.3rem;font-weight:600;margin-bottom:12px}}
.tabs{{display:flex;gap:6px;margin-bottom:0;flex-wrap:wrap}}
.tab-btn{{
  padding:7px 16px;border:1px solid #bbb;border-bottom:none;
  background:#e0dbd4;border-radius:6px 6px 0 0;cursor:pointer;
  font-size:.85rem;color:#444;
}}
.tab-btn.active{{background:#fff;border-color:#888;color:#111;font-weight:600}}
.tab-pane{{display:none;background:#fff;border:1px solid #888;
  border-radius:0 6px 6px 6px;padding:16px}}
.tab-pane.active{{display:block}}
.group-stats{{font-size:.85rem;color:#555;margin-bottom:10px}}
.sheet-grid{{display:flex;flex-direction:column;gap:24px}}
.sheet-card h3{{font-size:.9rem;font-weight:600;margin-bottom:6px;color:#333}}
.dim{{font-weight:400;color:#777;font-size:.8rem}}
.warn{{color:#b55;font-size:.85rem;margin-bottom:8px}}
.legend{{margin-top:20px;padding-top:12px;border-top:1px solid #ddd}}
.legend h2{{font-size:.85rem;font-weight:600;color:#555;margin-bottom:6px}}
.legend-item{{display:inline-flex;align-items:center;gap:5px;
  margin:3px 8px 3px 0;font-size:.78rem;color:#333}}
.legend-swatch{{width:14px;height:14px;border-radius:2px;
  border:1px solid rgba(0,0,0,.15);flex-shrink:0}}
.bom-tbl{{width:100%;border-collapse:collapse;font-size:.82rem}}
.bom-tbl th{{background:#2c3e50;color:#fff;padding:6px 8px;text-align:left;font-weight:600}}
.bom-tbl td{{padding:5px 8px;border-bottom:1px solid #e0e0e0}}
.bom-tbl tr:nth-child(even) td{{background:#f7f7f7}}
.bom-tbl tr:hover td{{background:#eef4fb}}
</style>
</head>
<body>
<h1>{_esc(cabinet_name)} — Cut Sheet Layout</h1>
<div class="tabs">{tabs_html}</div>
{panes_html}
<div class="legend">
<h2>Panel legend</h2>
{legend_items}
</div>
<script>
function showTab(n){{
  document.querySelectorAll('.tab-btn').forEach((b,i)=>b.classList.toggle('active',i===n));
  document.querySelectorAll('.tab-pane').forEach((p,i)=>p.classList.toggle('active',i===n));
}}
</script>
</body>
</html>"""


def generate_sheet_layout_pdf(
    groups: list[tuple[str, list["CutlistPanel"], "OptimizationResult"]],
    cabinet_name: str = "Cabinet",
    kerf: float = 3.2,
    hardware_lines: "list[HardwareLine] | None" = None,
) -> bytes:
    """Generate a PDF cutlist document with sheet layouts and parts list.

    Parameters
    ----------
    groups:
        List of ``(label, panels, opt_result)`` tuples — one per thickness
        group.  Same format as :func:`generate_sheet_layout_html`.
    cabinet_name:
        Used in the document title.
    kerf:
        Saw kerf in mm (shown in the header).

    Returns
    -------
    bytes
        Raw PDF bytes ready to write to a file.

    Raises
    ------
    ImportError
        If ``reportlab`` is not installed.
    """
    if not _REPORTLAB_AVAILABLE:
        raise ImportError(
            "reportlab is required for PDF export. "
            "Install with: uv pip install reportlab"
        )

    from datetime import date as _date

    PAGE = _rl_landscape(A4)
    MARGIN = 15 * _rl_mm
    CW = PAGE[0] - 2 * MARGIN   # usable content width

    styles = _getSampleStyleSheet()

    title_sty = _ParagraphStyle("ct", parent=styles["Title"],
                                fontSize=18, leading=22, spaceAfter=3 * _rl_mm)
    h1_sty    = _ParagraphStyle("ch1", parent=styles["Heading1"],
                                fontSize=12, leading=15, spaceBefore=4 * _rl_mm, spaceAfter=2 * _rl_mm)
    h2_sty    = _ParagraphStyle("ch2", parent=styles["Heading2"],
                                fontSize=9, leading=12, spaceBefore=2 * _rl_mm, spaceAfter=1.5 * _rl_mm)
    norm_sty  = _ParagraphStyle("cn", parent=styles["Normal"],
                                fontSize=8.5, leading=11)
    small_sty = _ParagraphStyle("cs", parent=styles["Normal"],
                                fontSize=7.5, leading=10)

    def _tbl_style(small: bool = False, align_right_from: int = 1) -> _TableStyle:
        fs = 7.5 if small else 9
        return _TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  _HexColor("#2c3e50")),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  _HexColor("#ffffff")),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), fs),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_HexColor("#f5f5f5"), _HexColor("#ffffff")]),
            ("GRID",          (0, 0), (-1, -1), 0.5, _HexColor("#cccccc")),
            ("ALIGN",         (0, 0), (0,  -1), "LEFT"),
            ("ALIGN",         (align_right_from, 0), (-1, -1), "CENTER"),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ])

    buf = io.BytesIO()
    doc = _SimpleDocTemplate(
        buf,
        pagesize=PAGE,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title=f"Cutlist — {cabinet_name}",
    )

    story = []

    # ── Page 1: summary ───────────────────────────────────────────────────────
    story.append(_Paragraph(f"Cutlist — {cabinet_name}", title_sty))
    story.append(_Paragraph(
        f"Generated {_date.today().isoformat()} · Kerf: {kerf} mm", norm_sty
    ))
    story.append(_Spacer(1, 5 * _rl_mm))

    # Sheet goods table
    story.append(_Paragraph("Sheet Goods Required", h1_sty))
    sg_data = [["Material", "Thickness", "Sheets", "Waste", "Unplaced"]]
    for label, _pnls, result in groups:
        mat = result.stock_sheet.material.replace("_", " ").title()
        sg_data.append([
            f"{label}  ({mat})",
            f"{result.stock_sheet.thickness:.0f} mm",
            str(result.sheets_used),
            f"{result.waste_pct:.1f}%",
            str(len(result.unplaced)) if result.unplaced else "—",
        ])
    sg_col_w = [CW * x for x in (0.42, 0.16, 0.14, 0.14, 0.14)]
    sg_tbl = _Table(sg_data, colWidths=sg_col_w)
    sg_tbl.setStyle(_tbl_style())
    story.append(sg_tbl)
    story.append(_Spacer(1, 5 * _rl_mm))

    # Cut parts table
    story.append(_Paragraph("Cut Parts List", h1_sty))
    all_panels: list[CutlistPanel] = []
    for _, pnls, _ in groups:
        all_panels.extend(pnls)
    all_panels.sort(key=lambda p: (p.thickness, p.material, p.name))

    parts_data = [["Part Name", "L (mm)", "W (mm)", "T (mm)", "Qty", "Material", "Edge Band", "Notes"]]
    for p in all_panels:
        parts_data.append([
            p.name,
            f"{p.length:.0f}",
            f"{p.width:.0f}",
            f"{p.thickness:.0f}",
            str(p.quantity),
            p.material.replace("_", " ").title(),
            ", ".join(p.edge_band) if p.edge_band else "—",
            p.notes or "—",
        ])
    parts_col_w = [CW * x for x in (0.22, 0.08, 0.08, 0.07, 0.05, 0.16, 0.12, 0.22)]
    parts_tbl = _Table(parts_data, colWidths=parts_col_w, repeatRows=1)
    parts_tbl.setStyle(_tbl_style(small=True))
    story.append(parts_tbl)

    # ── Sheet layout pages ────────────────────────────────────────────────────
    HEADER_RESERVE = 28 * _rl_mm    # space for title + subtitle above drawing
    CUT_TABLE_RESERVE = 50 * _rl_mm # space below drawing for cut-sequence table (~8 rows)
    DRAW_H = PAGE[1] - 2 * MARGIN - HEADER_RESERVE - CUT_TABLE_RESERVE

    for group_label, _pnls, result in groups:
        by_sheet: dict[int, list[Placement]] = {}
        for pl in result.placements:
            by_sheet.setdefault(pl.sheet_index, []).append(pl)

        for sheet_idx in sorted(by_sheet):
            story.append(_PageBreak())
            pls = by_sheet[sheet_idx]

            story.append(_Paragraph(
                f"{group_label} — Sheet {sheet_idx + 1} of {result.sheets_used}", h1_sty
            ))
            warn = ""
            if result.grain_mismatched:
                warn = f" · ⚠ {len(result.grain_mismatched)} grain mismatch(es)"
            story.append(_Paragraph(
                f"{result.stock_sheet.length:.0f} × {result.stock_sheet.width:.0f} mm "
                f"· Waste: {result.waste_pct:.1f}%{warn}",
                norm_sty,
            ))
            story.append(_Spacer(1, 2 * _rl_mm))

            story.append(_SheetDrawingFlowable(pls, result.stock_sheet, kerf, CW, DRAW_H))

            # Cut-sequence table
            raw_cuts: list = []
            _guillotine_cuts(pls, 0, 0, result.stock_sheet.length, result.stock_sheet.width,
                             depth=0, out=raw_cuts)
            raw_cuts.sort(key=lambda e: e[0])
            seq = 0
            cut_data = [["#", "Type", "Set fence to (shorter piece)"]]
            for entry in raw_cuts:
                if entry[7]:   # is_breakdown
                    seq += 1
                    orient = entry[2]
                    dim_a, dim_b = entry[8], entry[9]
                    cut_data.append([
                        str(seq),
                        "Rip" if orient == "h" else "Cross-cut",
                        f"{min(dim_a, dim_b):.0f} mm",
                    ])
            if len(cut_data) > 1:
                cut_col_w = [CW * x for x in (0.06, 0.20, 0.74)]
                cut_tbl = _Table(cut_data, colWidths=cut_col_w)
                cut_tbl.setStyle(_tbl_style(small=True))
                story.append(_KeepTogether([
                    _Spacer(1, 3 * _rl_mm),
                    _Paragraph("Cut Sequence", h2_sty),
                    cut_tbl,
                ]))

    # ── Hardware BOM page (optional) ──────────────────────────────────────────
    if hardware_lines:
        story.append(_PageBreak())
        story.append(_Paragraph("Hardware BOM", h1_sty))
        story.append(_Paragraph(
            "Quantities include procurement math based on pack size.", norm_sty
        ))
        story.append(_Spacer(1, 3 * _rl_mm))

        cat_order = {"pull": 0, "slide": 1, "hinge": 2, "leg": 3}
        sorted_hw = sorted(hardware_lines, key=lambda h: (cat_order.get(h.category, 9), h.name))

        hw_data = [["Category", "Name", "Brand", "Model #",
                    "Needed", "Pack Qty", "Packs to Order", "Leftover", "Notes"]]
        for h in sorted_hw:
            hw_data.append([
                h.category.title(),
                h.name,
                h.brand,
                h.model_number,
                str(h.pieces_needed),
                str(h.pack_quantity),
                str(h.packs_to_order),
                str(h.leftover) if h.leftover else "—",
                h.notes or "—",
            ])
        hw_col_w = [CW * x for x in (0.09, 0.22, 0.12, 0.13, 0.07, 0.08, 0.12, 0.08, 0.09)]
        hw_tbl = _Table(hw_data, colWidths=hw_col_w, repeatRows=1)
        hw_tbl.setStyle(_tbl_style(small=True))
        story.append(hw_tbl)

    doc.build(story)
    return buf.getvalue()


class _SheetDrawingFlowable(_Flowable):
    """Platypus Flowable that renders a single sheet layout using the canvas."""

    def __init__(
        self,
        placements: list["Placement"],
        stock: "SheetStock",
        kerf: float,
        avail_w: float,
        avail_h: float,
    ) -> None:
        super().__init__()
        self._pl = placements
        self._stock = stock
        self._kerf = kerf
        self.width = avail_w
        self.height = avail_h

    def draw(self) -> None:
        canvas = self.canv
        sl, sw = self._stock.length, self._stock.width

        scale = min(self.width / sl, self.height / sw)
        drawn_w = sl * scale
        drawn_h = sw * scale
        x_off = (self.width - drawn_w) / 2
        y_off = (self.height - drawn_h) / 2

        def sx(x_mm: float) -> float:
            return x_off + x_mm * scale

        def sy(y_mm: float, h_mm: float = 0.0) -> float:
            # SVG y-down → RL y-up
            return y_off + (sw - y_mm - h_mm) * scale

        # Sheet background
        canvas.setFillColor(_HexColor("#F5EED8"))
        canvas.setStrokeColor(_HexColor("#888888"))
        canvas.setLineWidth(0.5)
        canvas.rect(sx(0), sy(0, sw), drawn_w, drawn_h, fill=1, stroke=1)

        # Panels
        for p in self._pl:
            fc = _panel_colour(p.panel_name)
            sc = _panel_colour_dark(fc)
            canvas.setFillColor(_HexColor(fc))
            canvas.setStrokeColor(_HexColor(sc))
            canvas.setLineWidth(0.4)

            px_pt = sx(p.x)
            py_pt = sy(p.y, p.placed_width)
            pw_pt = p.placed_length * scale
            ph_pt = p.placed_width * scale
            corner_pt = max(1.0, min(pw_pt, ph_pt) * 0.03)
            canvas.roundRect(px_pt, py_pt, pw_pt, ph_pt, corner_pt, fill=1, stroke=1)

            label = p.panel_name[:20] + ("…" if len(p.panel_name) > 20 else "")
            if p.rotated:
                label += " ↺"
            dim_text = f"{p.placed_length:.0f}×{p.placed_width:.0f}mm"

            min_dim_pt = min(pw_pt, ph_pt)
            font_pt = max(5.0, min(min_dim_pt * 0.12, 9.0))
            dim_pt  = max(4.0, min(min_dim_pt * 0.09, 7.0))

            cx_pt = px_pt + pw_pt / 2
            cy_pt = py_pt + ph_pt / 2
            tall  = p.placed_width > p.placed_length

            canvas.saveState()
            canvas.translate(cx_pt, cy_pt)
            if tall:
                canvas.rotate(90)
            canvas.setFillColor(_HexColor(sc))
            canvas.setFont("Helvetica", font_pt)
            canvas.drawCentredString(0, font_pt * 0.25, label)
            canvas.setFont("Helvetica", dim_pt)
            canvas.drawCentredString(0, -dim_pt * 1.6, dim_text)
            canvas.restoreState()

        # Guillotine cut lines
        raw_cuts: list = []
        _guillotine_cuts(self._pl, 0, 0, sl, sw, depth=0, out=raw_cuts)
        raw_cuts.sort(key=lambda e: e[0])

        label_r_pt = max(4.0, sl * 0.016 * scale)
        seq = 0

        for entry in raw_cuts:
            depth, pos, orient, x0, y0, x1, y1, is_breakdown, dim_a, dim_b = entry

            if is_breakdown:
                seq += 1
                lc = _HexColor("#c0392b")
                lw = max(0.6, sl * 0.004 * scale)
                dash = max(3.0, sl * 0.015 * scale)
            else:
                lc = _HexColor("#aaaaaa")
                lw = 0.3
                dash = max(2.0, sl * 0.010 * scale)

            canvas.setStrokeColor(lc)
            canvas.setLineWidth(lw)
            canvas.setDash(dash, dash * 0.6)
            canvas.line(sx(x0), sy(y0), sx(x1), sy(y1))
            canvas.setDash()

            if is_breakdown:
                if orient == "h":
                    bx = (sx(x0) + sx(x1)) / 2
                    by = sy(y0)
                else:
                    bx = sx(x0)
                    by = (sy(y0) + sy(y1)) / 2

                canvas.setFillColor(lc)
                canvas.circle(bx, by, label_r_pt, fill=1, stroke=0)
                canvas.setFillColor(_HexColor("#ffffff"))
                canvas.setFont("Helvetica-Bold", max(4.0, label_r_pt * 1.1))
                canvas.drawCentredString(bx, by - label_r_pt * 0.38, str(seq))

                # Dimension label on the shorter side of the cut
                short_dim = min(dim_a, dim_b)
                dim_label = f"{short_dim:.0f}mm"
                dim_font_pt = max(4.0, label_r_pt * 0.85)
                pad_pt = label_r_pt * 1.8

                canvas.setFillColor(lc)
                canvas.setFont("Helvetica", dim_font_pt)
                if orient == "h":
                    tx = bx + label_r_pt * 1.5
                    ty = by + (pad_pt if dim_a > dim_b else -pad_pt)
                    canvas.drawString(tx, ty, dim_label)
                else:
                    tx = bx
                    ty = by + pad_pt
                    canvas.saveState()
                    canvas.translate(tx, ty)
                    canvas.rotate(90)
                    canvas.drawCentredString(0, 0, dim_label)
                    canvas.restoreState()

        # Bottom ruler
        canvas.setStrokeColor(_HexColor("#888888"))
        canvas.setLineWidth(0.4)
        ruler_y = sy(0, sw) - 1.0
        tick_font = max(4.0, min(sl * 0.014 * scale, 6.0))
        for tick_mm in range(0, int(sl) + 1, 200):
            tx = sx(tick_mm)
            canvas.line(tx, ruler_y, tx, ruler_y - 3.0)
            if tick_mm % 400 == 0:
                canvas.setFillColor(_HexColor("#666666"))
                canvas.setFont("Helvetica", tick_font)
                canvas.drawCentredString(tx, ruler_y - 3.0 - tick_font, str(tick_mm))


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
