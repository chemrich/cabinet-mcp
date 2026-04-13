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
        "I need a 900 mm base cabinet with two 150 mm drawers and a 400 mm door "
        "opening. Use QQQ drawers, Domino carcass, BLUMOTION full-overlay hinges. "
        "Generate the full cutlist."
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
                "width": 900, "height": 720, "depth": 550,
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
                "width": 900, "height": 720, "depth": 550,
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
                "width": 900, "height": 720, "depth": 550,
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
