"""
MCP server for the cabinet-design toolkit.

Exposes the parametric design, evaluation, and cutlist workflows as MCP tools
so that Claude, Gemini CLI, or any MCP-compatible client can design cabinets
conversationally.

Transports
----------
stdio (default)
    The host process (Claude Desktop, Gemini CLI, …) launches ``cabinet-mcp``
    as a subprocess and communicates over stdin/stdout.  No port is used; no
    port conflicts are possible.  This is the right choice for Claude Desktop
    and Gemini CLI.

HTTP/SSE  (``--http``)
    Runs an HTTP server (Starlette + uvicorn) with a Server-Sent Events
    endpoint at ``GET /sse`` and a POST endpoint at ``/messages/``.  Use this
    when you need a persistent process that multiple clients can reach, or when
    the host does not support stdio transport.

    Port selection
    ~~~~~~~~~~~~~~
    Default starting port is **3749** (distinctive enough to avoid accidental
    collisions with common dev servers).  If that port is already bound, the
    server tries 3750, 3751, … up to ``--max-port-attempts`` tries.  The
    resolved port is:
    - printed to **stderr** on startup
    - written to ``/tmp/cabinet-mcp.port`` so scripts / other tools can
      discover it without parsing log output
    - removed from ``/tmp/cabinet-mcp.port`` on clean exit

Entry point: ``cabinet-mcp`` (defined in pyproject.toml [project.scripts]).

Usage::

    # stdio (default) — Claude Desktop / Gemini CLI
    cabinet-mcp

    # HTTP/SSE on default port (3749, auto-increments on collision)
    cabinet-mcp --http

    # HTTP/SSE on a specific starting port
    cabinet-mcp --http --port 4000

    # Via uv without installing
    uv run cabinet-mcp --http --port 4000
"""

from __future__ import annotations

