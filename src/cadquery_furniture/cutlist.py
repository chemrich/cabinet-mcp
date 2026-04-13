"""
BOM extraction and cutlist optimizer interface.

Extracts a bill of materials from cabinet assemblies and formats it for
cutlist optimization. Supports output to:
- JSON (for cut-optimizer-2d Rust crate or MCP server)
- CSV (for manual reference)
- Console table

All dimensions in millimeters.
"""

import csv
import json
import io
from dataclasses import dataclass, field, asdict
from typing import Optional

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
    """Export cutlist as JSON, compatible with cut-optimizer-2d input format.

    The output JSON structure:
    {
        "cut_width": kerf,
        "panels": [...],
        "stock": [...]
    }
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
