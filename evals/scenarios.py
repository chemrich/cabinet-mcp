"""
Evaluation scenarios for the cabinet-design MCP server.

Each scenario models a realistic user request: a natural-language prompt, one or
more MCP tool calls that an LLM should make, and assertions on the results.

Scenarios are grouped by tag so the harness can run subsets:
    basic_cabinet, drawer, door, joinery, cutlist, evaluation, edge_case, kitchen
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


# ─── Assertion primitives ─────────────────────────────────────────────────────

class Op(Enum):
    """Comparison operators for result assertions."""
    EQ        = "eq"          # exact equality
    APPROX    = "approx"      # within 0.1
    GT        = "gt"          # greater than
    GTE       = "gte"         # greater than or equal
    LT        = "lt"          # less than
    LTE       = "lte"         # less than or equal
    IN        = "in"          # value is in a list
    CONTAINS  = "contains"    # list result contains value
    HAS_KEY   = "has_key"     # dict result has key
    LEN_EQ    = "len_eq"      # length of list equals
    LEN_GTE   = "len_gte"     # length of list >= value
    IS_TRUE   = "is_true"     # truthy
    IS_FALSE  = "is_false"    # falsy
    NO_ERRORS = "no_errors"   # summary.errors == 0
    HAS_ERROR = "has_error"   # summary.errors > 0
    HAS_WARNING = "has_warning"  # summary.warnings > 0


@dataclass(frozen=True)
class Assertion:
    """A single check on a tool result.

    ``path`` is a dot-separated key path into the JSON result, e.g.
    ``"exterior.width_mm"`` or ``"summary.errors"``.
    """
    path: str
    op: Op
    expected: Any = None
    description: str = ""


# ─── Tool call spec ───────────────────────────────────────────────────────────

@dataclass
class ToolCall:
    """One MCP tool invocation with arguments and post-assertions."""
    tool: str                         # tool name (e.g. "design_cabinet")
    args: dict[str, Any]              # arguments passed to the tool
    assertions: list[Assertion] = field(default_factory=list)
    label: str = ""                   # human-readable label for reporting


# ─── Scenario ─────────────────────────────────────────────────────────────────

@dataclass
class Scenario:
    """A complete eval scenario."""
    name: str
    prompt: str                          # natural-language user request
    tool_calls: list[ToolCall]           # expected MCP tool sequence
    tags: list[str] = field(default_factory=list)
    description: str = ""
    difficulty: str = "standard"         # "basic" | "standard" | "advanced"


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario catalogue
# ═══════════════════════════════════════════════════════════════════════════════

SCENARIOS: list[Scenario] = []


def _s(scenario: Scenario) -> Scenario:
    """Register and return a scenario."""
    SCENARIOS.append(scenario)
    return scenario


# ── 1. Basic cabinets ─────────────────────────────────────────────────────────

_s(Scenario(
    name="standard_base_cabinet",
    prompt="Design a standard 600 mm wide, 720 mm tall, 550 mm deep base cabinet.",
    tags=["basic_cabinet"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550},
            label="basic 600mm base cabinet",
            assertions=[
                Assertion("exterior.width_mm",  Op.EQ, 600),
                Assertion("exterior.height_mm", Op.EQ, 720),
                Assertion("exterior.depth_mm",  Op.EQ, 550),
                Assertion("interior.width_mm",  Op.EQ, 564),   # 600 - 2*18
                Assertion("interior.depth_mm",  Op.LT, 550),
                Assertion("joinery",            Op.EQ, "dado_rabbet"),
                Assertion("panels.side_panel.qty", Op.EQ, 2),
                Assertion("panels.bottom_panel", Op.HAS_KEY, True),
                Assertion("panels.back_panel",   Op.HAS_KEY, True),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 720, "depth": 550},
            label="evaluate basic cabinet",
            assertions=[
                Assertion("summary.pass", Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="narrow_wall_cabinet",
    prompt="Design a narrow 300 mm wide wall cabinet, 600 mm tall, 300 mm deep.",
    tags=["basic_cabinet"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 300, "height": 600, "depth": 300},
            label="narrow wall cabinet",
            assertions=[
                Assertion("exterior.width_mm", Op.EQ, 300),
                Assertion("interior.width_mm", Op.EQ, 264),   # 300 - 2*18
            ],
        ),
    ],
))

_s(Scenario(
    name="tall_pantry_cabinet",
    prompt="Design a tall pantry cabinet: 600 mm wide, 2100 mm tall, 600 mm deep.",
    tags=["basic_cabinet"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 2100, "depth": 600},
            label="tall pantry",
            assertions=[
                Assertion("exterior.height_mm", Op.EQ, 2100),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 2100, "depth": 600},
            label="evaluate tall pantry",
            assertions=[
                Assertion("summary.pass", Op.IS_TRUE),
            ],
        ),
    ],
))


# ── 2. Drawers ────────────────────────────────────────────────────────────────

_s(Scenario(
    name="single_drawer_butt_joint",
    prompt="Design a drawer for a 560 mm opening, 150 mm tall, 500 mm deep. Use butt joints.",
    tags=["drawer", "joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width": 560,
                "opening_height": 150,
                "opening_depth": 500,
                "joinery_style": "butt",
            },
            label="butt-joint drawer",
            assertions=[
                Assertion("box_width_mm",  Op.LT, 560),
                Assertion("box_height_mm", Op.LT, 150),
                Assertion("box_depth_mm",  Op.GT, 0),
                Assertion("joinery.style", Op.EQ, "butt"),
                Assertion("slide.name",    Op.HAS_KEY, True),
            ],
        ),
    ],
))

_s(Scenario(
    name="qqq_drawer_18mm_stock",
    prompt=(
        "Design a QQQ drawer for a 500 mm opening, 200 mm tall, 450 mm deep. "
        "Use 18 mm side stock."
    ),
    tags=["drawer", "joinery"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width": 500,
                "opening_height": 200,
                "opening_depth": 450,
                "joinery_style": "qqq",
                "side_thickness": 18.0,
                "front_back_thickness": 18.0,
            },
            label="QQQ drawer 18 mm stock",
            assertions=[
                Assertion("joinery.style", Op.EQ, "qqq"),
                # QQQ: all cuts = thickness / 2 = 9.0
                Assertion("joinery.side_dado_depth_x_mm", Op.APPROX, 9.0),
                Assertion("joinery.side_dado_depth_y_mm", Op.APPROX, 9.0),
                Assertion("joinery.fb_channel_depth_x_mm", Op.APPROX, 9.0),
                Assertion("joinery.fb_channel_depth_y_mm", Op.APPROX, 9.0),
                Assertion("joinery.requires_true_thickness", Op.IS_TRUE),
            ],
        ),
    ],
))

_s(Scenario(
    name="drawer_lock_joint",
    prompt="Design a drawer-lock joint drawer for a 600 mm opening, 180 mm tall, 500 mm deep.",
    tags=["drawer", "joinery"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width": 600,
                "opening_height": 180,
                "opening_depth": 500,
                "joinery_style": "drawer_lock",
            },
            label="drawer-lock drawer",
            assertions=[
                Assertion("joinery.style", Op.EQ, "drawer_lock"),
                Assertion("joinery.requires_router_bit", Op.IS_TRUE),
                Assertion("joinery.lock_step_depth_x_mm", Op.GT, 0),
                Assertion("joinery.lock_step_depth_y_mm", Op.GT, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="half_lap_drawer",
    prompt="Design a half-lap drawer for a 450 mm opening, 120 mm tall, 400 mm deep.",
    tags=["drawer", "joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width": 450,
                "opening_height": 120,
                "opening_depth": 400,
                "joinery_style": "half_lap",
            },
            label="half-lap drawer",
            assertions=[
                Assertion("joinery.style", Op.EQ, "half_lap"),
                Assertion("joinery.side_dado_depth_x_mm", Op.GT, 0),
            ],
        ),
    ],
))

# Standard height snapping scenarios

_s(Scenario(
    name="standard_height_snap_6inch",
    prompt=(
        "Design a drawer for a 500 mm opening, 190 mm tall, 450 mm deep. "
        "Use standard industry box heights."
    ),
    tags=["drawer", "standard_height"],
    difficulty="basic",
    description=(
        "Opening 190 mm → raw = 190 - 14 (bottom clearance) - 12 (vertical gap) = 164 mm. "
        "164 mm fits a 6\" (152 mm) box; should snap to 152 mm."
    ),
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width": 500,
                "opening_height": 190,
                "opening_depth": 450,
                "use_standard_height": True,
            },
            label="snap to 6\" box height",
            assertions=[
                Assertion("standard_box_height_mm", Op.APPROX, 152.0),
                Assertion("box_height_mm",           Op.APPROX, 152.0),
                Assertion("box_height_raw_mm",        Op.GT,     152.0),
                Assertion("use_standard_height",      Op.IS_TRUE),
            ],
        ),
    ],
))

_s(Scenario(
    name="standard_height_snap_4inch",
    prompt=(
        "Design a small drawer for a 500 mm opening, 140 mm tall, 450 mm deep. "
        "Use standard industry box heights."
    ),
    tags=["drawer", "standard_height"],
    difficulty="basic",
    description=(
        "Opening 140 mm → raw = 140 - 14 - 12 = 114 mm. "
        "114 mm fits a 4\" (102 mm) box; should snap to 102 mm."
    ),
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width": 500,
                "opening_height": 140,
                "opening_depth": 450,
                "use_standard_height": True,
            },
            label="snap to 4\" box height",
            assertions=[
                Assertion("standard_box_height_mm", Op.APPROX, 102.0),
                Assertion("box_height_mm",           Op.APPROX, 102.0),
            ],
        ),
    ],
))

_s(Scenario(
    name="standard_height_opt_out",
    prompt=(
        "Design a drawer for a 500 mm opening, 190 mm tall, 450 mm deep. "
        "Use the exact computed height, not a standard size."
    ),
    tags=["drawer", "standard_height"],
    difficulty="basic",
    description=(
        "use_standard_height=False should return the raw height (164 mm for opening=190). "
        "The standard_box_height_mm field is still reported (152 mm) for reference."
    ),
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width": 500,
                "opening_height": 190,
                "opening_depth": 450,
                "use_standard_height": False,
            },
            label="exact computed height (no snap)",
            assertions=[
                Assertion("use_standard_height",     Op.IS_FALSE),
                # raw and actual box_height should both be 164 (190 - 14 - 12)
                Assertion("box_height_raw_mm",        Op.APPROX, 164.0),
                Assertion("box_height_mm",            Op.APPROX, 164.0),
                # standard height still reported for reference
                Assertion("standard_box_height_mm",  Op.APPROX, 152.0),
            ],
        ),
    ],
))

_s(Scenario(
    name="standard_height_exact_match",
    prompt=(
        "Design a drawer whose opening maps to exactly 203 mm (8\") of raw box height "
        "after clearances — confirm the snap lands exactly on the standard size."
    ),
    tags=["drawer", "standard_height"],
    difficulty="standard",
    description=(
        "opening=229 → raw = 229 - 14 - 12 = 203 mm exactly. "
        "Should snap to 203 mm (8\") with no reduction."
    ),
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width": 500,
                "opening_height": 229,   # 229 - 14 - 12 = 203 exactly
                "opening_depth": 450,
                "use_standard_height": True,
            },
            label="snap to 8\" exactly",
            assertions=[
                Assertion("standard_box_height_mm", Op.APPROX, 203.0),
                Assertion("box_height_mm",           Op.APPROX, 203.0),
                Assertion("box_height_raw_mm",        Op.APPROX, 203.0),
            ],
        ),
    ],
))


# ── 3. Doors ──────────────────────────────────────────────────────────────────

_s(Scenario(
    name="full_overlay_single_door",
    prompt="Design a single full-overlay door for a 450 mm wide, 700 mm tall opening.",
    tags=["door"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 450,
                "opening_height": 700,
                "num_doors": 1,
                "hinge_key": "blum_clip_top_110_full",
            },
            label="full overlay single door",
            assertions=[
                Assertion("overlay_type", Op.EQ, "full"),
                Assertion("overlay_mm",   Op.EQ, 16.0),
                # Full overlay single: door_width = opening + 2 * 16 = 482
                Assertion("door_width_mm", Op.EQ, 482.0),
                Assertion("door_height_mm", Op.LT, 700),
                Assertion("hinges_per_door", Op.GTE, 2),
                Assertion("hinge.cup_diameter_mm", Op.EQ, 35.0),
                Assertion("hinge.cup_boring_distance_mm", Op.EQ, 22.5),
            ],
        ),
    ],
))

_s(Scenario(
    name="half_overlay_single_door",
    prompt="Design a single half-overlay door for a 500 mm wide, 600 mm tall opening.",
    tags=["door"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 500,
                "opening_height": 600,
                "num_doors": 1,
                "hinge_key": "blum_clip_top_110_half",
            },
            label="half overlay single door",
            assertions=[
                Assertion("overlay_type", Op.EQ, "half"),
                Assertion("overlay_mm",   Op.EQ, 9.5),
                # Half overlay single: door_width = 500 + 2 * 9.5 = 519
                Assertion("door_width_mm", Op.APPROX, 519.0),
            ],
        ),
    ],
))

_s(Scenario(
    name="inset_single_door",
    prompt="Design an inset door for a 450 mm wide, 650 mm tall opening.",
    tags=["door"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 450,
                "opening_height": 650,
                "num_doors": 1,
                "hinge_key": "blum_clip_top_110_inset",
            },
            label="inset single door",
            assertions=[
                Assertion("overlay_type", Op.EQ, "inset"),
                # Inset single: door_width = opening - 2 * gap_side = 450 - 4 = 446
                Assertion("door_width_mm", Op.LT, 450),
                Assertion("door_width_mm", Op.GT, 440),
            ],
        ),
    ],
))

_s(Scenario(
    name="full_overlay_door_pair",
    prompt="Design a pair of full-overlay doors for a 900 mm wide, 700 mm tall opening.",
    tags=["door"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 900,
                "opening_height": 700,
                "num_doors": 2,
                "hinge_key": "blum_clip_top_110_full",
            },
            label="full overlay door pair",
            assertions=[
                Assertion("num_doors",    Op.EQ, 2),
                Assertion("total_hinges", Op.GTE, 4),
                # Pair: each door = opening/2 + overlay - gap/2 = 450 + 16 - 1 = 465
                Assertion("door_width_mm", Op.APPROX, 465.0),
            ],
        ),
    ],
))

_s(Scenario(
    name="blumotion_soft_close_door",
    prompt=(
        "Design a single full-overlay door with BLUMOTION soft-close hinges "
        "for a 500 mm wide, 700 mm tall opening."
    ),
    tags=["door"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 500,
                "opening_height": 700,
                "hinge_key": "blum_clip_top_blumotion_110_full",
            },
            label="BLUMOTION soft-close door",
            assertions=[
                Assertion("hinge.soft_close", Op.IS_TRUE),
                Assertion("hinge.part_number", Op.EQ, "71B3590"),
            ],
        ),
    ],
))

_s(Scenario(
    name="tall_door_needs_three_hinges",
    prompt="Design a full-overlay door for a 500 mm wide, 1800 mm tall opening.",
    tags=["door"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 500,
                "opening_height": 1800,
                "num_doors": 1,
                "hinge_key": "blum_clip_top_110_full",
            },
            label="tall door — 3 hinges expected",
            assertions=[
                Assertion("hinges_per_door", Op.GTE, 3),
                Assertion("hinge_positions_z_mm", Op.LEN_GTE, 3),
            ],
        ),
    ],
))


# ── 4. Joinery comparison ────────────────────────────────────────────────────

_s(Scenario(
    name="compare_joinery_12mm",
    prompt="Compare all drawer joinery styles for 12 mm stock.",
    tags=["joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="compare_joinery",
            args={"side_thickness": 12.0, "front_back_thickness": 12.0},
            label="compare joinery 12 mm",
            assertions=[
                Assertion("styles.butt",        Op.HAS_KEY, True),
                Assertion("styles.qqq",         Op.HAS_KEY, True),
                Assertion("styles.half_lap",    Op.HAS_KEY, True),
                Assertion("styles.drawer_lock", Op.HAS_KEY, True),
                Assertion("styles.qqq.side_dado_depth_x_mm", Op.APPROX, 6.0),
                Assertion("styles.butt.side_dado_depth_x_mm", Op.EQ, 0.0),
            ],
        ),
    ],
))

_s(Scenario(
    name="compare_joinery_18mm",
    prompt="Compare all drawer joinery styles for 18 mm stock.",
    tags=["joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="compare_joinery",
            args={"side_thickness": 18.0, "front_back_thickness": 18.0},
            label="compare joinery 18 mm",
            assertions=[
                Assertion("styles.qqq.side_dado_depth_x_mm", Op.APPROX, 9.0),
            ],
        ),
    ],
))


# ── 5. Hardware catalogue ─────────────────────────────────────────────────────

_s(Scenario(
    name="list_all_hardware",
    prompt="Show me all available drawer slides and hinges.",
    tags=["hardware"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="list_hardware",
            args={"category": "all"},
            label="list all hardware",
            assertions=[
                Assertion("slides", Op.HAS_KEY, True),
                Assertion("hinges", Op.HAS_KEY, True),
                Assertion("slides.blum_tandem_550h", Op.HAS_KEY, True),
                Assertion("hinges.blum_clip_top_110_full", Op.HAS_KEY, True),
                Assertion("hinges.blum_clip_top_110_inset", Op.HAS_KEY, True),
            ],
        ),
    ],
))

_s(Scenario(
    name="list_joinery_options",
    prompt="What joinery options are available?",
    tags=["joinery", "hardware"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="list_joinery_options",
            args={},
            label="list joinery options",
            assertions=[
                Assertion("drawer_joinery_styles.qqq",       Op.HAS_KEY, True),
                Assertion("carcass_joinery_methods.floating_tenon", Op.HAS_KEY, True),
                Assertion("domino_sizes.8x40",               Op.HAS_KEY, True),
                Assertion("domino_sizes.8x40.machine",       Op.EQ, "DF 500"),
            ],
        ),
    ],
))


# ── 6. Carcass joinery ────────────────────────────────────────────────────────

_s(Scenario(
    name="domino_carcass",
    prompt=(
        "Design a 600 mm base cabinet joined with Festool Domino floating tenons. "
        "Then evaluate it."
    ),
    tags=["basic_cabinet", "joinery"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "carcass_joinery": "floating_tenon",
            },
            label="Domino carcass cabinet",
            assertions=[
                Assertion("joinery", Op.EQ, "floating_tenon"),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "carcass_joinery": "floating_tenon",
            },
            label="evaluate Domino cabinet",
            assertions=[
                Assertion("summary.pass", Op.IS_TRUE),
            ],
        ),
    ],
))

_s(Scenario(
    name="pocket_screw_carcass",
    prompt="Design and evaluate a 450 mm base cabinet with pocket-screw joinery.",
    tags=["basic_cabinet", "joinery"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 450, "height": 720, "depth": 550,
                "carcass_joinery": "pocket_screw",
            },
            label="pocket-screw cabinet",
            assertions=[
                Assertion("joinery", Op.EQ, "pocket_screw"),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 450, "height": 720, "depth": 550,
                "carcass_joinery": "pocket_screw",
            },
            label="evaluate pocket-screw cabinet",
            assertions=[
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))


# ── 7. Cutlist generation ────────────────────────────────────────────────────

_s(Scenario(
    name="cutlist_basic",
    prompt="Generate a cutlist for a standard 600 mm base cabinet.",
    tags=["cutlist"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550, "format": "both"},
            label="basic cutlist",
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
                Assertion("cutlist_json", Op.HAS_KEY, True),
                Assertion("cutlist_csv",  Op.HAS_KEY, True),
                Assertion("cutlist_json.panels", Op.LEN_GTE, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="cutlist_custom_sheet",
    prompt="Generate a cutlist for a 900 mm cabinet using 5x5 Baltic birch sheets.",
    tags=["cutlist"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="generate_cutlist",
            args={
                "width": 900, "height": 720, "depth": 550,
                "sheet_length": 1525, "sheet_width": 1525,
                "format": "json",
            },
            label="cutlist custom sheet",
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
                Assertion("cutlist_json.panels", Op.LEN_GTE, 3),
            ],
        ),
    ],
))


# ── 8. Full kitchen scenarios ─────────────────────────────────────────────────

_s(Scenario(
    name="three_drawer_base_cabinet",
    prompt=(
        "Design a 600 mm base cabinet with three drawers: "
        "150 mm, 150 mm, and 350 mm (bottom up). "
        "Use QQQ joinery for the drawers and Domino for the carcass. "
        "Full-overlay BLUMOTION soft-close hinges."
    ),
    tags=["kitchen", "drawer", "joinery"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[150, "drawer"], [150, "drawer"], [350, "drawer"]],
                "carcass_joinery": "floating_tenon",
            },
            label="3-drawer base cabinet",
            assertions=[
                Assertion("opening_stack", Op.LEN_EQ, 3),
                Assertion("opening_stack.0.type", Op.EQ, "drawer"),
                Assertion("opening_stack.0.height_mm", Op.EQ, 150),
                Assertion("joinery", Op.EQ, "floating_tenon"),
            ],
        ),
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width": 564, "opening_height": 150, "opening_depth": 544,
                "joinery_style": "qqq", "side_thickness": 15.0,
            },
            label="top drawer QQQ",
            assertions=[
                Assertion("joinery.style", Op.EQ, "qqq"),
                Assertion("box_width_mm",  Op.LT, 564),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[150, "drawer"], [150, "drawer"], [350, "drawer"]],
                "carcass_joinery": "floating_tenon",
            },
            label="evaluate 3-drawer cabinet",
            assertions=[
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={
                "width": 600, "height": 720, "depth": 550,
                "format": "both",
            },
            label="cutlist for 3-drawer",
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="drawer_plus_door_cabinet",
    prompt=(
        "Design a 600 mm cabinet with one 150 mm drawer on top and a single "
        "full-overlay door below (500 mm opening)."
    ),
    tags=["kitchen", "drawer", "door"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[500, "door"], [150, "drawer"]],
            },
            label="drawer + door cabinet",
            assertions=[
                Assertion("opening_stack", Op.LEN_EQ, 2),
            ],
        ),
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width": 564, "opening_height": 150, "opening_depth": 544,
            },
            label="top drawer",
            assertions=[
                Assertion("box_width_mm", Op.GT, 0),
            ],
        ),
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 564, "opening_height": 500,
                "hinge_key": "blum_clip_top_110_full",
            },
            label="bottom door",
            assertions=[
                Assertion("door_width_mm",  Op.GT, 564),  # full overlay is wider
                Assertion("door_height_mm", Op.LT, 500),
                Assertion("hinges_per_door", Op.GTE, 2),
            ],
        ),
    ],
))


# ── 9. Evaluation edge cases (designs that SHOULD produce issues) ────────────

_s(Scenario(
    name="overflow_drawer_stack",
    prompt="Design a cabinet where the drawer stack exceeds the interior height.",
    tags=["evaluation", "edge_case"],
    difficulty="advanced",
    description="drawer_config totals 900 mm but cabinet interior ≈ 696 mm",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[300, "drawer"], [300, "drawer"], [300, "drawer"]],
            },
            label="overflowing drawer stack",
            assertions=[
                Assertion("summary.pass",   Op.IS_FALSE),
                Assertion("summary.errors",  Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="thin_side_panels",
    prompt="Design a cabinet with 6 mm side panels and Domino joinery — should warn.",
    tags=["evaluation", "edge_case"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "side_thickness": 6.0,
                "carcass_joinery": "floating_tenon",
            },
            label="thin panels + Domino",
            assertions=[
                Assertion("summary.errors", Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="valid_biscuit_carcass",
    prompt="Design and evaluate a biscuit-jointed 600 mm base cabinet.",
    tags=["joinery", "evaluation"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "carcass_joinery": "biscuit",
            },
            label="biscuit carcass eval",
            assertions=[
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="valid_dowel_carcass",
    prompt="Design and evaluate a dowel-jointed 600 mm base cabinet.",
    tags=["joinery", "evaluation"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "carcass_joinery": "dowel",
            },
            label="dowel carcass eval",
            assertions=[
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))


# ── 10. Wide / unusual dimensions ─────────────────────────────────────────────

_s(Scenario(
    name="extra_wide_cabinet",
    prompt="Design a 1200 mm wide base cabinet with a door pair.",
    tags=["basic_cabinet", "door", "edge_case"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 1200, "height": 720, "depth": 550,
                "drawer_config": [[650, "door_pair"]],
            },
            label="1200 mm cabinet",
            assertions=[
                Assertion("exterior.width_mm", Op.EQ, 1200),
                Assertion("opening_stack.0.type", Op.EQ, "door_pair"),
            ],
        ),
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 1164, "opening_height": 650,
                "num_doors": 2,
                "hinge_key": "blum_clip_top_110_full",
            },
            label="door pair for wide cabinet",
            assertions=[
                Assertion("num_doors",    Op.EQ, 2),
                Assertion("total_hinges", Op.GTE, 4),
            ],
        ),
    ],
))

_s(Scenario(
    name="shallow_cabinet",
    prompt="Design a shallow 250 mm deep wall cabinet, 600 mm wide, 400 mm tall.",
    tags=["basic_cabinet", "edge_case"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 400, "depth": 250},
            label="shallow wall cabinet",
            assertions=[
                Assertion("exterior.depth_mm", Op.EQ, 250),
                Assertion("interior.depth_mm", Op.LT, 250),
            ],
        ),
    ],
))


# ── 11. Multi-step kitchen workflow ──────────────────────────────────────────

_s(Scenario(
    name="full_kitchen_workflow",
    prompt=(
        "I need a 900 mm wide, 750 mm tall base cabinet with two 150 mm drawers "
        "and a 400 mm door opening. Use QQQ drawers, Domino carcass, BLUMOTION "
        "full-overlay hinges. Generate the full cutlist."
    ),
    tags=["kitchen"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="list_hardware",
            args={"category": "all"},
            label="check available hardware",
            assertions=[
                Assertion("slides", Op.HAS_KEY, True),
                Assertion("hinges", Op.HAS_KEY, True),
            ],
        ),
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 900, "height": 750, "depth": 550,
                "drawer_config": [[400, "door"], [150, "drawer"], [150, "drawer"]],
                "carcass_joinery": "floating_tenon",
                "door_hinge": "blum_clip_top_blumotion_110_full",
            },
            label="900 mm kitchen base",
            assertions=[
                Assertion("opening_stack", Op.LEN_EQ, 3),
                Assertion("joinery", Op.EQ, "floating_tenon"),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 900, "height": 750, "depth": 550,
                "drawer_config": [[400, "door"], [150, "drawer"], [150, "drawer"]],
                "carcass_joinery": "floating_tenon",
            },
            label="evaluate kitchen base",
            assertions=[
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={
                "width": 900, "height": 750, "depth": 550,
                "format": "both",
            },
            label="kitchen cutlist",
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
                Assertion("cutlist_json.panels", Op.LEN_GTE, 3),
            ],
        ),
    ],
))


# ── 12. Drawer carcass clearance checks ──────────────────────────────────────

_s(Scenario(
    name="drawer_carcass_clearances_pass",
    prompt="Evaluate a standard 600 mm cabinet with three 150 mm drawers — clearances should all pass.",
    tags=["evaluation", "drawer"],
    difficulty="standard",
    description="Standard proportions: interior 564 mm wide, 541 mm deep, drawers 57 mm box height",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[150, "drawer"], [150, "drawer"], [150, "drawer"]],
            },
            label="standard drawers in 600 mm cabinet",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="drawer_carcass_clearances_narrow_cabinet",
    prompt="Evaluate a 100 mm wide cabinet with a drawer — should fail because the cabinet is too narrow for the slide.",
    tags=["evaluation", "drawer", "edge_case"],
    difficulty="advanced",
    description="interior_width = 100 - 36 = 64 mm; Blum Tandem needs 42 mm side clearance total → box_width < 22 mm",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 100, "height": 720, "depth": 550,
                "drawer_config": [[150, "drawer"]],
            },
            label="too-narrow cabinet for slide",
            assertions=[
                Assertion("summary.pass",   Op.IS_FALSE),
                Assertion("summary.errors", Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="drawer_carcass_clearances_short_opening",
    prompt="Evaluate a cabinet with a 60 mm drawer opening — too short for Blum Tandem 550H.",
    tags=["evaluation", "drawer", "edge_case"],
    difficulty="advanced",
    description="box_height = 60 - 3 = 57 mm; Blum min is 68 mm",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[60, "drawer"]],
            },
            label="opening height below slide minimum",
            assertions=[
                Assertion("summary.pass",   Op.IS_FALSE),
                Assertion("summary.errors", Op.GTE, 1),
            ],
        ),
    ],
))


# ── 8. Presets ────────────────────────────────────────────────────────────────

_s(Scenario(
    name="list_all_presets",
    prompt="Show me all the available cabinet presets.",
    tags=["presets"],
    difficulty="basic",
    description="list_presets with no filters should return all 9 presets.",
    tool_calls=[
        ToolCall(
            tool="list_presets",
            args={},
            label="list all presets",
            assertions=[
                Assertion("count",   Op.GTE, 9),
                Assertion("presets", Op.LEN_GTE, 9),
            ],
        ),
    ],
))

_s(Scenario(
    name="list_kitchen_presets",
    prompt="Show me only kitchen presets.",
    tags=["presets", "kitchen"],
    difficulty="basic",
    description="Filtering by category=kitchen should return at least 3 kitchen presets.",
    tool_calls=[
        ToolCall(
            tool="list_presets",
            args={"category": "kitchen"},
            label="kitchen presets only",
            assertions=[
                Assertion("count",   Op.GTE, 3),
                Assertion("presets", Op.LEN_GTE, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="apply_kitchen_base_3_drawer",
    prompt="Load the kitchen_base_3_drawer preset and check it's valid.",
    tags=["presets", "kitchen", "drawer"],
    difficulty="basic",
    description=(
        "apply_preset should return a 600×720×550 config with 3 drawers summing to interior height."
    ),
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "kitchen_base_3_drawer"},
            label="load kitchen 3-drawer preset",
            assertions=[
                Assertion("preset_name",    Op.EQ, "kitchen_base_3_drawer"),
                Assertion("config.width",   Op.EQ, 600),
                Assertion("config.height",  Op.EQ, 720),
                Assertion("config.depth",   Op.EQ, 550),
                Assertion("interior_height_mm",  Op.EQ, 684),
                Assertion("opening_stack_total_mm", Op.EQ, 684),
                Assertion("opening_stack_matches_interior", Op.IS_TRUE),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[300, "drawer"], [192, "drawer"], [192, "drawer"]],
                "drawer_slide": "blum_tandem_550h",
            },
            label="evaluate preset config",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="apply_preset_with_overrides",
    prompt=(
        "Load the kitchen_base_3_drawer preset but make it 750 mm wide "
        "and use Blum Movento 760H slides."
    ),
    tags=["presets", "kitchen", "drawer"],
    difficulty="standard",
    description=(
        "apply_preset with overrides: width→750, drawer_slide→blum_movento_760h. "
        "Config should reflect the overrides; stack still matches interior height."
    ),
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={
                "name": "kitchen_base_3_drawer",
                "overrides": {"width": 750, "drawer_slide": "blum_movento_760h"},
            },
            label="preset + overrides",
            assertions=[
                Assertion("config.width",        Op.EQ, 750),
                Assertion("config.drawer_slide",  Op.EQ, "blum_movento_760h"),
                Assertion("config.height",        Op.EQ, 720),
                Assertion("opening_stack_matches_interior", Op.IS_TRUE),
            ],
        ),
    ],
))

_s(Scenario(
    name="apply_preset_height_override_warns",
    prompt=(
        "Load the workshop_tool_chest preset but change its height to 1000 mm — "
        "the opening stack should no longer match."
    ),
    tags=["presets", "workshop", "edge_case"],
    difficulty="standard",
    description=(
        "Changing height without updating drawer_config should trigger "
        "opening_stack_matches_interior=false and include a warning message."
    ),
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={
                "name": "workshop_tool_chest",
                "overrides": {"height": 1000},
            },
            label="height override without stack update",
            assertions=[
                Assertion("config.height", Op.EQ, 1000),
                Assertion("opening_stack_matches_interior", Op.IS_FALSE),
                Assertion("opening_stack_warning", Op.HAS_KEY, True),
            ],
        ),
    ],
))

_s(Scenario(
    name="apply_preset_unknown_name",
    prompt="Try to load a preset called 'nonexistent_preset'.",
    tags=["presets", "edge_case"],
    difficulty="basic",
    description="apply_preset with an invalid name should return an ERROR response, not crash.",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "nonexistent_preset"},
            label="unknown preset name",
            assertions=[
                # Handler returns JSON {error: "...", available: [...]}
                Assertion("error",     Op.HAS_KEY, True),
                Assertion("available", Op.HAS_KEY, True),
            ],
        ),
    ],
))

_s(Scenario(
    name="apply_workshop_tool_chest",
    prompt="Load the workshop tool chest preset and confirm heavy-duty slides and pocket screw joinery.",
    tags=["presets", "workshop", "drawer"],
    difficulty="standard",
    description="workshop_tool_chest: 6 equal drawers, Movento 769 slides, pocket screw carcass.",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "workshop_tool_chest"},
            label="load workshop tool chest",
            assertions=[
                Assertion("preset_name",         Op.EQ, "workshop_tool_chest"),
                Assertion("config.width",         Op.EQ, 600),
                Assertion("config.height",        Op.EQ, 900),
                Assertion("config.drawer_slide",  Op.EQ, "blum_movento_769"),
                Assertion("config.carcass_joinery", Op.EQ, "pocket_screw"),
                Assertion("opening_stack_matches_interior", Op.IS_TRUE),
            ],
        ),
    ],
))


# ── 9. Living room / foyer presets ────────────────────────────────────────────

_s(Scenario(
    name="list_living_room_presets",
    prompt="Show me presets for living room furniture.",
    tags=["presets", "living_room"],
    difficulty="basic",
    description="Filtering by category=living_room should return all 5 living room presets.",
    tool_calls=[
        ToolCall(
            tool="list_presets",
            args={"category": "living_room"},
            label="living_room presets only",
            assertions=[
                Assertion("count",   Op.GTE, 5),
                Assertion("presets", Op.LEN_GTE, 5),
            ],
        ),
    ],
))

_s(Scenario(
    name="apply_foyer_console_2_drawer",
    prompt="Load the foyer_console_2_drawer preset and check dimensions and stack.",
    tags=["presets", "living_room"],
    difficulty="basic",
    description=(
        "foyer_console_2_drawer: 1200×800×350, interior_h=764, "
        "open shelf + 2×100 mm drawers = 764."
    ),
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "foyer_console_2_drawer"},
            label="load foyer console preset",
            assertions=[
                Assertion("preset_name",    Op.EQ, "foyer_console_2_drawer"),
                Assertion("config.width",   Op.EQ, 1200),
                Assertion("config.height",  Op.EQ, 800),
                Assertion("config.depth",   Op.EQ, 350),
                Assertion("interior_height_mm",              Op.EQ, 764),
                Assertion("opening_stack_total_mm",          Op.EQ, 764),
                Assertion("opening_stack_matches_interior",  Op.IS_TRUE),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 1200, "height": 800, "depth": 350,
                "drawer_config": [[564, "open"], [100, "drawer"], [100, "drawer"]],
                "drawer_slide": "blum_tandem_550h",
            },
            label="evaluate foyer console",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="apply_living_room_credenza",
    prompt="Load the living_room_credenza preset — check it has full-extension slides, soft-close hinges, and adj shelf holes.",
    tags=["presets", "living_room"],
    difficulty="standard",
    description=(
        "living_room_credenza: 1600×800×450, door pair below + 2 frieze drawers, "
        "Tandem+ slides, BLUMOTION hinges, adj_shelf_holes=True."
    ),
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "living_room_credenza"},
            label="load credenza preset",
            assertions=[
                Assertion("preset_name",              Op.EQ, "living_room_credenza"),
                Assertion("config.width",              Op.EQ, 1600),
                Assertion("config.depth",              Op.EQ, 450),
                Assertion("config.drawer_slide",       Op.EQ, "blum_tandem_plus_563h"),
                Assertion("config.door_hinge",         Op.EQ, "blum_clip_top_blumotion_110_full"),
                Assertion("config.adj_shelf_holes",    Op.IS_TRUE),
                Assertion("opening_stack_matches_interior", Op.IS_TRUE),
            ],
        ),
    ],
))

_s(Scenario(
    name="apply_living_room_sideboard",
    prompt="Load the living_room_sideboard preset and verify it passes evaluation.",
    tags=["presets", "living_room"],
    difficulty="standard",
    description=(
        "living_room_sideboard: 1800×900×500, door pair + 2 drawers, "
        "interior_h=864, stack=864."
    ),
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "living_room_sideboard"},
            label="load sideboard preset",
            assertions=[
                Assertion("preset_name",   Op.EQ, "living_room_sideboard"),
                Assertion("config.width",  Op.EQ, 1800),
                Assertion("config.height", Op.EQ, 900),
                Assertion("interior_height_mm",             Op.EQ, 864),
                Assertion("opening_stack_total_mm",         Op.EQ, 864),
                Assertion("opening_stack_matches_interior", Op.IS_TRUE),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 1800, "height": 900, "depth": 500,
                "drawer_config": [[614, "door_pair"], [125, "drawer"], [125, "drawer"]],
                "drawer_slide": "blum_tandem_plus_563h",
            },
            label="evaluate sideboard",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="apply_media_console",
    prompt="Load the media_console preset — check it's low-profile with a door pair and open shelf.",
    tags=["presets", "living_room"],
    difficulty="basic",
    description=(
        "media_console: 1800×600×450, door pair (264) + open shelf (300) = 564 interior."
    ),
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "media_console"},
            label="load media console preset",
            assertions=[
                Assertion("preset_name",   Op.EQ, "media_console"),
                Assertion("config.width",  Op.EQ, 1800),
                Assertion("config.height", Op.EQ, 600),
                Assertion("interior_height_mm",             Op.EQ, 564),
                Assertion("opening_stack_total_mm",         Op.EQ, 564),
                Assertion("opening_stack_matches_interior", Op.IS_TRUE),
            ],
        ),
    ],
))


# ── 10. Auto-fix & describe workflow ──────────────────────────────────────────

SCENARIOS.append(Scenario(
    name="auto_fix_oversized_stack",
    prompt="Fix a cabinet where the opening stack exceeds interior height.",
    tags=["auto_fix", "workflow"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="auto_fix_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[300, "drawer"], [300, "drawer"], [300, "drawer"]],
            },
            assertions=[
                Assertion("fixed",        Op.IS_TRUE),
                Assertion("clean",        Op.IS_TRUE),
                Assertion("errors_before", Op.GT, 0),
                Assertion("errors_after",  Op.EQ, 0),
                Assertion("changes",       Op.LEN_GTE, 1),
                Assertion("config.drawer_config", Op.LEN_EQ, 3),
            ],
        ),
    ],
))

SCENARIOS.append(Scenario(
    name="auto_fix_undersized_stack",
    prompt="Auto-fix on a cabinet where the opening stack is shorter than interior — no error, so no fix needed.",
    tags=["auto_fix", "workflow"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="auto_fix_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[200, "drawer"], [200, "drawer"]],
            },
            assertions=[
                # Shortfall is a valid design (open space at top), not an error.
                Assertion("errors_before", Op.EQ, 0),
                Assertion("errors_after",  Op.EQ, 0),
                Assertion("clean",         Op.IS_TRUE),
                Assertion("changes",       Op.LEN_EQ, 0),
            ],
        ),
    ],
))

SCENARIOS.append(Scenario(
    name="auto_fix_clean_config",
    prompt="Run auto-fix on a config that already passes evaluation.",
    tags=["auto_fix", "workflow"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="auto_fix_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[342, "drawer"], [342, "drawer"]],
            },
            assertions=[
                Assertion("errors_before", Op.EQ, 0),
                Assertion("errors_after",  Op.EQ, 0),
                Assertion("changes",       Op.LEN_EQ, 0),
                Assertion("clean",         Op.IS_TRUE),
            ],
        ),
    ],
))

SCENARIOS.append(Scenario(
    name="describe_basic_cabinet",
    prompt="Describe a simple 600×720×550 cabinet with two drawers.",
    tags=["describe", "workflow"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="describe_design",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[342, "drawer"], [342, "drawer"]],
            },
            assertions=[
                Assertion("prose",      Op.CONTAINS, "600 mm"),
                Assertion("prose",      Op.CONTAINS, "720 mm"),
                Assertion("prose",      Op.CONTAINS, "drawer"),
                Assertion("dimensions", Op.HAS_KEY,  "exterior"),
                Assertion("dimensions", Op.HAS_KEY,  "interior"),
                Assertion("openings.counts.drawer", Op.EQ, 2),
                Assertion("openings.stack_fills_interior", Op.IS_TRUE),
            ],
        ),
    ],
))

SCENARIOS.append(Scenario(
    name="describe_credenza_preset",
    prompt="Describe the living room credenza preset.",
    tags=["describe", "workflow", "living_room"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "living_room_credenza"},
            assertions=[
                Assertion("config", Op.HAS_KEY, "width"),
            ],
        ),
        ToolCall(
            tool="describe_design",
            args={
                "width": 1600, "height": 800, "depth": 450,
                "drawer_config": [[564, "door_pair"], [100, "drawer"], [100, "drawer"]],
                "drawer_slide": "blum_tandem_plus_566h",
                "door_hinge": "blum_clip_top_110_full",
                "adj_shelf_holes": True,
            },
            assertions=[
                Assertion("prose",      Op.CONTAINS, "1600 mm"),
                Assertion("prose",      Op.CONTAINS, "door"),
                Assertion("prose",      Op.CONTAINS, "drawer"),
                Assertion("hardware",   Op.HAS_KEY,  "drawer_slide"),
                Assertion("hardware",   Op.HAS_KEY,  "door_hinge"),
                Assertion("materials.adj_shelf_holes", Op.IS_TRUE),
            ],
        ),
    ],
))

SCENARIOS.append(Scenario(
    name="full_workflow_design_eval_fix_describe",
    prompt="Full workflow: design → evaluate → auto-fix → describe a broken config.",
    tags=["workflow", "auto_fix", "describe"],
    difficulty="advanced",
    tool_calls=[
        # Step 1: Design a cabinet with an oversized stack
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 900, "height": 720, "depth": 550,
                "drawer_config": [[200, "door_pair"], [200, "drawer"], [200, "drawer"], [200, "drawer"]],
            },
            assertions=[
                Assertion("opening_stack", Op.LEN_EQ, 4),
            ],
        ),
        # Step 2: Evaluate — should have errors (800 > 684 interior)
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 900, "height": 720, "depth": 550,
                "drawer_config": [[200, "door_pair"], [200, "drawer"], [200, "drawer"], [200, "drawer"]],
            },
            assertions=[
                Assertion("summary.errors", Op.GT, 0),
                Assertion("summary.pass",   Op.IS_FALSE),
            ],
        ),
        # Step 3: Auto-fix
        ToolCall(
            tool="auto_fix_cabinet",
            args={
                "width": 900, "height": 720, "depth": 550,
                "drawer_config": [[200, "door_pair"], [200, "drawer"], [200, "drawer"], [200, "drawer"]],
            },
            assertions=[
                Assertion("fixed", Op.IS_TRUE),
                Assertion("clean", Op.IS_TRUE),
                Assertion("config.drawer_config", Op.LEN_EQ, 4),
            ],
        ),
        # Step 4: Describe the fixed config (use the known-good rebalanced values)
        # We assert on the describe call using the original dimensions since
        # auto_fix only changes drawer_config; the tool call uses the original
        # envelope and the auto-fix-corrected stack will have already filled interior.
        # For simplicity we call describe on the *original* envelope with the
        # auto-fix rebalanced stack; the test just needs prose output.
        ToolCall(
            tool="describe_design",
            args={
                "width": 900, "height": 720, "depth": 550,
                "drawer_config": [[171, "door_pair"], [171, "drawer"], [171, "drawer"], [171, "drawer"]],
            },
            assertions=[
                Assertion("prose",      Op.CONTAINS, "900 mm"),
                Assertion("prose",      Op.CONTAINS, "drawer"),
                Assertion("openings.stack_fills_interior", Op.IS_TRUE),
            ],
        ),
    ],
))


# ── 13. Legs / feet ──────────────────────────────────────────────────────────

_s(Scenario(
    name="legs_default_richelieu",
    prompt="Add legs to my 600 mm wide, 550 mm deep base cabinet using the default Richelieu hardware.",
    tags=["legs", "hardware"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_legs",
            args={"cabinet_width": 600, "cabinet_depth": 550},
            label="default 4-corner Richelieu legs",
            assertions=[
                Assertion("leg.part_number",  Op.EQ,    "176138106"),
                Assertion("leg.height_mm",    Op.APPROX, 100.0),
                Assertion("count",            Op.EQ,     4),
                Assertion("pattern",          Op.EQ,     "corners"),
                Assertion("total_height_mm",  Op.APPROX, 100.0),
                Assertion("placement_mm",     Op.LEN_EQ, 4),
            ],
        ),
    ],
))

_s(Scenario(
    name="legs_load_check",
    prompt=(
        "I have a 900 mm wide cabinet with an estimated total weight of 80 kg. "
        "Check if 4 Richelieu legs can handle the load."
    ),
    tags=["legs", "hardware"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_legs",
            args={
                "cabinet_width": 900,
                "cabinet_depth": 550,
                "cabinet_weight_kg": 80.0,
            },
            label="load check 80 kg / 4 legs",
            assertions=[
                Assertion("load_per_leg_kg", Op.APPROX, 20.0),
                Assertion("load_check",      Op.HAS_KEY, True),
                # 20 kg per leg vs 50 kg capacity — should be well within limits
                Assertion("leg.load_capacity_kg", Op.GTE, 20.0),
            ],
        ),
    ],
))

_s(Scenario(
    name="legs_corners_and_midspan",
    prompt="Add 6 legs to a wide 1200 mm cabinet using the corners-and-midspan pattern.",
    tags=["legs", "hardware"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_legs",
            args={
                "cabinet_width": 1200,
                "cabinet_depth": 600,
                "leg_pattern": "corners_and_midspan",
                "count": 6,
            },
            label="6-leg corners-and-midspan",
            assertions=[
                Assertion("count",        Op.EQ,     6),
                Assertion("pattern",      Op.EQ,     "corners_and_midspan"),
                Assertion("placement_mm", Op.LEN_EQ, 6),
            ],
        ),
    ],
))

_s(Scenario(
    name="legs_list_hardware_includes_legs",
    prompt="Show me all available leg hardware.",
    tags=["legs", "hardware"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="list_hardware",
            args={"category": "legs"},
            label="list leg hardware",
            assertions=[
                Assertion("legs",                        Op.HAS_KEY, True),
                Assertion("legs.richelieu_176138106",     Op.HAS_KEY, True),
                Assertion("legs.richelieu_adjustable_40mm", Op.HAS_KEY, True),
            ],
        ),
    ],
))


# ── 14. Multi-column cabinets ─────────────────────────────────────────────────

_s(Scenario(
    name="multi_column_drawers_and_door",
    prompt=(
        "Design a 900 mm wide, 720 mm tall, 550 mm deep cabinet with two columns: "
        "a left column of three equal drawers and a right column with a single door."
    ),
    tags=["multi_column"],
    difficulty="standard",
    description=(
        "interior_width = 900 - 2×18 = 864 mm. "
        "Left column 432 mm (3 drawers × 228 mm). Right column 432 mm (1 door × 684 mm). "
        "Column widths sum = 864 mm = interior_width."
    ),
    tool_calls=[
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 900, "height": 720, "depth": 550,
                "columns": [
                    {"width_mm": 432, "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
                    {"width_mm": 432, "drawer_config": [[684, "door"]]},
                ],
            },
            label="2-column drawers+door",
            assertions=[
                Assertion("column_count",          Op.EQ,     2),
                Assertion("columns_fill_interior", Op.IS_TRUE),
                Assertion("column_widths_sum_mm",  Op.APPROX, 864.0),
                Assertion("interior_width_mm",     Op.APPROX, 864.0),
                Assertion("columns",               Op.LEN_EQ, 2),
            ],
        ),
    ],
))

_s(Scenario(
    name="multi_column_width_mismatch_error",
    prompt="Verify that column widths that don't add up produce a validation error.",
    tags=["multi_column", "evaluation"],
    difficulty="standard",
    description=(
        "Cabinet interior = 864 mm but columns sum to 500 mm — evaluator must flag error."
    ),
    tool_calls=[
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 900, "height": 720, "depth": 550,
                "columns": [
                    {"width_mm": 250, "drawer_config": [[684, "drawer"]]},
                    {"width_mm": 250, "drawer_config": [[684, "door"]]},
                ],
            },
            label="columns don't fill interior",
            assertions=[
                # The tool itself returns the mismatch flag
                Assertion("columns_fill_interior", Op.IS_FALSE),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 900, "height": 720, "depth": 550,
                "columns": [
                    {"width_mm": 250, "drawer_config": [[684, "drawer"]]},
                    {"width_mm": 250, "drawer_config": [[684, "door"]]},
                ],
            },
            label="evaluator flags column width error",
            assertions=[
                Assertion("summary", Op.HAS_ERROR),
            ],
        ),
    ],
))

_s(Scenario(
    name="multi_column_three_column_dresser",
    prompt=(
        "Design a 1200 mm wide, 900 mm tall, 500 mm deep dresser with three equal columns "
        "of drawers."
    ),
    tags=["multi_column"],
    difficulty="advanced",
    description=(
        "interior_width = 1200 - 36 = 1164 mm. "
        "Three equal columns = 388 mm each. Each column: 4 drawers × 216 mm = 864 mm interior."
    ),
    tool_calls=[
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 1200, "height": 900, "depth": 500,
                "columns": [
                    {"width_mm": 388, "drawer_config": [[216, "drawer"], [216, "drawer"], [216, "drawer"], [216, "drawer"]]},
                    {"width_mm": 388, "drawer_config": [[216, "drawer"], [216, "drawer"], [216, "drawer"], [216, "drawer"]]},
                    {"width_mm": 388, "drawer_config": [[216, "drawer"], [216, "drawer"], [216, "drawer"], [216, "drawer"]]},
                ],
            },
            label="3-column dresser",
            assertions=[
                Assertion("column_count",          Op.EQ,     3),
                Assertion("columns_fill_interior", Op.IS_TRUE),
                Assertion("panels.column_divider.qty", Op.EQ, 2),
            ],
        ),
    ],
))


# ─── Proportion suggestions ───────────────────────────────────────────────────

_s(Scenario(
    name="suggest_proportions_drawers_only",
    prompt="I'm designing a 900 mm tall sideboard with 5 drawers. Show me how all four proportion presets would distribute the drawer heights.",
    tags=["proportions"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 1220, "height": 900, "depth": 457, "num_drawers": 5},
            label="5-drawer comparison, all presets",
            assertions=[
                Assertion("interior_height_mm",           Op.EQ,      864.0),
                Assertion("drawer_suggestions",           Op.LEN_EQ,  4),
                Assertion("drawer_suggestions[0].viable", Op.IS_TRUE),
                Assertion("drawer_suggestions[1].viable", Op.IS_TRUE),
                Assertion("drawer_suggestions[2].viable", Op.IS_TRUE),
                Assertion("drawer_suggestions[3].viable", Op.IS_FALSE),
                Assertion("drawer_suggestions[3].preset", Op.EQ,      "golden"),
            ],
        ),
    ],
))

_s(Scenario(
    name="suggest_proportions_columns_only",
    prompt="I want 3 columns in my 1220 mm sideboard with a wider centre. Show me how the proportion presets divide the columns.",
    tags=["proportions"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 1220, "height": 900, "depth": 457, "num_columns": 3, "wide_index": 1},
            label="3-column comparison, wide centre, all presets",
            assertions=[
                Assertion("interior_width_mm",                  Op.EQ,      1184.0),
                Assertion("column_suggestions",                 Op.LEN_EQ,  4),
                Assertion("column_suggestions[0].widths_mm",    Op.LEN_EQ,  3),
                Assertion("column_suggestions[3].widths_mm",    Op.LEN_EQ,  3),
                Assertion("column_suggestions[3].wide_column_mm",   Op.GT,  400.0),
                Assertion("column_suggestions[3].narrow_column_mm", Op.LT,  400.0),
            ],
        ),
    ],
))

_s(Scenario(
    name="suggest_proportions_both",
    prompt="Compare proportion presets for a 3-column, 4-drawer sideboard.",
    tags=["proportions"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={
                "width": 1220, "height": 900, "depth": 457,
                "num_drawers": 4, "num_columns": 3, "wide_index": 1,
            },
            label="both drawer and column suggestions present",
            assertions=[
                Assertion("drawer_suggestions",           Op.LEN_EQ, 4),
                Assertion("column_suggestions",           Op.LEN_EQ, 4),
                Assertion("drawer_suggestions[0].viable", Op.IS_TRUE),
                Assertion("drawer_suggestions[3].viable", Op.IS_TRUE),
            ],
        ),
    ],
))


# ─── Index helpers ────────────────────────────────────────────────────────────

def scenarios_by_tag(tag: str) -> list[Scenario]:
    return [s for s in SCENARIOS if tag in s.tags]

def scenarios_by_difficulty(difficulty: str) -> list[Scenario]:
    return [s for s in SCENARIOS if s.difficulty == difficulty]

def scenario_by_name(name: str) -> Scenario:
    for s in SCENARIOS:
        if s.name == name:
            return s
    raise KeyError(f"No scenario named '{name}'. Available: {[s.name for s in SCENARIOS]}")

ALL_TAGS = sorted({tag for s in SCENARIOS for tag in s.tags})