import json
import math
import socket
import sys
import textwrap
from pathlib import Path
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from .cabinet import CabinetConfig, ColumnConfig, build_multi_bay_cabinet as _build_multi_bay_cabinet
from .auto_fix import auto_fix_cabinet as _auto_fix, AutoFixResult, fixable_checks
from .proportions import (
    graduated_drawer_heights as _grad_heights,
    column_widths as _col_widths,
    RATIO_PRESETS as _RATIO_PRESETS,
    _PRESET_DESCRIPTIONS,
    _mm_to_inches_str,
)
from .describe import describe_design as _describe_design
from .presets import PRESETS, get_preset, list_presets as _list_presets
from .furniture_refs import identify_furniture, get_furniture, SYNONYM_TO_PRESETS
from .visualize import build_and_visualize as _build_and_visualize, visualize_assembly as _visualize_assembly
from .cutlist import (
    CutlistPanel,
    SheetStock,
    consolidate_bom,
    generate_sheet_layout_html,
    generate_sheet_layout_pdf,
    hardware_bom_for_cabinet_config,
    to_hardware_json,
    optimize_cutlist,
    to_csv,
    to_json,
    _OPCUT_AVAILABLE,
    _RECTPACK_AVAILABLE,
)
from .cabinet import OpeningConfig
from .door import DoorConfig
from .drawer import DrawerConfig
from .evaluation import Issue, Severity, evaluate_cabinet
from .hardware import HINGES, SLIDES, LEGS, PULLS, OverlayType, LegPattern, get_leg, get_pull, price_for
from .joinery import (
    CarcassJoinery,
    DrawerJoineryStyle,
    DEFAULT_DOMINO,
    DEFAULT_POCKET_SCREW,
    DEFAULT_BISCUIT,
    DEFAULT_DOWEL,
    DOMINO_SIZES,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ok(data: Any) -> list[types.TextContent]:
    """Return a JSON success response."""
    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


def _err(msg: str) -> list[types.TextContent]:
    """Return a plain-text error response."""
    return [types.TextContent(type="text", text=f"ERROR: {msg}")]


def _issues_to_dicts(issues: list[Issue]) -> list[dict]:
    return [
        {
            "severity": i.severity.value,
            "check": i.check,
            "message": i.message,
            "part_a": i.part_a,
            "part_b": i.part_b,
            "value": i.value,
            "limit": i.limit,
        }
        for i in issues
    ]


def _to_opening(raw) -> OpeningConfig:
    """Normalize a raw [height, type] list/tuple, dict, or OpeningConfig → OpeningConfig."""
    if isinstance(raw, OpeningConfig):
        return raw
    if isinstance(raw, dict):
        return OpeningConfig(
            height_mm=float(raw["height_mm"]),
            opening_type=str(raw.get("opening_type", raw.get("slot_type", "open"))),
            hinge_key=raw.get("hinge_key"),
            hinge_side=raw.get("hinge_side"),
            pull_key=raw.get("pull_key"),
            num_doors=raw.get("num_doors"),
            door_thickness=raw.get("door_thickness"),
        )
    return OpeningConfig(height_mm=float(raw[0]), opening_type=str(raw[1]))


def _sort_drawer_config(dc: list) -> list:
    """Sort drawer openings largest-first (bottom); non-drawer openings stay at the end."""
    if not dc:
        return dc

    def _type(row):
        return row.opening_type if isinstance(row, OpeningConfig) else str(row[1])

    def _height(row):
        return row.height_mm if isinstance(row, OpeningConfig) else float(row[0])

    types_set = {_type(r) for r in dc}
    if len(types_set) == 1:
        return sorted(dc, key=_height, reverse=True)
    drawers = sorted([r for r in dc if _type(r) == "drawer"], key=_height, reverse=True)
    others  = [r for r in dc if _type(r) != "drawer"]
    return drawers + others


def _build_cabinet_config(args: dict) -> CabinetConfig:
    """Build a CabinetConfig from a flat dict of keyword arguments.

    Accepts ``drawer_config`` (backward-compat API name) as an alias for
    ``openings``. Each entry may be a ``[height_mm, opening_type]`` list,
    a dict, or an ``OpeningConfig`` object — all are normalised by
    ``_to_opening``.
    """
    preset_key = args.pop("pull_preset", None)
    if preset_key:
        from .hardware import get_pull_preset
        preset = get_pull_preset(preset_key)
        args.setdefault("drawer_pull", preset.drawer_pull)
        args.setdefault("door_pull", preset.door_pull)
        args.setdefault("door_pull_inset_mm", preset.door_pull_inset_mm)

    # Accept drawer_config as a backward-compat alias for openings.
    if "drawer_config" in args and "openings" not in args:
        args["openings"] = args.pop("drawer_config")
    else:
        args.pop("drawer_config", None)

    kwargs: dict[str, Any] = {}
    for key, value in args.items():
        if key == "carcass_joinery" and isinstance(value, str):
            kwargs[key] = CarcassJoinery(value)
        elif key == "openings" and isinstance(value, list):
            kwargs[key] = [_to_opening(r) for r in value]
        elif key == "columns" and isinstance(value, list):
            kwargs[key] = [
                ColumnConfig(
                    width_mm=float(c["width_mm"]),
                    openings=tuple(
                        _to_opening(r) for r in c.get("drawer_config", c.get("openings", []))
                    ),
                )
                for c in value
            ]
        else:
            kwargs[key] = value
    return CabinetConfig(**kwargs)


def _build_door_config(args: dict) -> DoorConfig:
    return DoorConfig(**args)


def _build_drawer_config(args: dict) -> DrawerConfig:
    kwargs: dict[str, Any] = {}
    for key, value in args.items():
        if key == "joinery_style" and isinstance(value, str):
            kwargs[key] = DrawerJoineryStyle(value)
        else:
            kwargs[key] = value
    return DrawerConfig(**kwargs)


def _raw_box_height(cfg: DrawerConfig) -> float:
    """Compute the clearance-adjusted height without standard snapping."""
    return cfg.opening_height - cfg.slide.min_bottom_clearance - cfg.vertical_gap


def _pull_placements_to_dicts(placements) -> list[dict]:
    """Convert PullPlacement objects to JSON-friendly dicts."""
    return [
        {
            "pull_key":     pl.pull_key,
            "center_xz_mm": [pl.center[0], pl.center[1]],
            "hole_coords_xz_mm": [list(hc) for hc in pl.hole_coords],
        }
        for pl in placements
    ]


def _hardware_line_to_dict(line) -> dict:
    """Convert a HardwareLine to a JSON-friendly dict including derived fields."""
    return {
        "sku":            line.sku,
        "category":       line.category,
        "name":           line.name,
        "brand":          line.brand,
        "model_number":   line.model_number,
        "pieces_needed":  line.pieces_needed,
        "pack_quantity":  line.pack_quantity,
        "packs_to_order": line.packs_to_order,
        "pieces_ordered": line.pieces_ordered,
        "leftover":       line.leftover,
        "notes":          line.notes,
    }


# ─── Server ───────────────────────────────────────────────────────────────────

server = Server("cabinet-mcp")


# ──────────────────────────────────────────────────────────────────────────────
# Tool: list_hardware
# ──────────────────────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_hardware",
            description=(
                "Return the catalogue of available drawer slides, hinges, legs, and pulls. "
                "Use this to discover valid key strings for other tools."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["slides", "hinges", "legs", "pulls", "all"],
                        "description": "Which hardware category to list.",
                        "default": "all",
                    },
                    "brand": {
                        "type": "string",
                        "description": (
                            "Optional case-insensitive brand filter for pulls "
                            "(e.g. 'IKEA', 'Top Knobs'). Ignored for other categories."
                        ),
                    },
                    "mount_style": {
                        "type": "string",
                        "enum": ["surface", "edge", "flush", "knob"],
                        "description": (
                            "Optional mount-style filter for pulls. "
                            "Ignored for other categories."
                        ),
                    },
                },
            },
        ),
        types.Tool(
            name="list_joinery_options",
            description=(
                "Return available joinery styles for drawer boxes and carcass construction, "
                "including Festool Domino tenon sizes."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="design_cabinet",
            description=textwrap.dedent("""\
                Define or update a cabinet configuration and return a summary of its
                parametric layout — panel sizes, opening stack, hardware, joinery — without
                running CadQuery geometry.

                Required: width, height, depth (all in mm).

                drawer_config is a list of [height_mm, slot_type] pairs stacked from
                bottom to top. slot_type options: "drawer", "door", "door_pair",
                "shelf", "open".

                carcass_joinery options: "dado_rabbet", "floating_tenon",
                "pocket_screw", "biscuit", "dowel".

                ── WORKFLOW ──
                After calling this tool you MUST immediately call evaluate_cabinet
                on the returned config before doing anything else. If errors are
                found, call auto_fix_cabinet, then re-evaluate.  Once all errors
                are resolved, call describe_design and present the prose summary
                to the user.  Do NOT call visualize_cabinet until the user has
                reviewed the description and explicitly approved.
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "width":  {"type": "number", "description": "Exterior width in mm."},
                    "height": {"type": "number", "description": "Exterior height in mm."},
                    "depth":  {"type": "number", "description": "Exterior depth in mm."},
                    "side_thickness":   {"type": "number", "default": 18.0},
                    "bottom_thickness": {"type": "number", "default": 18.0},
                    "top_thickness":    {"type": "number", "default": 18.0},
                    "shelf_thickness":  {"type": "number", "default": 18.0},
                    "back_thickness":   {"type": "number", "default": 6.0},
                    "drawer_config": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "prefixItems": [
                                {"type": "number", "description": "Opening height in mm"},
                                {"type": "string", "description": "Slot type"},
                            ],
                            "minItems": 2,
                            "maxItems": 2,
                        },
                        "description": "Stack of [height_mm, slot_type] pairs from bottom up.",
                        "default": [],
                    },
                    "carcass_joinery": {
                        "type": "string",
                        "enum": ["dado_rabbet", "floating_tenon", "pocket_screw", "biscuit", "dowel"],
                        "default": "floating_tenon",
                    },
                    "adj_shelf_holes": {"type": "boolean", "default": False},
                    "door_hinge": {
                        "type": "string",
                        "description": "Hinge key from list_hardware. Default: blum_clip_top_110_full.",
                        "default": "blum_clip_top_110_full",
                    },
                    "num_drawers": {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "Number of drawer openings. When provided without an explicit "
                            "drawer_config, heights are auto-computed from drawer_proportion."
                        ),
                    },
                    "drawer_proportion": {
                        "type": "string",
                        "enum": ["equal", "subtle", "classic", "golden"],
                        "description": (
                            "Height-graduation preset for auto-computed drawer stacks. "
                            "equal=uniform, subtle=1.2×, classic=1.4×, golden=1.618× (φ). "
                            "Default: classic."
                        ),
                    },
                    "drawer_pull": {
                        "type": "string",
                        "description": "Pull catalog key from list_hardware (category='pulls').",
                    },
                    "door_pull": {
                        "type": "string",
                        "description": "Pull catalog key applied to every door / door_pair slot.",
                    },
                    "pull_preset": {
                        "type": "string",
                        "description": "Named pull preset key (see list_pull_presets). Populates drawer_pull, door_pull, and orientation. Explicit drawer_pull/door_pull fields override the preset.",
                    },
                },
                "required": ["width", "height", "depth"],
            },
        ),
        types.Tool(
            name="design_multi_column_cabinet",
            description=textwrap.dedent("""\
                Design a cabinet with multiple side-by-side vertical columns sharing
                a common carcass — e.g. a left column of drawers next to a right
                column with a door, all within one set of exterior panels.

                Columns are separated by interior vertical dividers (same thickness as
                ``side_thickness``).  Column widths are interior measurements and must
                sum to the cabinet's interior_width (= width − 2 × side_thickness).

                Each column has its own ``drawer_config`` stack (same format as
                design_cabinet: list of [height_mm, slot_type] pairs).

                ── PROPORTION SHORTCUTS ──
                Instead of spelling out every column width and drawer height, you can
                let the tool compute proportional layouts automatically:

                  • column_proportion + num_columns [+ wide_index]: auto-computes
                    column widths using a named graduation preset.  wide_index marks
                    the accent column (0-based); omit for equal widths.

                  • drawer_proportion + num_drawers: auto-computes drawer heights
                    within each column using a geometric graduation preset.

                Presets: "equal" (uniform), "subtle" (1.2×), "classic" (1.4×),
                "golden" (1.618× / φ).

                Returns the same summary as design_cabinet plus:
                  - columns: per-column breakdown (interior width, slot stack, divider x)
                  - column_widths_sum_mm / interior_width_mm: for quick sanity check
                  - proportions_used: which presets were applied (if any)

                ── WORKFLOW ──
                After calling this tool you MUST call evaluate_cabinet on the returned
                config (using width/height/depth plus the columns array) before
                presenting results.  The evaluator will flag any column-width errors.
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "width":  {"type": "number", "description": "Exterior width in mm."},
                    "height": {"type": "number", "description": "Exterior height in mm."},
                    "depth":  {"type": "number", "description": "Exterior depth in mm."},
                    "columns": {
                        "type": "array",
                        "description": (
                            "List of column definitions, left to right. "
                            "Interior widths must sum to (width - 2 × side_thickness)."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "width_mm": {
                                    "type": "number",
                                    "description": "Interior width of this column in mm.",
                                },
                                "drawer_config": {
                                    "type": "array",
                                    "description": "Stack of [height_mm, slot_type] pairs bottom-to-top.",
                                    "items": {
                                        "type": "array",
                                        "prefixItems": [
                                            {"type": "number"},
                                            {"type": "string"},
                                        ],
                                        "minItems": 2,
                                        "maxItems": 2,
                                    },
                                    "default": [],
                                },
                            },
                            "required": ["width_mm"],
                        },
                        "minItems": 2,
                    },
                    "side_thickness":   {"type": "number", "default": 18.0},
                    "bottom_thickness": {"type": "number", "default": 18.0},
                    "top_thickness":    {"type": "number", "default": 18.0},
                    "shelf_thickness":  {"type": "number", "default": 18.0},
                    "back_thickness":   {"type": "number", "default": 6.0},
                    "carcass_joinery": {
                        "type": "string",
                        "enum": ["dado_rabbet", "floating_tenon", "pocket_screw", "biscuit", "dowel"],
                        "default": "floating_tenon",
                    },
                    "drawer_slide": {
                        "type": "string",
                        "default": "blum_tandem_550h",
                    },
                    "door_hinge": {
                        "type": "string",
                        "default": "blum_clip_top_110_full",
                    },
                    "num_columns": {
                        "type": "integer",
                        "minimum": 2,
                        "description": (
                            "Number of columns. Use with column_proportion / wide_index "
                            "as an alternative to supplying an explicit columns array."
                        ),
                    },
                    "wide_index": {
                        "type": "integer",
                        "description": "0-based index of the wider accent column (used with column_proportion).",
                    },
                    "column_proportion": {
                        "type": "string",
                        "enum": ["equal", "subtle", "classic", "golden"],
                        "description": (
                            "Width-graduation preset for auto-computed column widths. "
                            "Requires num_columns. Default: golden."
                        ),
                    },
                    "num_drawers": {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "Drawers per column when drawer_config is omitted from each column entry."
                        ),
                    },
                    "drawer_proportion": {
                        "type": "string",
                        "enum": ["equal", "subtle", "classic", "golden"],
                        "description": (
                            "Height-graduation preset for auto-computed drawer heights. "
                            "Default: classic."
                        ),
                    },
                    "drawer_pull": {
                        "type": "string",
                        "description": "Pull catalog key from list_hardware (category='pulls').",
                    },
                    "door_pull": {
                        "type": "string",
                        "description": "Pull catalog key applied to every door / door_pair slot.",
                    },
                    "pull_preset": {
                        "type": "string",
                        "description": "Named pull preset key (see list_pull_presets). Populates drawer_pull, door_pull, and orientation. Explicit drawer_pull/door_pull fields override the preset.",
                    },
                },
                "required": ["width", "height", "depth"],
            },
        ),
        types.Tool(
            name="evaluate_cabinet",
            description=textwrap.dedent("""\
                Run the full structural/fit evaluation on a cabinet configuration and return
                a list of issues (errors, warnings, info). Pass the same arguments as
                design_cabinet. Optionally include door_configs (list of DoorConfig dicts)
                to also evaluate door hardware.

                ── WORKFLOW ──
                This tool MUST be called after every call to design_cabinet or
                apply_preset.  If the result contains any severity=error issues,
                call auto_fix_cabinet once with the same config, then re-evaluate.
                If errors persist after auto-fix, describe the remaining errors to
                the user and ask for guidance.  Only proceed to describe_design
                (and eventually visualize_cabinet) when there are zero errors.
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "width":  {"type": "number"},
                    "height": {"type": "number"},
                    "depth":  {"type": "number"},
                    "side_thickness":   {"type": "number", "default": 18.0},
                    "bottom_thickness": {"type": "number", "default": 18.0},
                    "top_thickness":    {"type": "number", "default": 18.0},
                    "shelf_thickness":  {"type": "number", "default": 18.0},
                    "back_thickness":   {"type": "number", "default": 6.0},
                    "drawer_config": {
                        "type": "array",
                        "items": {"type": "array", "minItems": 2, "maxItems": 2},
                        "default": [],
                    },
                    "carcass_joinery": {
                        "type": "string",
                        "enum": ["dado_rabbet", "floating_tenon", "pocket_screw", "biscuit", "dowel"],
                        "default": "floating_tenon",
                    },
                    "door_hinge": {"type": "string", "default": "blum_clip_top_110_full"},
                    "door_configs": {
                        "type": "array",
                        "description": "Optional list of DoorConfig parameter dicts to evaluate.",
                        "items": {"type": "object"},
                        "default": [],
                    },
                },
                "required": ["width", "height", "depth"],
            },
        ),
        types.Tool(
            name="design_door",
            description=textwrap.dedent("""\
                Calculate door dimensions, hinge count, and hinge positions for a cabinet
                opening. Returns the DoorConfig summary.

                overlay_type is determined automatically from the hinge_key you choose.
                Use list_hardware to see valid hinge keys.

                Optional pull hardware: pass pull_key (from list_hardware with
                category="pulls") to get placements, the hardware BOM line, and
                fit checks in the response.  pull_vertical controls where the
                pull sits on the door face ("center", "upper_third", or
                "lower_third") — upper_third for base-cabinet doors, lower_third
                for wall cabinets.
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "opening_width":  {"type": "number", "description": "Cabinet opening width in mm."},
                    "opening_height": {"type": "number", "description": "Cabinet opening height in mm."},
                    "num_doors": {
                        "type": "integer",
                        "enum": [1, 2],
                        "description": "1 = single door, 2 = door pair.",
                        "default": 1,
                    },
                    "hinge_key": {
                        "type": "string",
                        "description": "Hinge key from list_hardware.",
                        "default": "blum_clip_top_110_full",
                    },
                    "door_thickness": {"type": "number", "default": 18.0},
                    "door_weight_kg": {"type": "number", "default": 0.0},
                    "gap_top":    {"type": "number", "default": 2.0},
                    "gap_bottom": {"type": "number", "default": 2.0},
                    "gap_side":   {"type": "number", "default": 2.0},
                    "gap_between": {"type": "number", "default": 2.0},
                    "pull_key": {
                        "type": "string",
                        "description": (
                            "Pull catalog key from list_hardware (category='pulls'). "
                            "Omit for no pull."
                        ),
                    },
                    "pull_count": {
                        "type": "integer",
                        "minimum": 0,
                        "description": (
                            "Override auto-selected pull count per door leaf. "
                            "0 = auto (single ≤ 600 mm, dual > 600 mm)."
                        ),
                    },
                    "pull_vertical": {
                        "type": "string",
                        "enum": ["center", "upper_third", "lower_third"],
                        "description": "Vertical placement policy on the door face.",
                        "default": "center",
                    },
                },
                "required": ["opening_width", "opening_height"],
            },
        ),
        types.Tool(
            name="design_drawer",
            description=textwrap.dedent("""\
                Calculate drawer box dimensions and joinery geometry for a given opening.
                Returns DrawerConfig summary including side/front-back dimensions and
                joinery cut specs.

                joinery_style options: "butt", "qqq", "half_lap", "drawer_lock".
                slide_key: use list_hardware to see options (default: blum_tandem_550h).

                By default, box_height_mm is snapped down to the nearest standard
                industry size (3"–12" in 1" steps) so boxes can be batch-ordered.
                Set use_standard_height=false to use the full clearance-adjusted height.
                The response always includes both standard_box_height_mm and the raw
                computed height for reference.

                Optional pull hardware: pass pull_key (from list_hardware with
                category="pulls") to get placements, the hardware BOM line, and
                fit checks in the response.  Omit pull_count (or set to 0) to let
                the tool auto-select single vs dual pulls at the 600 mm face
                threshold.
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "opening_width":  {"type": "number", "description": "Cabinet opening width in mm."},
                    "opening_height": {"type": "number", "description": "Available height for drawer in mm."},
                    "opening_depth":  {"type": "number", "description": "Cabinet interior depth in mm."},
                    "slide_key": {
                        "type": "string",
                        "description": "Drawer slide key from list_hardware.",
                        "default": "blum_tandem_550h",
                    },
                    "joinery_style": {
                        "type": "string",
                        "enum": ["butt", "qqq", "half_lap", "drawer_lock"],
                        "default": "half_lap",
                    },
                    "side_thickness":       {"type": "number", "default": 15.0},
                    "front_back_thickness": {"type": "number", "default": 15.0},
                    "bottom_thickness":     {"type": "number", "default": 6.0},
                    "face_thickness":       {"type": "number", "default": 18.0},
                    "use_standard_height": {
                        "type": "boolean",
                        "description": (
                            "Snap box height to the nearest standard industry size "
                            "(3\"–12\" in 1\" steps). Default true."
                        ),
                        "default": True,
                    },
                    "pull_key": {
                        "type": "string",
                        "description": (
                            "Pull catalog key from list_hardware (category='pulls'). "
                            "Omit for no pull."
                        ),
                    },
                    "pull_count": {
                        "type": "integer",
                        "minimum": 0,
                        "description": (
                            "Override auto-selected pull count. 0 = auto: single "
                            "pull if the drawer face is ≤ 600 mm wide, otherwise "
                            "two pulls placed at quarter-points."
                        ),
                    },
                    "pull_vertical": {
                        "type": "string",
                        "enum": ["center", "upper_third", "lower_third"],
                        "description": "Vertical placement policy on the drawer face.",
                        "default": "center",
                    },
                },
                "required": ["opening_width", "opening_height", "opening_depth"],
            },
        ),
        types.Tool(
            name="generate_cutlist",
            description=textwrap.dedent("""\
                Generate a complete bill of materials and cutlist from a cabinet
                configuration. Supports single-column and multi-column layouts.

                Pass the same cabinet parameters as design_cabinet, plus an
                optional ``columns`` array (same format as design_multi_column_cabinet)
                to include column dividers, drawer box parts, and applied false fronts.

                Returns:
                  - sheet_goods: uncut sheet quantities grouped by material/thickness
                  - panels_summary: flat panel list with dimensions and quantities
                  - cutlist_json / cutlist_csv: full BOM for external tools
                  - files: paths to written CSV and JSON files on disk
                  - optimization: sheets-used and waste% per thickness group (rectpack)

                Drawer box parts use 5/8\" (15 mm) sides/front/back and 1/4\" (6 mm)
                bottoms captured in a dado. Applied false fronts are listed separately
                as finished_wood (species to be specified by the user).
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "width":  {"type": "number"},
                    "height": {"type": "number"},
                    "depth":  {"type": "number"},
                    "name": {
                        "type": "string",
                        "description": "Base filename stem for output files. Default: 'cabinet'.",
                        "default": "cabinet",
                    },
                    "side_thickness":   {"type": "number", "default": 18.0},
                    "bottom_thickness": {"type": "number", "default": 18.0},
                    "shelf_thickness":  {"type": "number", "default": 18.0},
                    "back_thickness":   {"type": "number", "default": 6.0},
                    "drawer_config": {
                        "type": "array",
                        "items": {"type": "array", "minItems": 2, "maxItems": 2},
                        "default": [],
                    },
                    "columns": {
                        "description": "Multi-column layout from design_multi_column_cabinet. When provided, drawer_config is ignored.",
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "width_mm": {"type": "number"},
                                "drawer_config": {
                                    "type": "array",
                                    "items": {"type": "array", "minItems": 2, "maxItems": 2},
                                    "default": [],
                                },
                            },
                            "required": ["width_mm"],
                        },
                    },
                    "sheet_length": {
                        "type": "number",
                        "description": "Sheet stock length in mm (default 2440 / 4×8).",
                        "default": 2440,
                    },
                    "sheet_width": {
                        "type": "number",
                        "description": "Sheet stock width in mm (default 1220 / 4×8).",
                        "default": 1220,
                    },
                    "kerf": {
                        "type": "number",
                        "description": "Saw-blade kerf in mm added to each panel for layout. Default 3.2 mm.",
                        "default": 3.2,
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "csv", "both"],
                        "description": "Output format.",
                        "default": "both",
                    },
                    "optimizer": {
                        "type": "string",
                        "enum": ["auto", "opcut", "rectpack", "strip"],
                        "description": (
                            "Sheet layout algorithm. 'auto' (default) uses opcut if installed, "
                            "then rectpack if installed, then strip-cutting. 'rectpack' requires "
                            "the rectpack package (uv pip install -e '.[cutlist]')."
                        ),
                        "default": "auto",
                    },
                },
                "required": ["width", "height", "depth"],
            },
        ),
        types.Tool(
            name="compare_joinery",
            description=textwrap.dedent("""\
                Compare drawer joinery styles side-by-side for a given stock thickness.
                Returns cut dimensions and characteristics for butt, qqq, half_lap,
                and drawer_lock joints.
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "side_thickness": {
                        "type": "number",
                        "description": "Drawer side thickness in mm.",
                        "default": 12.0,
                    },
                    "front_back_thickness": {
                        "type": "number",
                        "description": "Drawer front/back thickness in mm.",
                        "default": 12.0,
                    },
                },
            },
        ),
        types.Tool(
            name="visualize_cabinet",
            description=textwrap.dedent("""\
                Build a full 3D cabinet assembly, export it as a GLB file, and
                generate a self-contained HTML viewer that opens in the browser.

                Requires CadQuery (pip install cadquery).  The HTML embeds the
                GLB as base64, so no server is needed — just open the file.

                Pass the same cabinet parameters as design_cabinet.
                Returns paths to the GLB and HTML files plus file size info.

                Viewer shortcuts: X = x-ray drawer fronts, O = open drawers.

                ── WORKFLOW ──
                NEVER call this tool directly after design_cabinet or
                apply_preset.  You MUST first:
                  1. evaluate_cabinet → ensure zero errors (auto_fix_cabinet if
                     needed)
                  2. describe_design → present the prose summary to the user
                  3. Wait for the user to explicitly approve or request changes
                Only call visualize_cabinet after the user has approved the
                evaluated, described design.
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "width":  {"type": "number", "description": "Exterior width in mm."},
                    "height": {"type": "number", "description": "Exterior height in mm."},
                    "depth":  {"type": "number", "description": "Exterior depth in mm."},
                    "side_thickness":   {"type": "number", "default": 18.0},
                    "bottom_thickness": {"type": "number", "default": 18.0},
                    "shelf_thickness":  {"type": "number", "default": 18.0},
                    "back_thickness":   {"type": "number", "default": 6.0},
                    "drawer_config": {
                        "type": "array",
                        "items": {"type": "array", "minItems": 2, "maxItems": 2},
                        "default": [],
                    },
                    "fixed_shelf_positions": {
                        "type": "array",
                        "items": {"type": "number"},
                        "default": [],
                    },
                    "adj_shelf_holes": {"type": "boolean", "default": False},
                    "num_bays": {
                        "type": "integer",
                        "description": "Number of identical side-by-side bays to render (default 1).",
                        "default": 1,
                    },
                    "columns": {
                        "type": "array",
                        "description": "Multi-column layout from design_multi_column_cabinet. Each entry has width_mm and drawer_config.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "width_mm": {"type": "number"},
                                "drawer_config": {
                                    "type": "array",
                                    "items": {"type": "array", "minItems": 2, "maxItems": 2},
                                },
                            },
                            "required": ["width_mm"],
                        },
                    },
                    "name": {
                        "type": "string",
                        "description": "Base filename stem for output files.",
                        "default": "cabinet",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Directory for output files. Default: ~/.cabinet-mcp/visualizations",
                        "default": "~/.cabinet-mcp/visualizations",
                    },
                    "open_browser": {
                        "type": "boolean",
                        "description": "Open the HTML viewer in the default browser.",
                        "default": True,
                    },
                    "tolerance": {
                        "type": "number",
                        "description": "Mesh tessellation tolerance in mm. Lower = finer mesh, bigger file. Default: 0.1",
                        "default": 0.1,
                    },
                    "drawer_pull": {
                        "type": "string",
                        "description": "Pull catalog key from list_hardware (category='pulls'). Omit for no pull hardware in render.",
                    },
                    "pull_preset": {
                        "type": "string",
                        "description": "Named pull preset key (see list_pull_presets). Populates drawer_pull, door_pull, and orientation. Explicit drawer_pull/door_pull fields override the preset.",
                    },
                    "furniture_top": {
                        "type": "boolean",
                        "description": (
                            "When true, renders a 'furniture top' style: a front cap strip "
                            "extends the top panel flush to the drawer-face plane, and the "
                            "bottom of the lowest drawer face drops to the carcass underside."
                        ),
                        "default": False,
                    },
                    "divider_full_height": {
                        "type": "boolean",
                        "description": (
                            "Controls the center divider in mixed drawer+door columns "
                            "(e.g. armoire). Default false: divider is clipped to the "
                            "drawer zone — the upper door/open section stays open with "
                            "no divider. Set true to extend the divider the full cabinet "
                            "height, separating the upper bay into independent compartments."
                        ),
                        "default": False,
                    },
                },
                "required": ["width", "height", "depth"],
            },
        ),
        types.Tool(
            name="list_presets",
            description=textwrap.dedent("""\
                Return the catalogue of named cabinet presets — validated starting
                configurations for common cabinet types (kitchen base, dresser,
                tool chest, bathroom vanity, wall cabinet, pantry, credenza,
                sideboard, console table, media console, etc.).

                Use this to discover preset names, then call apply_preset to load
                one as a full design_cabinet-compatible config dict.

                Optionally filter by category ("kitchen", "workshop", "bedroom",
                "bathroom", "storage", "living_room") or by tag (e.g. "drawer",
                "soft_close", "heavy_duty", "console", "credenza").
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["kitchen", "workshop", "bedroom", "bathroom", "storage",
                                 "living_room", "entryway", "office"],
                        "description": "Filter by cabinet category.",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Filter by tag (e.g. 'drawer', 'soft_close', 'wide').",
                    },
                },
            },
        ),
        types.Tool(
            name="apply_preset",
            description=textwrap.dedent("""\
                Load a named preset and return its full configuration dict, ready
                to pass directly to evaluate_cabinet.

                Optionally supply an overrides dict to tweak individual fields
                (e.g. change width, swap the drawer_slide, adjust depth) without
                rebuilding from scratch.

                Returns:
                  - preset_name, display_name, description, category
                  - config: the merged CabinetConfig fields as a flat dict
                  - interior_height_mm: computed from the merged config
                  - opening_stack_total_mm: sum of drawer_config heights
                  - opening_stack_matches_interior: whether they are equal
                    (mismatches indicate the overrides changed height but not
                    the opening stack — you should update drawer_config too)

                Use list_presets to discover valid preset names.

                ── WORKFLOW ──
                After calling this tool you MUST immediately call
                evaluate_cabinet on the returned config.  If errors are found,
                call auto_fix_cabinet, then re-evaluate.  Once clean, call
                describe_design and present the summary to the user.  Do NOT
                call visualize_cabinet until the user has approved.
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Preset slug from list_presets (e.g. 'kitchen_base_3_drawer').",
                    },
                    "overrides": {
                        "type": "object",
                        "description": (
                            "Optional dict of CabinetConfig fields to override after loading "
                            "the preset (e.g. {\"width\": 750, \"drawer_slide\": \"blum_movento_760h\"})."
                        ),
                        "default": {},
                    },
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="identify_furniture_type",
            description=textwrap.dedent("""\
                Look up a furniture piece by common name or synonym and return
                its canonical type, category, typical dimensions, related names,
                and any matching preset slugs.

                Accepts plain English names including historical, regional, and
                foreign-language terms: "chifforobe", "semainier", "tallboy",
                "credenza", "tansu", "armadio", "chevet", etc.

                Use this tool when the user names a furniture type you want to
                confirm, or to discover which preset best matches what they want.
                Returns up to 5 candidates when the name is ambiguous.
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Furniture piece name or synonym to look up.",
                    },
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="auto_fix_cabinet",
            description=textwrap.dedent("""\
                Attempt a single round of deterministic fixes on a cabinet
                configuration.  Evaluates the config, applies known-safe
                corrections (e.g. rebalancing an opening stack that overshoots
                interior_height, aligning a back-panel rabbet with the back
                thickness), then re-evaluates.

                Returns:
                  - config: the (possibly modified) config dict
                  - changes: human-readable list of what was adjusted
                  - initial_issues / final_issues: before and after
                  - fixed: whether at least one error was resolved
                  - clean: whether zero errors remain

                ── WORKFLOW ──
                Call this ONLY after evaluate_cabinet has returned one or more
                severity=error issues.  After auto-fix completes, call
                evaluate_cabinet again to confirm the result is clean.  If
                errors remain, describe them to the user and ask for guidance.
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "width":  {"type": "number"},
                    "height": {"type": "number"},
                    "depth":  {"type": "number"},
                    "side_thickness":   {"type": "number", "default": 18.0},
                    "bottom_thickness": {"type": "number", "default": 18.0},
                    "top_thickness":    {"type": "number", "default": 18.0},
                    "shelf_thickness":  {"type": "number", "default": 18.0},
                    "back_thickness":   {"type": "number", "default": 6.0},
                    "drawer_config": {
                        "type": "array",
                        "items": {"type": "array", "minItems": 2, "maxItems": 2},
                        "default": [],
                    },
                    "carcass_joinery": {
                        "type": "string",
                        "enum": ["dado_rabbet", "floating_tenon", "pocket_screw", "biscuit", "dowel"],
                        "default": "floating_tenon",
                    },
                    "door_hinge": {"type": "string", "default": "blum_clip_top_110_full"},
                    "adj_shelf_holes": {"type": "boolean", "default": False},
                    "drawer_slide": {"type": "string", "default": "blum_tandem_550h"},
                },
                "required": ["width", "height", "depth"],
            },
        ),
        types.Tool(
            name="describe_design",
            description=textwrap.dedent("""\
                Generate a human-readable prose description of a cabinet
                configuration — dimensions in both metric and imperial, opening
                layout, hardware names, joinery methods, and materials — suitable
                for presenting to the user during design review.

                Returns:
                  - prose: a short paragraph summarising the design
                  - dimensions, openings, hardware, materials: structured dicts
                  - materials.carcass_joinery: the carcass joinery method
                  - materials.drawer_box_joinery: the drawer-box corner joint

                ── WORKFLOW ──
                Call this after evaluate_cabinet returns zero errors (or after
                auto_fix_cabinet has cleaned them).  Present the prose to the
                user, then EXPLICITLY ask them to confirm or change the two
                joinery choices — carcass joinery (materials.carcass_joinery)
                and drawer-box joinery (materials.drawer_box_joinery) — before
                calling visualize_cabinet.  Do not proceed to visualization
                until the user has acknowledged the joinery methods.
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "width":  {"type": "number"},
                    "height": {"type": "number"},
                    "depth":  {"type": "number"},
                    "side_thickness":   {"type": "number", "default": 18.0},
                    "bottom_thickness": {"type": "number", "default": 18.0},
                    "top_thickness":    {"type": "number", "default": 18.0},
                    "shelf_thickness":  {"type": "number", "default": 18.0},
                    "back_thickness":   {"type": "number", "default": 6.0},
                    "drawer_config": {
                        "type": "array",
                        "items": {"type": "array", "minItems": 2, "maxItems": 2},
                        "default": [],
                    },
                    "carcass_joinery": {
                        "type": "string",
                        "enum": ["dado_rabbet", "floating_tenon", "pocket_screw", "biscuit", "dowel"],
                        "default": "floating_tenon",
                    },
                    "door_hinge": {"type": "string", "default": "blum_clip_top_110_full"},
                    "adj_shelf_holes": {"type": "boolean", "default": False},
                    "drawer_slide": {"type": "string", "default": "blum_tandem_550h"},
                },
                "required": ["width", "height", "depth"],
            },
        ),
        types.Tool(
            name="design_legs",
            description=textwrap.dedent("""\
                Configure the legs / feet for a cabinet and return placement
                coordinates, hardware specs, and load-per-leg.

                Default: 4 corner feet using Richelieu 176138106 (100 mm brushed
                nickel contemporary square leg, 50 kg per leg).

                NOTE: the Richelieu 176138106 is 100 mm (3-15/16\"), not a true
                4\" leg.  If you need exactly 4\" / 102 mm, choose a different SKU
                or use an adjustable leg.

                leg_pattern options:
                  "corners"              — one foot at each corner (default, 4 legs)
                  "corners_and_midspan"  — corners + one centred on each long side
                  "along_front_back"     — count/2 evenly spaced across front and back

                Use list_hardware (with category="legs") to see available leg keys.

                Returns:
                  - leg: hardware spec (name, height_mm, load_capacity_kg, part_number)
                  - count: total number of legs
                  - placement_mm: list of {x, y} positions (origin = front-left corner)
                  - inset_mm: how far each foot is set in from the cabinet edge
                  - load_per_leg_kg: cabinet_weight_kg / count (if weight provided)
                  - total_height_mm: leg height (pass to cabinet design as base clearance)
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "cabinet_width":  {"type": "number", "description": "Cabinet exterior width in mm."},
                    "cabinet_depth":  {"type": "number", "description": "Cabinet exterior depth in mm."},
                    "leg_key": {
                        "type": "string",
                        "description": (
                            "Leg key from list_hardware (category=legs). "
                            "Default: richelieu_176138106."
                        ),
                        "default": "richelieu_176138106",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of legs. Default: 4.",
                        "default": 4,
                    },
                    "leg_pattern": {
                        "type": "string",
                        "enum": ["corners", "corners_and_midspan", "along_front_back"],
                        "description": "Foot placement pattern. Default: corners.",
                        "default": "corners",
                    },
                    "inset_mm": {
                        "type": "number",
                        "description": "How far each foot centre is set in from the cabinet edge. Default: 30 mm.",
                        "default": 30.0,
                    },
                    "cabinet_weight_kg": {
                        "type": "number",
                        "description": "Estimated cabinet + contents weight for load-per-leg calc. Default: 0 (skipped).",
                        "default": 0.0,
                    },
                },
                "required": ["cabinet_width", "cabinet_depth"],
            },
        ),
        types.Tool(
            name="design_pulls",
            description=textwrap.dedent("""\
                Compute pull-hardware placements, fit checks, and consolidated
                procurement BOM for an entire cabinet in one call.

                Pass the cabinet footprint (width/height/depth) plus a
                drawer_config (or columns array, for multi-column cabinets)
                matching the shape used by design_cabinet / design_multi_column_cabinet,
                together with drawer_pull and/or door_pull keys from
                list_hardware (category="pulls").

                For each drawer / door / door_pair slot the tool returns:
                  - slot index, slot type, face dimensions
                  - list of placements (centre + hole coordinates, face-local mm)
                  - per-slot issues (e.g. pull_fit, pull_projection)

                Plus:
                  - cabinet_issues: style-consistency check across drawer/door pulls
                  - hardware_bom: consolidated HardwareLine per SKU, including
                    pack-quantity math (packs_to_order / pieces_ordered / leftover)

                Omit both drawer_pull and door_pull to get an empty BOM and no
                slot placements (useful for confirming the tool accepts a layout).

                ── WORKFLOW ──
                Call this AFTER design_cabinet / design_multi_column_cabinet and
                AFTER evaluate_cabinet returns clean; the pull-consistency warning
                is reported here as well so the user sees it alongside the BOM.
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "width":  {"type": "number", "description": "Exterior width in mm."},
                    "height": {"type": "number", "description": "Exterior height in mm."},
                    "depth":  {"type": "number", "description": "Exterior depth in mm."},
                    "side_thickness":   {"type": "number", "default": 18.0},
                    "bottom_thickness": {"type": "number", "default": 18.0},
                    "top_thickness":    {"type": "number", "default": 18.0},
                    "back_thickness":   {"type": "number", "default": 6.0},
                    "drawer_config": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "prefixItems": [
                                {"type": "number"},
                                {"type": "string"},
                            ],
                            "minItems": 2,
                            "maxItems": 2,
                        },
                        "description": "Flat stack of [height_mm, slot_type] pairs bottom-to-top.",
                        "default": [],
                    },
                    "columns": {
                        "type": "array",
                        "description": (
                            "Multi-column layout; mirrors design_multi_column_cabinet. "
                            "If provided, drawer_config is ignored."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "width_mm": {"type": "number"},
                                "drawer_config": {
                                    "type": "array",
                                    "items": {
                                        "type": "array",
                                        "prefixItems": [
                                            {"type": "number"},
                                            {"type": "string"},
                                        ],
                                        "minItems": 2,
                                        "maxItems": 2,
                                    },
                                    "default": [],
                                },
                            },
                            "required": ["width_mm"],
                        },
                    },
                    "drawer_slide": {"type": "string", "default": "blum_tandem_550h"},
                    "door_hinge":   {"type": "string", "default": "blum_clip_top_110_full"},
                    "drawer_pull": {
                        "type": "string",
                        "description": "Pull catalog key applied to every drawer slot.",
                    },
                    "door_pull": {
                        "type": "string",
                        "description": "Pull catalog key applied to every door / door_pair slot.",
                    },
                    "drawer_pull_vertical": {
                        "type": "string",
                        "enum": ["center", "upper_third", "lower_third"],
                        "default": "center",
                    },
                    "door_pull_vertical": {
                        "type": "string",
                        "enum": ["center", "upper_third", "lower_third"],
                        "default": "center",
                    },
                    "pull_preset": {
                        "type": "string",
                        "description": "Named pull preset key (see list_pull_presets). Populates drawer_pull, door_pull, and orientation. Explicit drawer_pull/door_pull fields override the preset.",
                    },
                },
                "required": ["width", "height", "depth"],
            },
        ),
        types.Tool(
            name="suggest_proportions",
            description=textwrap.dedent("""\
                Compare all four proportion presets (equal / subtle / classic / golden)
                side-by-side for a given cabinet's interior dimensions.

                For drawers: returns per-preset heights (mm + fractional inches) and a
                viability flag — if a preset would produce a top drawer below the 75 mm
                minimum it is marked not viable with a reason rather than raising an error.

                For columns: returns per-preset column widths (mm). Column widths are
                always viable for standard cabinet dimensions.

                Omit num_drawers to skip drawer suggestions; omit num_columns to skip
                column suggestions. At least one must be provided.

                Use this before committing to a proportion preset in design_cabinet or
                design_multi_column_cabinet.
            """),
            inputSchema={
                "type": "object",
                "properties": {
                    "width":  {"type": "number", "description": "Exterior width in mm."},
                    "height": {"type": "number", "description": "Exterior height in mm."},
                    "depth":  {"type": "number", "description": "Exterior depth in mm (accepted but not used in proportion math)."},
                    "side_thickness":   {"type": "number", "default": 18},
                    "bottom_thickness": {"type": "number", "default": 18},
                    "top_thickness":    {"type": "number", "default": 18},
                    "num_drawers": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Number of drawer openings to compare across all presets.",
                    },
                    "num_columns": {
                        "type": "integer",
                        "minimum": 2,
                        "description": "Number of columns to compare across all presets.",
                    },
                    "wide_index": {
                        "type": "integer",
                        "description": "0-based index of the accent (wide) column (used with num_columns).",
                    },
                },
                "required": ["width", "height", "depth"],
            },
        ),
        types.Tool(
            name="list_pull_presets",
            description=textwrap.dedent("""\
                List available pull presets. Each preset bundles a drawer pull,
                door pull, and orientation/inset settings under a single key.

                Pass the preset key to design_cabinet, design_multi_column_cabinet,
                or visualize_cabinet as ``pull_preset`` to apply all settings at once.
                Individual ``drawer_pull`` / ``door_pull`` fields still override the
                preset when supplied alongside it.
            """),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Tool handlers
# ──────────────────────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "list_hardware":
            return await _tool_list_hardware(arguments)
        elif name == "list_joinery_options":
            return await _tool_list_joinery(arguments)
        elif name == "design_cabinet":
            return await _tool_design_cabinet(arguments)
        elif name == "design_multi_column_cabinet":
            return await _tool_design_multi_column_cabinet(arguments)
        elif name == "evaluate_cabinet":
            return await _tool_evaluate_cabinet(arguments)
        elif name == "design_door":
            return await _tool_design_door(arguments)
        elif name == "design_drawer":
            return await _tool_design_drawer(arguments)
        elif name == "generate_cutlist":
            return await _tool_generate_cutlist(arguments)
        elif name == "compare_joinery":
            return await _tool_compare_joinery(arguments)
        elif name == "visualize_cabinet":
            return await _tool_visualize_cabinet(arguments)
        elif name == "list_presets":
            return await _tool_list_presets(arguments)
        elif name == "apply_preset":
            return await _tool_apply_preset(arguments)
        elif name == "identify_furniture_type":
            return await _tool_identify_furniture_type(arguments)
        elif name == "auto_fix_cabinet":
            return await _tool_auto_fix_cabinet(arguments)
        elif name == "describe_design":
            return await _tool_describe_design(arguments)
        elif name == "design_legs":
            return await _tool_design_legs(arguments)
        elif name == "design_pulls":
            return await _tool_design_pulls(arguments)
        elif name == "suggest_proportions":
            return await _tool_suggest_proportions(arguments)
        elif name == "list_pull_presets":
            return await _tool_list_pull_presets(arguments)
        else:
            return _err(f"Unknown tool: {name}")
    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}")


# ── list_pull_presets ─────────────────────────────────────────────────────────


async def _tool_list_pull_presets(args: dict) -> list[types.TextContent]:
    from .hardware import PULL_PRESETS
    presets = [
        {
            "key": p.key,
            "style_name": p.style_name,
            "description": p.description,
            "drawer_pull": p.drawer_pull,
            "door_pull": p.door_pull,
            "door_pull_inset_mm": p.door_pull_inset_mm,
        }
        for p in PULL_PRESETS.values()
    ]
    return _ok({"presets": presets, "count": len(presets)})


# ── list_hardware ─────────────────────────────────────────────────────────────

async def _tool_list_hardware(args: dict) -> list[types.TextContent]:
    category = args.get("category", "all")
    result: dict[str, Any] = {}

    if category in ("slides", "all"):
        result["slides"] = {
            key: {
                "name": s.name,
                "slide_type": s.slide_type.value,
                "available_lengths_mm": list(s.available_lengths),
                "nominal_side_clearance_mm": s.nominal_side_clearance,
                "min_bottom_clearance_mm": s.min_bottom_clearance,
                "max_load_kg": s.max_load_kg,
                "min_drawer_height_mm": s.min_drawer_height,
            }
            for key, s in SLIDES.items()
        }

    if category in ("hinges", "all"):
        result["hinges"] = {
            key: {
                "name": h.name,
                "overlay_type": h.overlay_type.value,
                "overlay_mm": h.overlay,
                "cup_diameter_mm": h.cup_diameter,
                "cup_boring_distance_mm": h.cup_boring_distance,
                "opening_angle_deg": h.opening_angle,
                "soft_close": h.soft_close,
                "max_door_weight_kg": h.max_door_weight_kg,
                "part_number": h.part_number,
            }
            for key, h in HINGES.items()
        }

    if category in ("legs", "all"):
        result["legs"] = {
            key: {
                "name": l.name,
                "height_mm": l.height_mm,
                "base_diameter_mm": l.base_diameter_mm,
                "is_adjustable": l.is_adjustable,
                "adjustment_range_mm": l.adjustment_range_mm,
                "load_capacity_kg": l.load_capacity_kg,
                "finish": l.finish,
                "part_number": l.part_number,
                "notes": l.notes,
            }
            for key, l in LEGS.items()
        }

    if category in ("pulls", "all"):
        brand_filter = (args.get("brand") or "").strip().lower()
        mount_filter = (args.get("mount_style") or "").strip().lower()
        pulls_out: dict[str, dict[str, Any]] = {}
        for key, p in PULLS.items():
            if brand_filter and brand_filter not in p.brand.lower():
                continue
            if mount_filter and p.mount_style.value != mount_filter:
                continue
            pulls_out[key] = {
                "name":           p.name,
                "brand":          p.brand,
                "model_number":   p.model_number,
                "url":            p.url,
                "style":          p.style,
                "material":       p.material,
                "finish":         p.finish,
                "mount_style":    p.mount_style.value,
                "pack_quantity":  p.pack_quantity,
                "cc_mm":          p.cc_mm,
                "length_mm":      p.length_mm,
                "projection_mm":  p.projection_mm,
                "is_knob":        p.is_knob,
                "tags":           list(p.tags),
            }
        result["pulls"] = pulls_out
        # Provide a handy count so clients don't have to walk the dict.
        result["pulls_count"] = len(pulls_out)

    return _ok(result)


# ── list_joinery_options ──────────────────────────────────────────────────────

async def _tool_list_joinery(args: dict) -> list[types.TextContent]:
    from .joinery import DrawerJoinerySpec

    drawer_styles = {
        "butt":        "Simple butt joint — glue and fasteners only, no interlocking cuts.",
        "qqq":         "Quarter-Quarter-Quarter locking rabbet (Stephen Phipps). "
                       "All cuts = material_thickness ÷ 2. Stronger than dovetail, table-saw only.",
        "half_lap":    "Half-lap: side dado depth = side_thickness ÷ 2; "
                       "front/back channel matches.",
        "drawer_lock": "Drawer-lock (router bit required). Two-step interlock — "
                       "side dado + inner step for positive mechanical lock.",
    }

    carcass_methods = {
        "dado_rabbet":     "Dadoes for shelves/bottom, rabbet for back. No additional hardware.",
        "floating_tenon":  "Festool Domino oval mortise/tenon. DF 500 (≤8 mm) or DF 700 (10/14 mm).",
        "pocket_screw":    "Kreg-style 15° angled pocket. Fast, tool-accessible, no mortise needed.",
        "biscuit":         "Plate-joinery biscuits (#0, #10, #20). Alignment aid + glue surface.",
        "dowel":           "Round dowels — compatible with 32 mm European shelf-pin grid.",
    }

    domino_sizes = {
        key: {
            "tenon_length_mm":          d.tenon_length,
            "tenon_thickness_mm":       d.tenon_thickness,
            "mortise_length_mm":        d.mortise_length,
            "mortise_width_mm":         d.mortise_width,
            "mortise_depth_per_side_mm": d.mortise_depth_per_side,
            "machine": d.machine,
        }
        for key, d in DOMINO_SIZES.items()
    }

    return _ok({
        "drawer_joinery_styles": drawer_styles,
        "carcass_joinery_methods": carcass_methods,
        "domino_sizes": domino_sizes,
    })


# ── design_cabinet ────────────────────────────────────────────────────────────

async def _tool_design_cabinet(args: dict) -> list[types.TextContent]:
    num_drawers       = args.pop("num_drawers", None)
    drawer_proportion = args.pop("drawer_proportion", None)
    args.pop("furniture_top", None)
    proportions_used: dict = {}

    if num_drawers and not args.get("drawer_config"):
        preset = drawer_proportion or "classic"
        side_t   = float(args.get("side_thickness",   18))
        bottom_t = float(args.get("bottom_thickness", 18))
        top_t    = float(args.get("top_thickness",    18))
        interior_h = float(args["height"]) - bottom_t - top_t
        heights = _grad_heights(interior_h, int(num_drawers), preset)
        args["drawer_config"] = [[h, "drawer"] for h in heights]
        proportions_used["drawer_proportion"] = preset

    if args.get("drawer_config"):
        args["drawer_config"] = _sort_drawer_config(args["drawer_config"])

    cfg = _build_cabinet_config(args)

    # Interior dimensions
    interior_width  = cfg.width  - 2 * cfg.side_thickness
    interior_height = cfg.interior_height
    interior_depth  = cfg.depth  - cfg.back_thickness

    # Panel sizes (parametric only, no CQ needed)
    panels = {
        "side_panel": {
            "qty": 2,
            "width_mm":  cfg.depth,
            "height_mm": cfg.height,
            "thickness_mm": cfg.side_thickness,
        },
        "bottom_panel": {
            "qty": 1,
            "width_mm":  interior_width,
            "depth_mm":  cfg.depth - cfg.back_thickness,
            "thickness_mm": cfg.bottom_thickness,
        },
        "top_panel": {
            "qty": 1,
            "width_mm":  interior_width,
            "depth_mm":  cfg.depth - cfg.back_thickness,
            "thickness_mm": cfg.top_thickness,
        },
        "back_panel": {
            "qty": 1,
            "width_mm":  interior_width,
            "height_mm": cfg.height,
            "thickness_mm": cfg.back_thickness,
        },
    }

    for i, pos in enumerate(cfg.fixed_shelf_positions):
        panels[f"fixed_shelf_{i+1}"] = {
            "qty": 1,
            "width_mm":  interior_width,
            "depth_mm":  interior_depth,
            "thickness_mm": cfg.shelf_thickness,
            "height_from_bottom_mm": pos,
        }

    opening_stack = [
        {"height_mm": op.height_mm, "type": op.opening_type} for op in cfg.openings
    ]

    result = {
        "exterior": {"width_mm": cfg.width, "height_mm": cfg.height, "depth_mm": cfg.depth},
        "interior": {
            "width_mm":  interior_width,
            "height_mm": interior_height,
            "depth_mm":  interior_depth,
        },
        "joinery":  cfg.carcass_joinery.value,
        "panels":   panels,
        "opening_stack": opening_stack,
        "adj_shelf_holes": cfg.adj_shelf_holes,
        "door_hinge": cfg.door_hinge,
        "drawer_pull": cfg.drawer_pull,
        "door_pull": cfg.door_pull,
    }
    if proportions_used:
        result["proportions_used"] = proportions_used
    return _ok(result)


# ── design_multi_column_cabinet ───────────────────────────────────────────────

async def _tool_design_multi_column_cabinet(args: dict) -> list[types.TextContent]:
    """Handler for the design_multi_column_cabinet tool."""
    num_columns       = args.pop("num_columns",       None)
    wide_index        = args.pop("wide_index",         None)
    column_proportion = args.pop("column_proportion",  None)
    num_drawers       = args.pop("num_drawers",        None)
    drawer_proportion = args.pop("drawer_proportion",  None)
    args.pop("furniture_top", None)
    proportions_used: dict = {}

    # ── Resolve column widths ──────────────────────────────────────────────────
    if not args.get("columns"):
        if not num_columns:
            return _err("Provide either 'columns' or 'num_columns'.")
        side_t     = float(args.get("side_thickness", 18))
        n_cols     = int(num_columns)
        interior_w = float(args["width"]) - 2 * side_t
        available_w = interior_w - (n_cols - 1) * side_t  # subtract internal divider space
        col_preset = column_proportion or ("golden" if wide_index is not None else "equal")
        widths = _col_widths(available_w, n_cols, wide_index, col_preset)
        proportions_used["column_proportion"] = col_preset
        if wide_index is not None:
            proportions_used["wide_index"] = wide_index
        # Build placeholder column dicts (drawer_config filled below)
        args["columns"] = [{"width_mm": w} for w in widths]

    # ── Resolve drawer heights ─────────────────────────────────────────────────
    if num_drawers:
        bottom_t   = float(args.get("bottom_thickness", 18))
        top_t      = float(args.get("top_thickness",    18))
        interior_h = float(args["height"]) - bottom_t - top_t
        drw_preset = drawer_proportion or "classic"
        heights    = _grad_heights(interior_h, int(num_drawers), drw_preset)
        proportions_used["drawer_proportion"] = drw_preset
        # Fill in any column that has no explicit drawer_config
        for col in args["columns"]:
            if not col.get("drawer_config"):
                col["drawer_config"] = [[h, "drawer"] for h in heights]

    for col in args.get("columns", []):
        if col.get("drawer_config"):
            col["drawer_config"] = _sort_drawer_config(col["drawer_config"])

    cfg = _build_cabinet_config(args)

    interior_width  = cfg.interior_width
    interior_height = cfg.interior_height
    interior_depth  = cfg.depth - cfg.back_thickness

    # Build per-column breakdown
    col_x = 0.0  # running interior x from left column
    col_details = []
    for i, col in enumerate(cfg.columns):
        stack = [{"height_mm": op.height_mm, "type": op.opening_type} for op in col.openings]
        stack_total = sum(op.height_mm for op in col.openings)
        col_details.append({
            "index":             i,
            "interior_width_mm": col.width_mm,
            "divider_left_x_mm": col_x - cfg.side_thickness if i > 0 else 0.0,
            "stack_total_mm":    stack_total,
            "stack_fills_interior": abs(stack_total - interior_height) < 0.5,
            "opening_stack":     stack,
        })
        col_x += col.width_mm + cfg.side_thickness  # account for divider between columns

    col_sum = sum(c.width_mm for c in cfg.columns)
    n_dividers = max(len(cfg.columns) - 1, 0)

    panels = {
        "side_panel":    {"qty": 2, "height_mm": cfg.height, "depth_mm": cfg.depth, "thickness_mm": cfg.side_thickness},
        "bottom_panel":  {"qty": 1, "width_mm": interior_width, "depth_mm": interior_depth, "thickness_mm": cfg.bottom_thickness},
        "top_panel":     {"qty": 1, "width_mm": interior_width, "depth_mm": interior_depth, "thickness_mm": cfg.top_thickness},
        "back_panel":    {"qty": 1, "width_mm": interior_width, "height_mm": cfg.height,    "thickness_mm": cfg.back_thickness},
        "column_divider": {"qty": n_dividers, "height_mm": cfg.height, "depth_mm": cfg.depth - cfg.back_rabbet_width, "thickness_mm": cfg.side_thickness},
    }

    result = {
        "exterior":   {"width_mm": cfg.width, "height_mm": cfg.height, "depth_mm": cfg.depth},
        "interior":   {"width_mm": interior_width, "height_mm": interior_height, "depth_mm": interior_depth},
        "joinery":    cfg.carcass_joinery.value,
        "panels":     panels,
        "column_count":          len(cfg.columns),
        "column_widths_sum_mm":  col_sum,
        "interior_width_mm":     interior_width,
        "columns_fill_interior": abs(col_sum - (interior_width - n_dividers * cfg.side_thickness)) < 0.5,
        "columns":               col_details,
        "adj_shelf_holes":       cfg.adj_shelf_holes,
        "door_hinge":            cfg.door_hinge,
    }
    if proportions_used:
        result["proportions_used"] = proportions_used
    return _ok(result)


# ── evaluate_cabinet ──────────────────────────────────────────────────────────

async def _tool_evaluate_cabinet(args: dict) -> list[types.TextContent]:
    door_config_dicts = args.pop("door_configs", []) or []
    args.pop("furniture_top", None)
    cfg = _build_cabinet_config(args)

    door_configs = [_build_door_config(d) for d in door_config_dicts]

    issues = evaluate_cabinet(
        cab_cfg=cfg,
        door_configs=door_configs if door_configs else None,
    )

    errors   = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]
    infos    = [i for i in issues if i.severity == Severity.INFO]

    return _ok({
        "summary": {
            "errors":   len(errors),
            "warnings": len(warnings),
            "info":     len(infos),
            "pass":     len(errors) == 0,
        },
        "issues": _issues_to_dicts(issues),
    })


# ── design_door ───────────────────────────────────────────────────────────────

async def _tool_design_door(args: dict) -> list[types.TextContent]:
    cfg = _build_door_config(args)
    hinge = cfg.hinge

    result: dict[str, Any] = {
        "door_width_mm":      cfg.door_width,
        "door_height_mm":     cfg.door_height,
        "door_thickness_mm":  cfg.door_thickness,
        "num_doors":          cfg.num_doors,
        "overlay_type":       hinge.overlay_type.value,
        "overlay_mm":         hinge.overlay,
        "hinges_per_door":    cfg.hinge_count,
        "total_hinges":       cfg.total_hinge_count,
        "hinge_positions_z_mm": cfg.hinge_positions_z,
        "hinge": {
            "key":             args.get("hinge_key", "blum_clip_top_110_full"),
            "name":            hinge.name,
            "cup_diameter_mm": hinge.cup_diameter,
            "cup_boring_distance_mm": hinge.cup_boring_distance,
            "soft_close":      hinge.soft_close,
            "part_number":     hinge.part_number,
        },
        "gaps": {
            "top_mm":     cfg.gap_top,
            "bottom_mm":  cfg.gap_bottom,
            "side_mm":    cfg.gap_side,
            "between_mm": cfg.gap_between,
        },
    }

    if cfg.pull_key is not None:
        from .cutlist import pull_line_from_door
        from .evaluation import check_door_pull

        placements = cfg.pull_placements  # per-leaf placements
        pull_issues = check_door_pull(cfg)
        bom_line = pull_line_from_door(cfg)
        result["pull"] = {
            "key":                 cfg.pull_key,
            "placements_per_leaf": _pull_placements_to_dicts(placements),
            "pulls_per_leaf":      len(placements),
            "total_pulls":         cfg.total_pull_count,
            "vertical_policy":     cfg.pull_vertical,
            "issues":              _issues_to_dicts(pull_issues),
            "bom":                 _hardware_line_to_dict(bom_line) if bom_line else None,
        }

    return _ok(result)


# ── design_drawer ─────────────────────────────────────────────────────────────

async def _tool_design_drawer(args: dict) -> list[types.TextContent]:
    cfg = _build_drawer_config(args)
    joinery = cfg.joinery
    slide   = cfg.slide

    joinery_info: dict[str, Any] = {
        "style": joinery.style.value,
        "requires_router_bit":     joinery.requires_router_bit,
        "requires_true_thickness": joinery.requires_true_thickness,
    }
    if joinery.style.value != "butt":
        joinery_info["side_dado_depth_x_mm"]  = joinery.side_dado_depth_x
        joinery_info["side_dado_depth_y_mm"]  = joinery.side_dado_depth_y
        joinery_info["fb_channel_depth_x_mm"] = joinery.fb_channel_depth_x
        joinery_info["fb_channel_depth_y_mm"] = joinery.fb_channel_depth_y
        joinery_info["side_tongue_width_mm"]  = joinery.side_tongue_width
    if joinery.style.value == "drawer_lock":
        joinery_info["lock_step_depth_x_mm"] = joinery.lock_step_depth_x
        joinery_info["lock_step_depth_y_mm"] = joinery.lock_step_depth_y

    from .drawer import snap_to_standard_box_height, STANDARD_BOX_HEIGHTS
    slide_length = slide.slide_length_for_depth(cfg.opening_depth)
    raw_height   = _raw_box_height(cfg)
    std_height   = snap_to_standard_box_height(raw_height)

    result: dict[str, Any] = {
        "box_width_mm":               cfg.box_width,
        "box_height_mm":              cfg.box_height,   # snapped when use_standard_height=True
        "box_height_raw_mm":          raw_height,       # clearance-adjusted, before snapping
        "standard_box_height_mm":     std_height,       # always the snapped value for reference
        "use_standard_height":        cfg.use_standard_height,
        "standard_heights_available": list(STANDARD_BOX_HEIGHTS),
        "box_depth_mm":               cfg.box_depth,
        "side_thickness_mm":       cfg.side_thickness,
        "front_back_thickness_mm": cfg.front_back_thickness,
        "bottom_thickness_mm":     cfg.bottom_thickness,
        "slide": {
            "name":                     slide.name,
            "selected_length_mm":       slide_length,
            "nominal_side_clearance_mm": slide.nominal_side_clearance,
            "min_bottom_clearance_mm":  slide.min_bottom_clearance,
            "max_load_kg":              slide.max_load_kg,
        },
        "joinery": joinery_info,
    }

    if cfg.pull_key is not None:
        from .cutlist import pull_line_from_drawer
        from .evaluation import check_drawer_pull

        placements = cfg.pull_placements
        pull_issues = check_drawer_pull(cfg)
        bom_line = pull_line_from_drawer(cfg)
        result["pull"] = {
            "key":               cfg.pull_key,
            "placements":        _pull_placements_to_dicts(placements),
            "count":             len(placements),
            "vertical_policy":   cfg.pull_vertical,
            "face_width_mm":     cfg.face_width,
            "face_height_mm":    cfg.face_height,
            "issues":            _issues_to_dicts(pull_issues),
            "bom":               _hardware_line_to_dict(bom_line) if bom_line else None,
        }

    return _ok(result)


def _build_cost_estimate(
    sheet_goods: list[dict],
    hw_lines: list,
) -> dict:
    """Summarise list-price cost by category with a grand total."""
    sheets_total = sum(e.get("line_total_usd", 0.0) for e in sheet_goods)
    hw_by_cat: dict[str, float] = {}
    for h in hw_lines:
        cat = h.category
        hw_by_cat[cat] = hw_by_cat.get(cat, 0.0) + round(h.packs_to_order * price_for(h.sku), 2)
    hw_total = sum(hw_by_cat.values())
    return {
        "sheet_goods_usd": round(sheets_total, 2),
        "hardware_by_category_usd": {k: round(v, 2) for k, v in hw_by_cat.items()},
        "hardware_total_usd": round(hw_total, 2),
        "grand_total_usd": round(sheets_total + hw_total, 2),
        "note": "List/MSRP prices — actual cost varies by supplier and region.",
    }


# ── generate_cutlist ──────────────────────────────────────────────────────────

async def _tool_generate_cutlist(args: dict) -> list[types.TextContent]:
    fmt          = args.pop("format", "both")
    sheet_length = float(args.pop("sheet_length", 2440))
    sheet_width  = float(args.pop("sheet_width",  1220))
    kerf         = float(args.pop("kerf", 3.2))
    optimizer    = str(args.pop("optimizer", "auto"))
    name         = str(args.pop("name", "cabinet"))
    columns_raw  = args.pop("columns", None)
    args.pop("furniture_top", None)

    cfg = _build_cabinet_config(args)

    interior_width = cfg.width - 2 * cfg.side_thickness
    interior_depth = cfg.depth - cfg.back_thickness

    # ── Carcass panels (side_thickness / 18 mm) ───────────────────────────
    raw_carcass: list[CutlistPanel] = [
        CutlistPanel(name="side", length=cfg.height, width=cfg.depth,
                     thickness=cfg.side_thickness, quantity=2,
                     grain_direction="length", material="baltic_birch",
                     edge_band=["front"]),
        CutlistPanel(name="bottom", length=interior_width, width=interior_depth,
                     thickness=cfg.bottom_thickness, quantity=1,
                     grain_direction="length", material="baltic_birch",
                     edge_band=["front"]),
        CutlistPanel(name="top", length=interior_width, width=interior_depth,
                     thickness=cfg.top_thickness, quantity=1,
                     grain_direction="length", material="baltic_birch",
                     edge_band=["front"]),
    ]
    for i, _ in enumerate(cfg.fixed_shelf_positions):
        raw_carcass.append(CutlistPanel(
            name=f"shelf_{i + 1}", length=interior_width, width=interior_depth,
            thickness=cfg.shelf_thickness, quantity=1,
            grain_direction="length", material="baltic_birch",
        ))

    # ── Back panel (back_thickness / 6 mm) ────────────────────────────────
    raw_6mm: list[CutlistPanel] = [
        CutlistPanel(name="back", length=cfg.height, width=interior_width,
                     thickness=cfg.back_thickness, quantity=1,
                     grain_direction="", material="baltic_birch",
                     notes="1/4 in plywood"),
    ]

    # ── Multi-column additions ─────────────────────────────────────────────
    raw_box: list[CutlistPanel] = []   # 5/8 in (15 mm) drawer box parts
    raw_false_fronts: list[CutlistPanel] = []

    if columns_raw:
        num_dividers = len(columns_raw) - 1
        if num_dividers > 0:
            raw_carcass.append(CutlistPanel(
                name="column_divider",
                length=cfg.height,
                width=cfg.depth - cfg.back_thickness,
                thickness=cfg.side_thickness,
                quantity=num_dividers,
                grain_direction="length",
                material="baltic_birch",
            ))

        for col in columns_raw:
            col_width = float(col["width_mm"])
            for i, _ in enumerate(col.get("fixed_shelf_positions", [])):
                raw_carcass.append(CutlistPanel(
                    name=f"shelf_{i + 1}",
                    length=col_width,
                    width=interior_depth,
                    thickness=cfg.shelf_thickness,
                    quantity=1,
                    grain_direction="length",
                    material="baltic_birch",
                    edge_band=["front"],
                ))
            col_drawers = col.get("openings", col.get("drawer_config", []))
            for row in col_drawers:
                op = _to_opening(row)
                opening_h, slot_type = op.height_mm, op.opening_type
                if slot_type != "drawer":
                    continue
                dcfg = DrawerConfig(
                    opening_width=col_width,
                    opening_height=opening_h,
                    opening_depth=interior_depth,
                )
                bw = round(dcfg.box_width, 1)
                bh = round(dcfg.box_height, 1)
                bd = round(dcfg.box_depth, 1)
                bt = dcfg.side_thickness   # 15 mm (5/8 in)
                bottom_w = round(dcfg.bottom_panel_width, 1)

                raw_box += [
                    CutlistPanel(name="drawer_box_side", length=bd, width=bh,
                                 thickness=bt, quantity=2,
                                 grain_direction="", material="baltic_birch"),
                    CutlistPanel(name="drawer_box_front", length=bw, width=bh,
                                 thickness=bt, quantity=1,
                                 grain_direction="", material="baltic_birch"),
                    CutlistPanel(name="drawer_box_back", length=bw, width=bh,
                                 thickness=bt, quantity=1,
                                 grain_direction="", material="baltic_birch"),
                ]
                raw_6mm.append(CutlistPanel(
                    name="drawer_box_bottom",
                    length=bottom_w,
                    width=bd,
                    thickness=dcfg.bottom_thickness,
                    quantity=1,
                    grain_direction="",
                    material="baltic_birch",
                    notes="1/4 in, dado-captured",
                ))

                face_w = round(col_width + 2 * dcfg.face_overlay_sides, 1)
                face_h = round(opening_h + dcfg.face_overlay_top + dcfg.face_overlay_bottom, 1)
                raw_false_fronts.append(CutlistPanel(
                    name="false_front",
                    length=face_w,
                    width=face_h,
                    thickness=dcfg.face_thickness,
                    quantity=1,
                    grain_direction="length",
                    material="finished_wood",
                    notes="species TBD; full-overlay 3 mm reveal",
                ))

    # Consolidate each material group
    carcass_panels  = consolidate_bom(raw_carcass)
    panels_6mm      = consolidate_bom(raw_6mm)
    box_panels      = consolidate_bom(raw_box)
    false_fronts    = consolidate_bom(raw_false_fronts)

    all_panels = carcass_panels + box_panels + panels_6mm + false_fronts

    # ── Sheet optimisation per thickness group ─────────────────────────────
    def _make_sheet(t: float) -> SheetStock:
        return SheetStock(
            name=f"{int(sheet_length)}x{int(sheet_width)} {t:.0f}mm",
            length=sheet_length, width=sheet_width, thickness=t,
        )

    def _opt_group(panels: list[CutlistPanel], thickness: float):
        # Returns (summary_dict, OptimizationResult | None)
        if not panels:
            return {}, None
        sheet = _make_sheet(thickness)
        opt = optimize_cutlist(panels, stock_sheet=sheet, kerf=kerf, algorithm=optimizer)
        return ({"sheets_used": opt.sheets_used, "waste_pct": opt.waste_pct,
                 "unplaced": opt.unplaced}, opt)

    carcass_t   = cfg.side_thickness
    box_t       = DrawerConfig.__dataclass_fields__["side_thickness"].default
    bottom_t    = DrawerConfig.__dataclass_fields__["bottom_thickness"].default

    opt_carcass, opt_carcass_result = _opt_group(carcass_panels, carcass_t)
    opt_box, opt_box_result         = _opt_group(box_panels, box_t)
    opt_6mm, opt_6mm_result         = _opt_group(panels_6mm, bottom_t)

    # ── Sheet goods summary ────────────────────────────────────────────────
    sheet_goods = []
    if carcass_panels:
        sheets = opt_carcass.get("sheets_used", 0)
        unit_p = price_for("sheet_baltic_birch_18mm")
        entry = {"material": f"Baltic Birch 3/4\" ({carcass_t:.0f} mm)",
                 "thickness_mm": carcass_t,
                 "panel_count": sum(p.quantity for p in carcass_panels),
                 "price_per_sheet_usd": unit_p,
                 "line_total_usd": round(sheets * unit_p, 2)}
        entry.update(opt_carcass)
        sheet_goods.append(entry)
    if box_panels:
        sheets = opt_box.get("sheets_used", 0)
        unit_p = price_for("sheet_baltic_birch_15mm")
        entry = {"material": f"Baltic Birch 5/8\" ({box_t:.0f} mm)",
                 "thickness_mm": box_t,
                 "panel_count": sum(p.quantity for p in box_panels),
                 "price_per_sheet_usd": unit_p,
                 "line_total_usd": round(sheets * unit_p, 2)}
        entry.update(opt_box)
        sheet_goods.append(entry)
    if panels_6mm:
        sheets = opt_6mm.get("sheets_used", 0)
        unit_p = price_for("sheet_baltic_birch_6mm")
        entry = {"material": f"Baltic Birch 1/4\" ({bottom_t:.0f} mm)",
                 "thickness_mm": bottom_t,
                 "panel_count": sum(p.quantity for p in panels_6mm),
                 "price_per_sheet_usd": unit_p,
                 "line_total_usd": round(sheets * unit_p, 2)}
        entry.update(opt_6mm)
        sheet_goods.append(entry)
    if false_fronts:
        sheet_goods.append({
            "material": "Finished wood — false fronts (species TBD)",
            "thickness_mm": DrawerConfig.__dataclass_fields__["face_thickness"].default,
            "panel_count": sum(p.quantity for p in false_fronts),
            "note": "Order solid stock or veneered panel; not included in sheet optimisation.",
        })

    # ── File output ────────────────────────────────────────────────────────
    out_dir = Path.home() / ".cabinet-mcp" / "cutlists"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path  = out_dir / f"{name}_cutlist.csv"
    json_path = out_dir / f"{name}_cutlist.json"
    csv_path.write_text(to_csv(all_panels))
    json_path.write_text(to_json(all_panels, [_make_sheet(carcass_t)]))

    files: dict[str, str] = {"csv": str(csv_path), "json": str(json_path)}

    # ── Hardware BOM ───────────────────────────────────────────────────────
    hw_lines = hardware_bom_for_cabinet_config(cfg, columns_raw)
    if hw_lines:
        hw_json_path = out_dir / f"{name}_hardware_bom.json"
        hw_json_path.write_text(to_hardware_json(hw_lines))
        files["hardware_bom_json"] = str(hw_json_path)

    layout_groups = []
    if opt_carcass_result and carcass_panels:
        layout_groups.append((
            f'18mm Carcass (3/4") — {opt_carcass_result.sheets_used} sheets',
            carcass_panels, opt_carcass_result,
        ))
    if opt_box_result and box_panels:
        layout_groups.append((
            f'15mm Drawer Boxes (5/8") — {opt_box_result.sheets_used} sheets',
            box_panels, opt_box_result,
        ))
    if opt_6mm_result and panels_6mm:
        layout_groups.append((
            f'6mm Backs & Bottoms (1/4") — {opt_6mm_result.sheets_used} sheets',
            panels_6mm, opt_6mm_result,
        ))
    if layout_groups:
        html = generate_sheet_layout_html(
            layout_groups, cabinet_name=name, kerf=kerf,
            hardware_lines=hw_lines or None,
        )
        layout_path = out_dir / f"{name}_layout.html"
        layout_path.write_text(html)
        files["layout"] = str(layout_path)

        try:
            pdf_bytes = generate_sheet_layout_pdf(
                layout_groups, cabinet_name=name, kerf=kerf,
                hardware_lines=hw_lines or None,
            )
            pdf_path = out_dir / f"{name}_layout.pdf"
            pdf_path.write_bytes(pdf_bytes)
            files["pdf"] = str(pdf_path)
        except ImportError:
            pass  # reportlab not installed

    # ── Build result ───────────────────────────────────────────────────────
    result: dict[str, Any] = {
        "panel_count": len(all_panels),
        "sheet_goods": sheet_goods,
        "panels_summary": [
            {"name": p.name, "length_mm": p.length, "width_mm": p.width,
             "thickness_mm": p.thickness, "qty": p.quantity, "material": p.material}
            for p in all_panels
        ],
        "hardware_bom": [
            {
                "category": h.category,
                "name": h.name,
                "brand": h.brand,
                "model_number": h.model_number,
                "pieces_needed": h.pieces_needed,
                "pack_quantity": h.pack_quantity,
                "packs_to_order": h.packs_to_order,
                "leftover": h.leftover,
                "notes": h.notes,
                "unit_price_usd": price_for(h.sku),
                "line_total_usd": round(h.packs_to_order * price_for(h.sku), 2),
            }
            for h in hw_lines
        ],
        "cost_estimate": _build_cost_estimate(sheet_goods, hw_lines),
        "files": files,
    }

    if fmt in ("json", "both"):
        result["cutlist_json"] = json.loads(to_json(all_panels, [_make_sheet(carcass_t)]))
    if fmt in ("csv", "both"):
        result["cutlist_csv"] = to_csv(all_panels)

    if "sheets_used" in opt_carcass:
        result["sheets_used"]     = opt_carcass["sheets_used"]
        result["waste_pct"]       = opt_carcass["waste_pct"]
        result["unplaced_panels"] = opt_carcass["unplaced"]
    if optimizer == "rectpack" or (optimizer == "auto" and not _OPCUT_AVAILABLE and _RECTPACK_AVAILABLE):
        algo = "rectpack GuillotineBssfSas"
    elif optimizer == "strip" or (optimizer == "auto" and not _OPCUT_AVAILABLE and not _RECTPACK_AVAILABLE):
        algo = "strip-cutting (fallback)"
    else:
        algo = "opcut FORWARD_GREEDY (guillotine)"
    result["optimization_note"] = (
        f"Sheet layout via {algo}. "
        "Every cut is a straight line across the remaining panel — "
        "the layout is directly executable at the saw."
    )

    return _ok(result)


# ── compare_joinery ───────────────────────────────────────────────────────────

async def _tool_compare_joinery(args: dict) -> list[types.TextContent]:
    from .joinery import DrawerJoinerySpec

    t_s  = float(args.get("side_thickness", 12.0))
    t_fb = float(args.get("front_back_thickness", 12.0))

    comparison = {}
    for style in DrawerJoineryStyle:
        spec = DrawerJoinerySpec.from_stock(style, t_s, t_fb)
        entry: dict[str, Any] = {
            "style": style.value,
            "requires_router_bit":    spec.requires_router_bit,
            "requires_true_thickness": spec.requires_true_thickness,
            "side_dado_depth_x_mm":  spec.side_dado_depth_x,
            "side_dado_depth_y_mm":  spec.side_dado_depth_y,
            "fb_channel_depth_x_mm": spec.fb_channel_depth_x,
            "fb_channel_depth_y_mm": spec.fb_channel_depth_y,
        }
        if style == DrawerJoineryStyle.QQQ:
            entry["note"] = (
                f"All cuts = side_thickness ÷ 2 = {t_s / 2:.1f} mm. "
                "True 18 mm stock required for nominal 18 mm settings."
            )
        if style == DrawerJoineryStyle.DRAWER_LOCK:
            entry["lock_step_depth_x_mm"] = spec.lock_step_depth_x
            entry["lock_step_depth_y_mm"] = spec.lock_step_depth_y
            entry["note"] = "Requires dedicated drawer-lock router bit."
        comparison[style.value] = entry

    return _ok({
        "side_thickness_mm":       t_s,
        "front_back_thickness_mm": t_fb,
        "styles": comparison,
    })


# ── suggest_proportions ───────────────────────────────────────────────────────

async def _tool_suggest_proportions(args: dict) -> list[types.TextContent]:
    width    = float(args["width"])
    height   = float(args["height"])
    side_t   = float(args.get("side_thickness",   18))
    bottom_t = float(args.get("bottom_thickness", 18))
    top_t    = float(args.get("top_thickness",    18))
    num_drawers = args.get("num_drawers")
    num_columns = args.get("num_columns")
    wide_index  = args.get("wide_index")

    if not num_drawers and not num_columns:
        return _err("Provide at least one of num_drawers or num_columns.")

    interior_h = height - bottom_t - top_t
    interior_w = width - 2 * side_t

    result: dict[str, Any] = {
        "interior_height_mm": interior_h,
        "interior_width_mm":  interior_w,
    }

    if num_drawers:
        suggestions = []
        for preset, ratio in _RATIO_PRESETS.items():
            try:
                heights = _grad_heights(interior_h, int(num_drawers), preset)
                suggestions.append({
                    "preset":              preset,
                    "ratio":               ratio,
                    "character":           _PRESET_DESCRIPTIONS[preset],
                    "viable":              True,
                    "heights_mm":          heights,
                    "heights_in":          [_mm_to_inches_str(h) for h in heights],
                    "bottom_mm":           heights[0],
                    "top_mm":              heights[-1],
                    "bottom_to_top_ratio": round(heights[0] / heights[-1], 3),
                })
            except ValueError as exc:
                suggestions.append({
                    "preset":    preset,
                    "ratio":     ratio,
                    "character": _PRESET_DESCRIPTIONS[preset],
                    "viable":    False,
                    "reason":    str(exc),
                })
        result["drawer_suggestions"] = suggestions

    if num_columns:
        suggestions = []
        n_cols_suggest = int(num_columns)
        available_w_suggest = interior_w - (n_cols_suggest - 1) * side_t
        for preset, ratio in _RATIO_PRESETS.items():
            widths = _col_widths(available_w_suggest, n_cols_suggest, wide_index, preset)
            wide_w   = widths[wide_index] if wide_index is not None else None
            narrow_w = widths[0] if wide_index != 0 else widths[1]
            suggestions.append({
                "preset":           preset,
                "ratio":            ratio,
                "character":        _PRESET_DESCRIPTIONS[preset],
                "widths_mm":        widths,
                "wide_column_mm":   wide_w,
                "narrow_column_mm": narrow_w,
            })
        result["column_suggestions"] = suggestions

    return _ok(result)


# ── visualize_cabinet ─────────────────────────────────────────────────────────

async def _tool_visualize_cabinet(args: dict) -> list[types.TextContent]:
    name          = str(args.pop("name", "cabinet"))
    output_dir    = str(args.pop("output_dir", "~/.cabinet-mcp/visualizations"))
    open_browser  = bool(args.pop("open_browser", True))
    tolerance     = float(args.pop("tolerance", 0.1))
    num_bays      = int(args.pop("num_bays", 1))
    columns_raw        = args.pop("columns", None)
    furniture_top      = bool(args.pop("furniture_top", False))
    divider_full_height = bool(args.pop("divider_full_height", False))

    cfg = _build_cabinet_config(args)

    transition_shelf_zs: list[float] = []
    divider_top_z: float | None = None

    if columns_raw:
        # Build one bay config per column so build_multi_bay_cabinet renders
        # the correct dividers.  Bay exterior width = column interior width +
        # 2×side_thickness; the multi-bay function handles shared dividers.
        side_t = cfg.side_thickness
        # Determine which column indices have door slots, then assign hinge sides:
        # leftmost door column → "left", rightmost → "right" (French-door style).
        def _col_openings_raw(col: dict) -> list:
            return col.get("openings", col.get("drawer_config", []))

        _has_door = [
            any(_to_opening(r).opening_type in ("door", "door_pair")
                for r in _col_openings_raw(col))
            for col in columns_raw
        ]
        _door_col_indices = [i for i, has in enumerate(_has_door) if has]
        _rightmost_door_col = _door_col_indices[-1] if _door_col_indices else -1

        bay_configs = []
        for col_idx, col in enumerate(columns_raw):
            if col_idx == _rightmost_door_col and len(_door_col_indices) > 1:
                hinge_side = "right"
            else:
                hinge_side = cfg.door_hinge_side
            bay_configs.append(CabinetConfig(
                width=float(col["width_mm"]) + 2 * side_t,
                height=cfg.height,
                depth=cfg.depth,
                side_thickness=side_t,
                bottom_thickness=cfg.bottom_thickness,
                top_thickness=cfg.top_thickness,
                back_thickness=cfg.back_thickness,
                shelf_thickness=cfg.shelf_thickness,
                drawer_slide=cfg.drawer_slide,
                drawer_pull=cfg.drawer_pull,
                door_pull=cfg.door_pull,
                door_hinge_side=hinge_side,
                door_pull_inset_mm=cfg.door_pull_inset_mm,
                fixed_shelf_positions=[
                    float(z) for z in col.get("fixed_shelf_positions", [])
                ],
                openings=[
                    _to_opening(r)
                    for r in _sort_drawer_config(_col_openings_raw(col))
                ],
            ))
        total_width = cfg.width
        info = {"width": total_width, "height": cfg.height, "depth": cfg.depth,
                "columns": len(bay_configs)}

        # Detect drawer-to-door transitions per column; use lowest transition z.
        per_bay_transitions = []
        for bc in bay_configs:
            z = bc.bottom_thickness
            for op in bc.openings:
                if op.opening_type in ("door", "door_pair"):
                    per_bay_transitions.append(z)
                    break
                z += op.height_mm
        if per_bay_transitions:
            transition_shelf_zs.append(min(per_bay_transitions))

        # Clip center divider to drawer zone unless caller wants full-height.
        if not divider_full_height and transition_shelf_zs:
            divider_top_z = transition_shelf_zs[0] + bay_configs[0].shelf_thickness
    else:
        bay_configs = [cfg] * num_bays
        info = {"width": cfg.width * num_bays, "height": cfg.height, "depth": cfg.depth}

    # When there's a door zone at the top of the column, extend faces to the
    # carcass exterior top so doors don't leave a gap at the top panel.
    face_top_overhang = (
        bay_configs[0].top_thickness if transition_shelf_zs else 0.0
    )

    assy, parts = _build_multi_bay_cabinet(
        bay_configs,
        feet_at_dividers=(columns_raw is None),
        furniture_top=furniture_top,
        face_top_overhang=face_top_overhang,
        transition_shelf_zs=transition_shelf_zs or None,
        divider_top_z=divider_top_z,
    )
    result = _visualize_assembly(
        assy,
        parts,
        output_dir=output_dir,
        name=name,
        open_browser=open_browser,
        tolerance=tolerance,
        info=info,
    )

    return _ok({
        "html":        result["html"],
        "glb":         result["glb"],
        "parts":       result["parts"],
        "glb_size_kb": result["glb_size_kb"],
        "note": (
            "HTML viewer written. Open the 'html' path in a browser to inspect "
            "the 3D model (orbit with left-drag, pan with right-drag, scroll to zoom)."
        ),
    })


# ── list_presets ──────────────────────────────────────────────────────────────

async def _tool_list_presets(args: dict) -> list[types.TextContent]:
    category = args.get("category")
    tag      = args.get("tag")

    presets = _list_presets(category=category, tag=tag)

    return _ok({
        "count": len(presets),
        "presets": [p.summary() for p in presets],
    })


# ── apply_preset ──────────────────────────────────────────────────────────────

async def _tool_apply_preset(args: dict) -> list[types.TextContent]:
    name      = args.get("name", "")
    overrides = args.get("overrides") or {}

    synonym_redirect: str | None = None
    try:
        preset = get_preset(name)
    except KeyError:
        # Try resolving via furniture-type synonym (e.g. "dresser" → "bedroom_dresser").
        synonym_slugs = SYNONYM_TO_PRESETS.get(name.lower().strip(), ())
        resolved = next(
            (get_preset(slug) for slug in synonym_slugs if slug in PRESETS),
            None,
        )
        if resolved is not None:
            preset = resolved
            synonym_redirect = name
        else:
            ref = get_furniture(name)
            note = (
                f"No preset named {name!r}. "
                + (
                    f"Closest furniture type: '{ref.piece}' ({ref.category}). "
                    f"Suggested presets: {list(ref.preset_keys) or 'none yet'}."
                    if ref else
                    "No matching furniture type found either."
                )
            )
            return _ok({"error": note, "available": sorted(PRESETS.keys())})

    # Merge: start from preset's config dict, apply caller overrides on top.
    merged = preset.config_dict()
    for key, value in overrides.items():
        if key == "carcass_joinery" and isinstance(value, str):
            merged[key] = value          # kept as string; _build_cabinet_config handles enum
        else:
            merged[key] = value

    # Validate merged config builds without error.
    try:
        cfg = _build_cabinet_config(dict(merged))
    except Exception as exc:
        return _err(f"Override produced an invalid config: {type(exc).__name__}: {exc}")

    interior_h = cfg.height - cfg.bottom_thickness - cfg.top_thickness
    stack_total = sum(op.height_mm for op in cfg.openings)
    stack_matches = abs(stack_total - interior_h) < 0.01

    result: dict[str, Any] = {
        "preset_name":   preset.name,
        "display_name":  preset.display_name,
        "description":   preset.description,
        "category":      preset.category,
        "config":        merged,
        "interior_height_mm":          interior_h,
        "opening_stack_total_mm":      stack_total,
        "opening_stack_matches_interior": stack_matches,
    }
    if synonym_redirect:
        result["resolved_from"] = synonym_redirect

    if not stack_matches and cfg.openings:
        diff = interior_h - stack_total
        result["opening_stack_warning"] = (
            f"Opening stack ({stack_total:.0f} mm) does not fill interior height "
            f"({interior_h:.0f} mm) — {abs(diff):.0f} mm "
            f"{'unaccounted for' if diff > 0 else 'over by'}. "
            "Update drawer_config heights to match."
        )

    return _ok(result)


# ── identify_furniture_type ───────────────────────────────────────────────────

async def _tool_identify_furniture_type(args: dict) -> list[types.TextContent]:
    query = str(args.get("name", "")).strip()
    if not query:
        return _ok({"error": "'name' is required."})

    matches = identify_furniture(query)
    if not matches:
        return _ok({
            "error": f"No furniture type found matching {query!r}.",
            "suggestion": "Try a common English name or synonym (e.g. 'dresser', 'armoire', 'credenza').",
        })

    def _enrich(ref) -> dict:
        d = ref.to_dict()
        d["presets"] = [
            PRESETS[slug].summary()
            for slug in ref.preset_keys
            if slug in PRESETS
        ]
        return d

    if len(matches) == 1:
        return _ok({"match": _enrich(matches[0])})

    return _ok({
        "candidates": [_enrich(r) for r in matches],
        "note": f"Multiple furniture types match {query!r}. Narrow your query for an exact match.",
    })


# ── auto_fix_cabinet ─────────────────────────────────────────────────────────

async def _tool_auto_fix_cabinet(args: dict) -> list[types.TextContent]:
    cfg = _build_cabinet_config(args)
    result: AutoFixResult = _auto_fix(cfg)

    errors_before = sum(1 for i in result.initial_issues if i.severity == Severity.ERROR)
    errors_after  = sum(1 for i in result.final_issues   if i.severity == Severity.ERROR)

    # Re-serialise the (possibly modified) config so it can be passed back
    # to evaluate_cabinet or describe_design directly.
    fixed_cfg = result.config
    config_dict: dict[str, Any] = {
        "width":            fixed_cfg.width,
        "height":           fixed_cfg.height,
        "depth":            fixed_cfg.depth,
        "side_thickness":   fixed_cfg.side_thickness,
        "bottom_thickness": fixed_cfg.bottom_thickness,
        "top_thickness":    fixed_cfg.top_thickness,
        "shelf_thickness":  fixed_cfg.shelf_thickness,
        "back_thickness":   fixed_cfg.back_thickness,
        "drawer_config":    [[op.height_mm, op.opening_type] for op in fixed_cfg.openings],
        "carcass_joinery":  fixed_cfg.carcass_joinery.value,
        "door_hinge":       fixed_cfg.door_hinge,
        "drawer_slide":     fixed_cfg.drawer_slide,
        "adj_shelf_holes":  fixed_cfg.adj_shelf_holes,
        "leg_key":          fixed_cfg.leg_key,
        "leg_count":        fixed_cfg.leg_count,
        "leg_inset":        fixed_cfg.leg_inset,
    }

    return _ok({
        "config":         config_dict,
        "changes":        result.changes,
        "errors_before":  errors_before,
        "errors_after":   errors_after,
        "fixed":          result.fixed,
        "clean":          result.clean,
        "initial_issues": _issues_to_dicts(result.initial_issues),
        "final_issues":   _issues_to_dicts(result.final_issues),
        "fixable_checks": fixable_checks(),
    })


# ── describe_design ──────────────────────────────────────────────────────────

async def _tool_describe_design(args: dict) -> list[types.TextContent]:
    cfg = _build_cabinet_config(args)
    return _ok(_describe_design(cfg))


# ── design_legs ───────────────────────────────────────────────────────────────

def _compute_leg_positions(
    width: float,
    depth: float,
    count: int,
    pattern: str,
    inset: float,
) -> list[dict[str, float]]:
    """Return a list of {x, y} foot-centre coordinates.

    Origin is the front-left corner of the cabinet.  X runs left→right,
    Y runs front→back.
    """
    positions: list[dict[str, float]] = []

    if pattern == "corners":
        positions = [
            {"x": inset,         "y": inset},
            {"x": width - inset, "y": inset},
            {"x": inset,         "y": depth - inset},
            {"x": width - inset, "y": depth - inset},
        ]
        # If more than 4 feet requested, add evenly-spaced extras along front/back
        extra = count - 4
        if extra > 0:
            spacing = width / (extra + 1)
            for i in range(extra):
                x = spacing * (i + 1)
                positions.append({"x": x, "y": inset})
                positions.append({"x": x, "y": depth - inset})

    elif pattern == "corners_and_midspan":
        positions = [
            {"x": inset,         "y": inset},
            {"x": width - inset, "y": inset},
            {"x": inset,         "y": depth - inset},
            {"x": width - inset, "y": depth - inset},
            {"x": width / 2,     "y": inset},
            {"x": width / 2,     "y": depth - inset},
        ]

    elif pattern == "along_front_back":
        half = max(count // 2, 1)
        spacing = (width - 2 * inset) / (half - 1) if half > 1 else 0.0
        for i in range(half):
            x = inset + spacing * i if half > 1 else width / 2
            positions.append({"x": x, "y": inset})
            positions.append({"x": x, "y": depth - inset})

    # Trim or pad to exactly count feet
    return positions[:count]


async def _tool_design_legs(args: dict) -> list[types.TextContent]:
    cab_width  = float(args.get("cabinet_width",  600.0))
    cab_depth  = float(args.get("cabinet_depth",  550.0))
    leg_key    = str(args.get("leg_key",   "richelieu_176138106"))
    count      = int(args.get("count",     4))
    pattern    = str(args.get("leg_pattern", "corners"))
    inset      = float(args.get("inset_mm", 30.0))
    cab_weight = float(args.get("cabinet_weight_kg", 0.0))

    try:
        leg = get_leg(leg_key)
    except KeyError as exc:
        return _err(str(exc))

    positions = _compute_leg_positions(cab_width, cab_depth, count, pattern, inset)
    actual_count = len(positions)

    load_per_leg: float | None = None
    load_note: str = ""
    if cab_weight > 0 and actual_count > 0:
        load_per_leg = cab_weight / actual_count
        capacity = leg.load_capacity_kg
        if load_per_leg > capacity:
            load_note = (
                f"WARNING: load per leg ({load_per_leg:.1f} kg) exceeds "
                f"rated capacity ({capacity:.1f} kg). Add more legs or choose a heavier spec."
            )
        else:
            load_note = (
                f"OK — {load_per_leg:.1f} kg per leg vs {capacity:.1f} kg rated "
                f"({(load_per_leg / capacity * 100):.0f}% capacity)."
            )

    packs_needed = -(-actual_count // 2) if "richelieu" in leg_key else actual_count  # ceiling div
    ordering_note = (
        f"Sold in 2-packs — order {packs_needed} pack(s) for {actual_count} legs."
        if "richelieu" in leg_key
        else f"Order {actual_count} individual legs."
    )

    result: dict[str, Any] = {
        "leg": {
            "key":               leg_key,
            "name":              leg.name,
            "height_mm":         leg.height_mm,
            "base_diameter_mm":  leg.base_diameter_mm,
            "is_adjustable":     leg.is_adjustable,
            "load_capacity_kg":  leg.load_capacity_kg,
            "finish":            leg.finish,
            "part_number":       leg.part_number,
            "notes":             leg.notes,
        },
        "count":           actual_count,
        "pattern":         pattern,
        "inset_mm":        inset,
        "total_height_mm": leg.height_mm,
        "placement_mm":    positions,
        "ordering":        ordering_note,
    }
    if load_per_leg is not None:
        result["load_per_leg_kg"] = round(load_per_leg, 2)
        result["load_check"]      = load_note

    return _ok(result)


# ── design_pulls ──────────────────────────────────────────────────────────────

async def _tool_design_pulls(args: dict) -> list[types.TextContent]:
    """Compute per-slot pull placements + cabinet-level pull issues + BOM.

    Walks the cabinet's drawer_config (or columns) once, building a parametric
    DrawerConfig / DoorConfig per slot, and reports placements + per-slot fit
    issues. Cabinet-level style consistency is checked separately.
    """
    from .drawer import DrawerConfig
    from .door import DoorConfig
    from .cutlist import pull_lines_for_cabinet_config
    from .evaluation import (
        check_drawer_pull,
        check_door_pull,
        check_cabinet_pull_consistency,
    )

    # Tool-only knobs that don't live on CabinetConfig — strip before building.
    drawer_pull_vertical = args.pop("drawer_pull_vertical", "center")
    door_pull_vertical   = args.pop("door_pull_vertical",   "center")

    try:
        cab_cfg = _build_cabinet_config(args)
    except (TypeError, ValueError, KeyError) as exc:
        return _err(f"Could not build cabinet config: {exc}")

    drawer_slots: list[dict[str, Any]] = []
    door_slots: list[dict[str, Any]] = []

    def _walk_stack(stack, interior_width: float, interior_depth: float,
                    column_index: int | None) -> None:
        for slot_idx, item in enumerate(stack):
            op = _to_opening(item)
            opening_h  = op.height_mm
            slot_type  = op.opening_type
            base: dict[str, Any] = {
                "slot_index":        slot_idx,
                "opening_height_mm": opening_h,
                "slot_type":         slot_type,
            }
            if column_index is not None:
                base["column_index"] = column_index

            if slot_type == "drawer":
                pull_key = op.pull_key or cab_cfg.drawer_pull
                if pull_key is None:
                    continue  # nothing to place
                dcfg = DrawerConfig(
                    opening_width=interior_width,
                    opening_height=opening_h,
                    opening_depth=interior_depth,
                    slide_key=cab_cfg.drawer_slide,
                    pull_key=pull_key,
                    pull_vertical=drawer_pull_vertical,
                )
                try:
                    placements = dcfg.pull_placements
                except KeyError:
                    placements = []
                issues = check_drawer_pull(dcfg)
                drawer_slots.append({
                    **base,
                    "face_width_mm":   dcfg.face_width,
                    "face_height_mm":  dcfg.face_height,
                    "pull_key":        pull_key,
                    "vertical_policy": drawer_pull_vertical,
                    "placements":      _pull_placements_to_dicts(placements),
                    "count":           len(placements),
                    "issues":          _issues_to_dicts(issues),
                })

            elif slot_type in ("door", "door_pair"):
                pull_key = op.pull_key or cab_cfg.door_pull
                hinge_key = op.hinge_key or cab_cfg.door_hinge
                if pull_key is None:
                    continue
                num_doors = 2 if slot_type == "door_pair" else 1
                dcfg = DoorConfig(
                    opening_width=interior_width,
                    opening_height=opening_h,
                    num_doors=num_doors,
                    hinge_key=hinge_key,
                    pull_key=pull_key,
                    pull_vertical=door_pull_vertical,
                )
                try:
                    placements = dcfg.pull_placements
                    total = dcfg.total_pull_count
                except KeyError:
                    placements = []
                    total = 0
                issues = check_door_pull(dcfg)
                door_slots.append({
                    **base,
                    "num_doors":           num_doors,
                    "leaf_width_mm":       dcfg.door_width,
                    "leaf_height_mm":      dcfg.door_height,
                    "pull_key":            pull_key,
                    "vertical_policy":     door_pull_vertical,
                    "placements_per_leaf": _pull_placements_to_dicts(placements),
                    "pulls_per_leaf":      len(placements),
                    "total_pulls":         total,
                    "issues":              _issues_to_dicts(issues),
                })
            # shelf / open slots contribute nothing

    if getattr(cab_cfg, "columns", None):
        for ci, col in enumerate(cab_cfg.columns):
            _walk_stack(col.openings, col.width_mm, cab_cfg.interior_depth, ci)
    else:
        _walk_stack(cab_cfg.openings, cab_cfg.interior_width,
                    cab_cfg.interior_depth, None)

    cabinet_issues = check_cabinet_pull_consistency(cab_cfg)
    bom_lines = pull_lines_for_cabinet_config(cab_cfg)

    result: dict[str, Any] = {
        "exterior": {
            "width_mm":  cab_cfg.width,
            "height_mm": cab_cfg.height,
            "depth_mm":  cab_cfg.depth,
        },
        "drawer_pull":          cab_cfg.drawer_pull,
        "door_pull":            cab_cfg.door_pull,
        "drawer_pull_vertical": drawer_pull_vertical,
        "door_pull_vertical":   door_pull_vertical,
        "drawer_slots":         drawer_slots,
        "door_slots":           door_slots,
        "cabinet_issues":       _issues_to_dicts(cabinet_issues),
        "hardware_bom":         [_hardware_line_to_dict(l) for l in bom_lines],
        "bom_totals": {
            "line_count":     len(bom_lines),
            "pieces_needed":  sum(l.pieces_needed for l in bom_lines),
            "packs_to_order": sum(l.packs_to_order for l in bom_lines),
        },
    }
    return _ok(result)


# ─── Port management ──────────────────────────────────────────────────────────

#: Default port for HTTP/SSE mode — chosen to be distinctive and avoid
#: accidental collision with common dev servers (3000, 3001, 8000, 8080 …).
DEFAULT_PORT: int = 3749

#: File written when the server binds in HTTP mode so other processes can
#: discover the actual port without parsing log output.
PORT_FILE: Path = Path("/tmp/cabinet-mcp.port")


def find_free_port(start: int = DEFAULT_PORT, max_attempts: int = 20) -> int:
    """Return the first unused TCP port in ``[start, start + max_attempts)``.

    Tries each candidate port in order.  Raises ``RuntimeError`` if the entire
    range is occupied.
    """
    for port in range(start, start + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            # Do NOT set SO_REUSEADDR here — we need a true "is this port free"
            # check, not a "can I eventually take it" check.
            try:
                sock.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        f"No free port found in range {start}–{start + max_attempts - 1}. "
        "Use --port to choose a different starting point or --max-port-attempts "
        "to widen the search window."
    )


def write_port_file(port: int, path: Path = PORT_FILE) -> None:
    """Write the resolved port to a well-known file so other tools can read it."""
    path.write_text(str(port))


def clear_port_file(path: Path = PORT_FILE) -> None:
    """Remove the port file on clean exit."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# ─── Transport runners ────────────────────────────────────────────────────────

def _init_options() -> InitializationOptions:
    return InitializationOptions(
        server_name="cabinet-mcp",
        server_version="0.1.0",
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    )


async def _run_stdio() -> None:
    """Run the server over stdin/stdout (default, for Claude Desktop / Gemini CLI)."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, _init_options())


async def _run_http(host: str, port: int) -> None:
    """Run the server over HTTP/SSE (Starlette + uvicorn)."""
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request):  # type: ignore[no-untyped-def]
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await server.run(read_stream, write_stream, _init_options())

    starlette_app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ],
    )

    print(
        f"cabinet-mcp  HTTP/SSE  http://{host}:{port}/sse",
        file=sys.stderr,
        flush=True,
    )

    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level="warning",   # suppress uvicorn access logs; our own startup line is enough
    )
    uv_server = uvicorn.Server(config)
    await uv_server.serve()


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(
        prog="cabinet-mcp",
        description="Cabinet-design MCP server (stdio by default, HTTP/SSE with --http).",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Use HTTP/SSE transport instead of stdio.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        metavar="PORT",
        help=f"Starting port for HTTP mode (auto-increments if in use). Default: {DEFAULT_PORT}.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        metavar="HOST",
        help="Bind address for HTTP mode. Default: 127.0.0.1.",
    )
    parser.add_argument(
        "--max-port-attempts",
        type=int,
        default=20,
        metavar="N",
        dest="max_port_attempts",
        help="Number of consecutive ports to try before giving up. Default: 20.",
    )
    parser.add_argument(
        "--port-file",
        type=Path,
        default=PORT_FILE,
        metavar="PATH",
        dest="port_file",
        help=f"Where to write the resolved port in HTTP mode. Default: {PORT_FILE}.",
    )

    args = parser.parse_args()

    if args.http:
        port = find_free_port(args.port, args.max_port_attempts)
        write_port_file(port, args.port_file)
        try:
            asyncio.run(_run_http(args.host, port))
        finally:
            clear_port_file(args.port_file)
    else:
        asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()
