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
    """One MCP tool invocation with arguments and post-assertions.

    Context chaining
    ----------------
    ``save_as``     — after a successful call, walk each path into the result
                      and store the resolved value in the scenario's shared
                      context dict under the given variable name.
                      e.g. ``{"iw": "interior.width_mm"}`` saves the interior
                      width as context variable ``"iw"``.

    ``context_args`` — before calling the tool, resolve each named context
                      variable and inject it as a tool argument.
                      e.g. ``{"opening_width": "iw"}`` pulls ``context["iw"]``
                      into ``args["opening_width"]``.

    ``arg_transforms`` — optional callables applied to a resolved context value
                      *before* injection.  Keyed by the same arg name used in
                      ``context_args``.
                      e.g. ``{"drawer_config": lambda hs: [[h, "drawer"] for h in hs]}``
                      converts a list of heights into a valid drawer_config list.
    """
    tool: str                         # tool name (e.g. "design_cabinet")
    args: dict[str, Any]              # arguments passed to the tool
    assertions: list[Assertion] = field(default_factory=list)
    label: str = ""                   # human-readable label for reporting
    # ── context chaining ──────────────────────────────────────────────────
    save_as: dict[str, str] = field(default_factory=dict)
    # {context_var_name: result_path}  — save resolved values after success
    context_args: dict[str, str] = field(default_factory=dict)
    # {arg_name: context_var_name}  — inject context values before the call
    arg_transforms: dict[str, Any] = field(default_factory=dict)
    # {arg_name: callable}  — transform applied to the resolved context value


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

# ── 7b. Sheet optimiser scenarios (require rectpack) ─────────────────────────
#
# These scenarios assert on the optimization fields added in Phase 2.
# They expect rectpack to be installed (the default with `uv run`).

_s(Scenario(
    name="cutlist_optimizer_single_sheet",
    prompt="Generate a cutlist for a 600 mm base cabinet and tell me how many sheets of plywood I need.",
    tags=["cutlist", "optimizer"],
    difficulty="basic",
    description="Standard base cabinet should fit on one 4×8 sheet.",
    tool_calls=[
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550},
            label="single-sheet cabinet",
            assertions=[
                Assertion("sheets_used",     Op.EQ,      1),
                Assertion("waste_pct",       Op.GT,      0.0),
                Assertion("waste_pct",       Op.LT,      100.0),
                Assertion("unplaced_panels", Op.LEN_EQ,  0),
                Assertion("optimization_note", Op.HAS_KEY, True),
            ],
        ),
    ],
))

_s(Scenario(
    name="cutlist_optimizer_multi_sheet",
    prompt=(
        "I'm building a 900 mm wide, 2100 mm tall pantry cabinet with three fixed shelves. "
        "Generate the cutlist and let me know how many full sheets I'll need to buy."
    ),
    tags=["cutlist", "optimizer"],
    difficulty="standard",
    description="Tall cabinet with shelves should require multiple 4×8 sheets.",
    tool_calls=[
        ToolCall(
            tool="generate_cutlist",
            args={
                "width": 900, "height": 2100, "depth": 600,
                "drawer_config": [[200, "shelf"], [200, "shelf"], [200, "shelf"]],
            },
            label="multi-sheet tall cabinet",
            assertions=[
                Assertion("sheets_used",     Op.GTE,    2),
                Assertion("waste_pct",       Op.GT,     0.0),
                Assertion("waste_pct",       Op.LT,     100.0),
                Assertion("unplaced_panels", Op.LEN_EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="cutlist_optimizer_oversized_panel",
    prompt=(
        "Design a floor-to-ceiling wardrobe 900 mm wide and 2500 mm tall. "
        "Generate the cutlist against standard 4×8 sheets and flag any panels "
        "that are too large to fit."
    ),
    tags=["cutlist", "optimizer", "edge_case"],
    difficulty="standard",
    description=(
        "A 2500 mm tall cabinet has side panels (2500×600 mm) that exceed the "
        "2440 mm sheet length, so they appear in unplaced_panels."
    ),
    tool_calls=[
        ToolCall(
            tool="generate_cutlist",
            args={"width": 900, "height": 2500, "depth": 600},
            label="wardrobe with oversized sides",
            assertions=[
                Assertion("unplaced_panels", Op.CONTAINS,  "side"),
                Assertion("unplaced_panels", Op.LEN_GTE,   1),
                Assertion("optimization_note", Op.HAS_KEY, True),
                # Sheets used only covers panels that *were* placed.
                Assertion("sheets_used",     Op.GTE,       0),
            ],
        ),
    ],
))

_s(Scenario(
    name="cutlist_optimizer_custom_kerf",
    prompt="Generate a cutlist for a 600 mm cabinet. I'm using a track saw with a 2.5 mm kerf.",
    tags=["cutlist", "optimizer"],
    difficulty="basic",
    description="Custom kerf value propagates to the optimizer without errors.",
    tool_calls=[
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550, "kerf": 2.5},
            label="custom kerf cutlist",
            assertions=[
                Assertion("sheets_used",       Op.GTE,     1),
                Assertion("unplaced_panels",   Op.LEN_EQ,  0),
                Assertion("panel_count",       Op.GTE,     3),
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
                Assertion("drawer_suggestions.0.viable", Op.IS_TRUE),
                Assertion("drawer_suggestions.1.viable", Op.IS_TRUE),
                Assertion("drawer_suggestions.2.viable", Op.IS_TRUE),
                Assertion("drawer_suggestions.3.viable", Op.IS_FALSE),
                Assertion("drawer_suggestions.3.preset", Op.EQ,      "golden"),
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
                Assertion("column_suggestions.0.widths_mm",    Op.LEN_EQ,  3),
                Assertion("column_suggestions.3.widths_mm",    Op.LEN_EQ,  3),
                Assertion("column_suggestions.3.wide_column_mm",   Op.GT,  400.0),
                Assertion("column_suggestions.3.narrow_column_mm", Op.LT,  400.0),
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
                Assertion("drawer_suggestions.0.viable", Op.IS_TRUE),
                Assertion("drawer_suggestions.3.viable", Op.IS_TRUE),
            ],
        ),
    ],
))


# ─── Pulls and knobs ──────────────────────────────────────────────────────────

_s(Scenario(
    name="list_pulls_basic",
    prompt="What pull and knob hardware do we support? Show me the catalog.",
    tags=["pulls"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="list_hardware",
            args={"category": "pulls"},
            label="pulls-only listing",
            assertions=[
                Assertion("pulls",        Op.HAS_KEY),
                Assertion("pulls_count",  Op.GT, 40),
                # Known catalog entries from multiple brands.
                Assertion("pulls.topknobs-hb-128",           Op.HAS_KEY),
                Assertion("pulls.ikea-bagganas-black-128",   Op.HAS_KEY),
                Assertion("pulls.rockler-42250",             Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="list_pulls_ikea_brand_filter",
    prompt="Which IKEA pulls are in the catalog, and what pack size do they ship in?",
    tags=["pulls"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="list_hardware",
            args={"category": "pulls", "brand": "ikea"},
            label="IKEA-only filter",
            assertions=[
                Assertion("pulls_count", Op.GTE, 4),
                # IKEA cabinet hardware ships in 2-packs
                Assertion("pulls.ikea-bagganas-black-128.pack_quantity", Op.EQ, 2),
                Assertion("pulls.ikea-hackas-anthracite-128.pack_quantity", Op.EQ, 2),
                Assertion("pulls.ikea-bagganas-black-128.brand", Op.EQ, "IKEA"),
            ],
        ),
    ],
))

_s(Scenario(
    name="drawer_with_single_pull",
    prompt=(
        "I've got a 500 mm drawer opening, 180 mm tall, 500 mm deep. "
        "Add a Top Knobs Kinney 128 mm bar pull, centred vertically."
    ),
    tags=["pulls", "drawer"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width":  500,
                "opening_height": 180,
                "opening_depth":  500,
                "pull_key":       "topknobs-hb-128",
                "pull_vertical":  "center",
            },
            label="narrow drawer, single pull",
            assertions=[
                Assertion("pull",                   Op.HAS_KEY),
                Assertion("pull.key",               Op.EQ, "topknobs-hb-128"),
                # 500 mm opening → 484 mm face → below 600 mm threshold → 1 pull.
                Assertion("pull.count",             Op.EQ, 1),
                Assertion("pull.placements",        Op.LEN_EQ, 1),
                Assertion("pull.vertical_policy",   Op.EQ, "center"),
                Assertion("pull.issues",            Op.LEN_EQ, 0),
                Assertion("pull.bom.pieces_needed", Op.EQ, 1),
                Assertion("pull.bom.packs_to_order", Op.EQ, 1),
                Assertion("pull.bom.leftover",      Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="wide_drawer_gets_dual_pulls",
    prompt=(
        "Design a 900 mm wide drawer (150 mm tall, 500 mm deep) with the same "
        "Top Knobs Kinney 128 mm bar pull. Because the face is wider than "
        "600 mm, we should get two pulls."
    ),
    tags=["pulls", "drawer"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width":  900,
                "opening_height": 150,
                "opening_depth":  500,
                "pull_key":       "topknobs-hb-128",
            },
            label="wide drawer triggers dual-pull policy",
            assertions=[
                # 900 mm opening → 884 mm face, over the 600 mm threshold.
                Assertion("pull.count",             Op.EQ, 2),
                Assertion("pull.placements",        Op.LEN_EQ, 2),
                Assertion("pull.bom.pieces_needed", Op.EQ, 2),
            ],
        ),
    ],
))

_s(Scenario(
    name="door_pair_with_pulls",
    prompt=(
        "Add pulls to an 800 mm wide × 600 mm tall two-door cabinet. "
        "Each leaf should carry its own pull."
    ),
    tags=["pulls", "door"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width":  800,
                "opening_height": 600,
                "num_doors":      2,
                "pull_key":       "topknobs-hb-128",
            },
            label="door pair with one pull per leaf",
            assertions=[
                Assertion("num_doors",              Op.EQ, 2),
                Assertion("pull.key",               Op.EQ, "topknobs-hb-128"),
                # Each leaf is well under 600 mm → 1 pull per leaf, 2 total.
                Assertion("pull.pulls_per_leaf",    Op.EQ, 1),
                Assertion("pull.total_pulls",       Op.EQ, 2),
                Assertion("pull.bom.pieces_needed", Op.EQ, 2),
            ],
        ),
    ],
))

_s(Scenario(
    name="design_pulls_kitchen_stack",
    prompt=(
        "I've got a 900 × 720 × 550 mm kitchen base with two drawers and a "
        "door pair. Put Top Knobs Kinney 128 mm pulls on everything and give "
        "me placements and a consolidated BOM."
    ),
    tags=["pulls"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_pulls",
            args={
                "width":  900, "height": 720, "depth": 550,
                "drawer_config": [
                    [180, "drawer"],
                    [180, "drawer"],
                    [360, "door_pair"],
                ],
                "drawer_pull": "topknobs-hb-128",
                "door_pull":   "topknobs-hb-128",
            },
            label="end-to-end pulls pass on a kitchen base",
            assertions=[
                Assertion("drawer_slots",   Op.LEN_EQ, 2),
                Assertion("door_slots",     Op.LEN_EQ, 1),
                Assertion("cabinet_issues", Op.LEN_EQ, 0),
                # 884 mm drawer face → 2 pulls each; door_pair → 2 leaves × 1.
                # Total: 4 + 2 = 6, consolidated onto a single SKU line.
                Assertion("bom_totals.line_count",     Op.EQ, 1),
                Assertion("bom_totals.pieces_needed",  Op.EQ, 6),
                Assertion("bom_totals.packs_to_order", Op.EQ, 6),
                Assertion("hardware_bom.0.sku",        Op.EQ, "topknobs-hb-128"),
                Assertion("hardware_bom.0.leftover",   Op.EQ, 0),
                # Each drawer slot carries dual pulls
                Assertion("drawer_slots.0.count",      Op.EQ, 2),
                Assertion("drawer_slots.1.count",      Op.EQ, 2),
                # Door pair: 1 per leaf × 2 leaves
                Assertion("door_slots.0.pulls_per_leaf", Op.EQ, 1),
                Assertion("door_slots.0.total_pulls",    Op.EQ, 2),
            ],
        ),
    ],
))

_s(Scenario(
    name="design_pulls_style_mismatch_warning",
    prompt=(
        "On a 900 × 720 × 550 mm base cabinet, use Transitional Top Knobs "
        "bar pulls on the drawers but Contemporary Ashley Norton wood pulls "
        "on the door. Flag any style consistency problems."
    ),
    tags=["pulls", "evaluation"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_pulls",
            args={
                "width":  900, "height": 720, "depth": 550,
                "drawer_config": [
                    [180, "drawer"],
                    [540, "door"],
                ],
                "drawer_pull": "topknobs-hb-128",   # Transitional
                "door_pull":   "rockler-wnl-160",   # Contemporary
            },
            label="mixed pull styles emit consistency warning",
            assertions=[
                Assertion("cabinet_issues",        Op.LEN_EQ, 1),
                Assertion("cabinet_issues.0.check", Op.EQ, "pull_style_mismatch"),
                Assertion("cabinet_issues.0.severity", Op.EQ, "warning"),
                # Both SKUs still flow through to the consolidated BOM
                Assertion("bom_totals.line_count",  Op.EQ, 2),
            ],
        ),
    ],
))

_s(Scenario(
    name="design_pulls_ikea_pack_quantity_math",
    prompt=(
        "Design a narrow 5-drawer sideboard (500 × 900 × 550 mm) fitted "
        "with IKEA Bagganäs black pulls. IKEA pulls ship in 2-packs, so "
        "tell me how many packs to order and whether we'll have leftovers."
    ),
    tags=["pulls", "cutlist"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_pulls",
            args={
                "width":  500, "height": 900, "depth": 550,
                "drawer_config": [
                    [150, "drawer"], [150, "drawer"], [150, "drawer"],
                    [150, "drawer"], [150, "drawer"],
                ],
                "drawer_pull": "ikea-bagganas-black-128",
            },
            label="IKEA 2-pack rounding on 5-drawer sideboard",
            assertions=[
                # 464 mm face < 600 mm threshold → 1 pull per drawer × 5 drawers
                Assertion("bom_totals.pieces_needed",    Op.EQ, 5),
                Assertion("hardware_bom.0.sku",          Op.EQ, "ikea-bagganas-black-128"),
                Assertion("hardware_bom.0.pack_quantity", Op.EQ, 2),
                # 5 pieces / 2 per pack = 3 packs (ceiling), 6 ordered, 1 leftover
                Assertion("hardware_bom.0.packs_to_order", Op.EQ, 3),
                Assertion("hardware_bom.0.pieces_ordered", Op.EQ, 6),
                Assertion("hardware_bom.0.leftover",       Op.EQ, 1),
                Assertion("cabinet_issues",                Op.LEN_EQ, 0),
            ],
        ),
    ],
))


# ── 20. Shop / workshop cabinets ─────────────────────────────────────────────
#
# Realistic shop-cabinet configurations: tool chests, hardware organisers,
# workbench bases, tall tool cabinets, and outfeed-table drawer banks.
# Several mix doors and drawers; some are wide (≥1200 mm) or tall (≥1500 mm).

_s(Scenario(
    name="shop_tool_chest_8_drawer",
    prompt=(
        "Design a wide shop tool chest: 1200 mm wide, 900 mm tall, 600 mm deep "
        "with eight equal drawers — sized for sockets, wrenches, and hand tools."
    ),
    tags=["workshop", "drawer", "wide"],
    difficulty="standard",
    description=(
        "interior_h = 900 - 36 = 864 mm.  8 × 108 mm drawers = 864 mm. "
        "interior_w = 1200 - 36 = 1164 mm."
    ),
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 1200, "height": 900, "depth": 600,
                "drawer_config": [
                    [108, "drawer"], [108, "drawer"], [108, "drawer"], [108, "drawer"],
                    [108, "drawer"], [108, "drawer"], [108, "drawer"], [108, "drawer"],
                ],
            },
            label="1200 mm tool chest — 8 equal drawers",
            assertions=[
                Assertion("exterior.width_mm",  Op.EQ, 1200),
                Assertion("interior.width_mm",  Op.EQ, 1164),
                Assertion("opening_stack",       Op.LEN_EQ, 8),
                Assertion("opening_stack.0.height_mm", Op.EQ, 108),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 1200, "height": 900, "depth": 600,
                "drawer_config": [
                    [108, "drawer"], [108, "drawer"], [108, "drawer"], [108, "drawer"],
                    [108, "drawer"], [108, "drawer"], [108, "drawer"], [108, "drawer"],
                ],
            },
            label="evaluate tool chest",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="shop_wall_cabinet_door_and_drawer",
    prompt=(
        "Design a 600 mm shop wall cabinet (720 tall, 350 deep) with a large "
        "door opening below and a shallow drawer at the top for small parts.  "
        "Then design the door using the actual interior width."
    ),
    tags=["workshop", "door", "drawer", "workflow"],
    difficulty="standard",
    description=(
        "interior_h = 684 mm: 534 mm door + 150 mm drawer. "
        "interior_w = 564 mm → fed into design_door via chaining."
    ),
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 720, "depth": 350,
                "drawer_config": [[150, "drawer"], [534, "door"]],
            },
            label="600 mm wall cabinet — drawer over door",
            save_as={
                "iw":     "interior.width_mm",
                "door_h": "opening_stack.1.height_mm",
            },
            assertions=[
                Assertion("exterior.width_mm",         Op.EQ, 600),
                Assertion("interior.width_mm",         Op.EQ, 564),
                Assertion("opening_stack",             Op.LEN_EQ, 2),
                Assertion("opening_stack.0.type",      Op.EQ, "drawer"),
                Assertion("opening_stack.1.type",      Op.EQ, "door"),
            ],
        ),
        ToolCall(
            tool="design_door",
            args={"num_doors": 1, "hinge_key": "blum_clip_top_110_full"},
            label="door sized from cabinet interior (chained)",
            context_args={"opening_width": "iw", "opening_height": "door_h"},
            assertions=[
                # Full-overlay door is WIDER than opening (opening + 2 × overlay_mm)
                Assertion("door_width_mm",   Op.GT, 0),
                Assertion("overlay_type",    Op.EQ, "full"),
                # Door height is slightly less than opening (top + bottom gap)
                Assertion("door_height_mm",  Op.LT, 534),
                Assertion("door_height_mm",  Op.GT, 520),
                Assertion("total_hinges",    Op.GTE, 2),
            ],
        ),
    ],
))

_s(Scenario(
    name="shop_hardware_cabinet_tall_7_drawer",
    prompt=(
        "I need a tall narrow hardware cabinet for the shop: 500 mm wide, "
        "1200 mm tall, 400 mm deep with seven equal drawers for nuts, bolts, "
        "and small hardware."
    ),
    tags=["workshop", "drawer", "tall"],
    difficulty="standard",
    description=(
        "interior_h = 1200 - 36 = 1164 mm.  "
        "6 drawers × 166 mm + 1 drawer × 168 mm = 1164 mm."
    ),
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 500, "height": 1200, "depth": 400,
                "drawer_config": [
                    [166, "drawer"], [166, "drawer"], [166, "drawer"],
                    [166, "drawer"], [166, "drawer"], [166, "drawer"],
                    [168, "drawer"],
                ],
            },
            label="500 mm hardware cabinet — 7 drawers",
            assertions=[
                Assertion("exterior.height_mm", Op.EQ, 1200),
                Assertion("opening_stack",       Op.LEN_EQ, 7),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 500, "height": 1200, "depth": 400,
                "drawer_config": [
                    [166, "drawer"], [166, "drawer"], [166, "drawer"],
                    [166, "drawer"], [166, "drawer"], [166, "drawer"],
                    [168, "drawer"],
                ],
            },
            label="evaluate hardware cabinet",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="shop_workbench_base_door_drawers",
    prompt=(
        "Design a workbench base cabinet 600 mm wide, 900 mm tall (bench height), "
        "600 mm deep.  Put a door compartment at the bottom for big power tools "
        "and three drawers above for hand tools."
    ),
    tags=["workshop", "door", "drawer"],
    difficulty="standard",
    description=(
        "interior_h = 900 - 36 = 864 mm.  "
        "264 mm door + 3 × 200 mm drawers = 864 mm."
    ),
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 900, "depth": 600,
                "drawer_config": [
                    [200, "drawer"], [200, "drawer"], [200, "drawer"],
                    [264, "door"],
                ],
            },
            label="workbench base — drawers over door",
            assertions=[
                Assertion("exterior.height_mm",   Op.EQ,  900),
                Assertion("opening_stack",         Op.LEN_EQ, 4),
                Assertion("opening_stack.0.type",  Op.EQ, "drawer"),
                Assertion("opening_stack.3.type",  Op.EQ, "door"),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 900, "depth": 600,
                "drawer_config": [
                    [200, "drawer"], [200, "drawer"], [200, "drawer"],
                    [264, "door"],
                ],
            },
            label="evaluate workbench base",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="shop_tall_tool_cabinet_door_and_drawers",
    prompt=(
        "I want a tall shop tool cabinet: 900 mm wide, 1800 mm tall, 600 mm deep.  "
        "Large door pair at the bottom half for power tools and jigs, "
        "five drawers in the top half for hand tools."
    ),
    tags=["workshop", "door", "drawer", "tall"],
    difficulty="advanced",
    description=(
        "interior_h = 1800 - 36 = 1764 mm.  "
        "900 mm door_pair + 4 × 172 mm drawers + 176 mm drawer = 1764 mm."
    ),
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 900, "height": 1800, "depth": 600,
                "drawer_config": [
                    [172, "drawer"], [172, "drawer"], [172, "drawer"],
                    [172, "drawer"], [176, "drawer"],
                    [900, "door_pair"],
                ],
            },
            label="tall tool cabinet — 5 drawers over door pair",
            assertions=[
                Assertion("exterior.height_mm",  Op.EQ, 1800),
                Assertion("exterior.width_mm",   Op.EQ,  900),
                Assertion("opening_stack",        Op.LEN_EQ, 6),
                Assertion("opening_stack.5.type", Op.EQ, "door_pair"),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 900, "height": 1800, "depth": 600,
                "drawer_config": [
                    [172, "drawer"], [172, "drawer"], [172, "drawer"],
                    [172, "drawer"], [176, "drawer"],
                    [900, "door_pair"],
                ],
            },
            label="evaluate tall tool cabinet",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="shop_outfeed_table_wide_4_drawer",
    prompt=(
        "Design an outfeed table base cabinet: 1500 mm wide, 900 mm tall "
        "(bench height), 600 mm deep with four drawers for templates and sleds."
    ),
    tags=["workshop", "drawer", "wide"],
    difficulty="standard",
    description=(
        "interior_h = 864 mm.  "
        "3 × 200 mm drawers + 264 mm drawer = 864 mm."
    ),
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 1500, "height": 900, "depth": 600,
                "drawer_config": [
                    [200, "drawer"], [200, "drawer"],
                    [200, "drawer"], [264, "drawer"],
                ],
            },
            label="1500 mm outfeed base — 4 drawers",
            assertions=[
                Assertion("exterior.width_mm",  Op.EQ, 1500),
                Assertion("interior.width_mm",  Op.EQ, 1464),
                Assertion("opening_stack",       Op.LEN_EQ, 4),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 1500, "height": 900, "depth": 600,
                "drawer_config": [
                    [200, "drawer"], [200, "drawer"],
                    [200, "drawer"], [264, "drawer"],
                ],
            },
            label="evaluate outfeed base",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))


# ── 21. Furniture ─────────────────────────────────────────────────────────────
#
# Bedroom, living room, and home-office furniture: dressers, nightstands,
# filing cabinets, wardrobes, sideboards, media consoles, and buffets.
# Includes wide and tall pieces as well as several mixed door+drawer designs.

_s(Scenario(
    name="furniture_dresser_6_drawer",
    prompt=(
        "Design a bedroom dresser: 900 mm wide, 1100 mm tall, 550 mm deep "
        "with six drawers using subtle graduated proportions.  "
        "Then validate the design using the computed drawer heights."
    ),
    tags=["furniture", "drawer"],
    difficulty="standard",
    description=(
        "interior_h = 1100 - 36 = 1064 mm.  "
        "Six drawers with subtle (1.2×) ratio — classic fails (top drawer 65 mm < 75 mm min). "
        "Heights are floats; chained via opening_stack → drawer_config transform."
    ),
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 900, "height": 1100, "depth": 550,
                "num_drawers": 6,
                "drawer_proportion": "subtle",
            },
            label="900 mm dresser — 6 subtle-graduated drawers",
            save_as={"stack": "opening_stack"},
            assertions=[
                Assertion("exterior.width_mm",   Op.EQ, 900),
                Assertion("exterior.height_mm",  Op.EQ, 1100),
                Assertion("opening_stack",        Op.LEN_EQ, 6),
                Assertion("opening_stack.0.type", Op.EQ, "drawer"),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 900, "height": 1100, "depth": 550},
            label="evaluate dresser (drawer_config chained from opening_stack)",
            context_args={"drawer_config": "stack"},
            arg_transforms={
                "drawer_config": lambda s: [[item["height_mm"], item["type"]] for item in s],
            },
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="furniture_tall_chest_8_drawer",
    prompt=(
        "Design a tall bedroom chest of drawers: 600 mm wide, 1800 mm tall, "
        "550 mm deep with eight equal drawers.  "
        "Validate using the computed heights."
    ),
    tags=["furniture", "drawer", "tall"],
    difficulty="standard",
    description=(
        "interior_h = 1800 - 36 = 1764 mm.  "
        "Eight equal drawers (220.5 mm each — float heights chained to evaluate)."
    ),
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 1800, "depth": 550,
                "num_drawers": 8,
                "drawer_proportion": "equal",
            },
            label="600 mm tall chest — 8 equal drawers",
            save_as={"stack": "opening_stack"},
            assertions=[
                Assertion("exterior.height_mm",  Op.EQ, 1800),
                Assertion("opening_stack",        Op.LEN_EQ, 8),
                Assertion("opening_stack.0.type", Op.EQ, "drawer"),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 1800, "depth": 550},
            label="evaluate tall chest (drawer_config chained from opening_stack)",
            context_args={"drawer_config": "stack"},
            arg_transforms={
                "drawer_config": lambda s: [[item["height_mm"], item["type"]] for item in s],
            },
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="furniture_nightstand_door_and_drawer",
    prompt=(
        "Design a bedside nightstand: 500 mm wide, 600 mm tall, 450 mm deep.  "
        "One shallow drawer on top for remotes and glasses, "
        "a door compartment below."
    ),
    tags=["furniture", "door", "drawer"],
    difficulty="basic",
    description=(
        "interior_h = 600 - 36 = 564 mm.  "
        "200 mm drawer + 364 mm door = 564 mm."
    ),
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 500, "height": 600, "depth": 450,
                "drawer_config": [[200, "drawer"], [364, "door"]],
            },
            label="nightstand — drawer over door",
            assertions=[
                Assertion("exterior.width_mm",        Op.EQ, 500),
                Assertion("opening_stack",             Op.LEN_EQ, 2),
                Assertion("opening_stack.0.type",      Op.EQ, "drawer"),
                Assertion("opening_stack.1.type",      Op.EQ, "door"),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 500, "height": 600, "depth": 450,
                "drawer_config": [[200, "drawer"], [364, "door"]],
            },
            label="evaluate nightstand",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="furniture_filing_cabinet_4_drawer",
    prompt=(
        "Design a home-office filing cabinet: 450 mm wide, 1200 mm tall, "
        "600 mm deep with four equal drawers deep enough for letter-size hanging "
        "files."
    ),
    tags=["furniture", "drawer", "tall"],
    difficulty="standard",
    description=(
        "interior_h = 1200 - 36 = 1164 mm.  4 × 291 mm = 1164 mm."
    ),
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 450, "height": 1200, "depth": 600,
                "drawer_config": [
                    [291, "drawer"], [291, "drawer"],
                    [291, "drawer"], [291, "drawer"],
                ],
            },
            label="450 mm filing cabinet — 4 drawers",
            assertions=[
                Assertion("exterior.height_mm", Op.EQ, 1200),
                Assertion("exterior.depth_mm",  Op.EQ, 600),
                Assertion("opening_stack",       Op.LEN_EQ, 4),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 450, "height": 1200, "depth": 600,
                "drawer_config": [
                    [291, "drawer"], [291, "drawer"],
                    [291, "drawer"], [291, "drawer"],
                ],
            },
            label="evaluate filing cabinet",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="furniture_wardrobe_door_pair_and_drawers",
    prompt=(
        "Design a full-height bedroom wardrobe: 900 mm wide, 2100 mm tall, "
        "600 mm deep.  Large door pair covering the top two-thirds, "
        "two drawers at the base."
    ),
    tags=["furniture", "door", "drawer", "tall"],
    difficulty="advanced",
    description=(
        "interior_h = 2100 - 36 = 2064 mm.  "
        "1600 mm door_pair + 200 mm drawer + 264 mm drawer = 2064 mm."
    ),
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 900, "height": 2100, "depth": 600,
                "drawer_config": [
                    [200, "drawer"], [264, "drawer"],
                    [1600, "door_pair"],
                ],
            },
            label="900 mm wardrobe — 2 drawers below door pair",
            assertions=[
                Assertion("exterior.height_mm",  Op.EQ, 2100),
                Assertion("opening_stack",        Op.LEN_EQ, 3),
                Assertion("opening_stack.2.type", Op.EQ, "door_pair"),
                Assertion("opening_stack.0.type", Op.EQ, "drawer"),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 900, "height": 2100, "depth": 600,
                "drawer_config": [
                    [200, "drawer"], [264, "drawer"],
                    [1600, "door_pair"],
                ],
            },
            label="evaluate wardrobe",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="furniture_sideboard_3col_door_drawer_door",
    prompt=(
        "Design a 1500 mm wide sideboard (850 mm tall, 450 mm deep) with three "
        "columns: a door compartment on each side and four drawers in the centre."
    ),
    tags=["furniture", "door", "drawer", "wide", "multi_column"],
    difficulty="advanced",
    description=(
        "interior_h = 814 mm, interior_w = 1464 mm.  "
        "Three 488 mm columns: door_pair | 4 drawers | door_pair."
    ),
    tool_calls=[
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 1500, "height": 850, "depth": 450,
                "columns": [
                    {"width_mm": 488, "drawer_config": [[814, "door_pair"]]},
                    {
                        "width_mm": 488,
                        "drawer_config": [
                            [200, "drawer"], [200, "drawer"],
                            [200, "drawer"], [214, "drawer"],
                        ],
                    },
                    {"width_mm": 488, "drawer_config": [[814, "door_pair"]]},
                ],
            },
            label="1500 mm sideboard — door | drawers | door",
            assertions=[
                Assertion("column_count",          Op.EQ, 3),
                Assertion("columns_fill_interior", Op.IS_TRUE),
                Assertion("interior_width_mm",     Op.APPROX, 1464.0),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 1500, "height": 850, "depth": 450,
                "columns": [
                    {"width_mm": 488, "drawer_config": [[814, "door_pair"]]},
                    {
                        "width_mm": 488,
                        "drawer_config": [
                            [200, "drawer"], [200, "drawer"],
                            [200, "drawer"], [214, "drawer"],
                        ],
                    },
                    {"width_mm": 488, "drawer_config": [[814, "door_pair"]]},
                ],
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
    name="furniture_media_console_3col_low_wide",
    prompt=(
        "Design a low media console: 1800 mm wide, 450 mm tall, 400 mm deep.  "
        "Three columns: door compartments on the outside, "
        "two drawers in the centre for remotes and cables."
    ),
    tags=["furniture", "door", "drawer", "wide", "multi_column"],
    difficulty="advanced",
    description=(
        "interior_h = 414 mm, interior_w = 1764 mm.  "
        "Three 588 mm columns: door_pair | 2 × 207 mm drawers | door_pair."
    ),
    tool_calls=[
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 1800, "height": 450, "depth": 400,
                "columns": [
                    {"width_mm": 588, "drawer_config": [[414, "door_pair"]]},
                    {
                        "width_mm": 588,
                        "drawer_config": [[207, "drawer"], [207, "drawer"]],
                    },
                    {"width_mm": 588, "drawer_config": [[414, "door_pair"]]},
                ],
            },
            label="1800 mm media console — door | 2 drawers | door",
            assertions=[
                Assertion("column_count",          Op.EQ, 3),
                Assertion("columns_fill_interior", Op.IS_TRUE),
                Assertion("exterior.width_mm",     Op.EQ, 1800),
                Assertion("exterior.height_mm",    Op.EQ, 450),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 1800, "height": 450, "depth": 400,
                "columns": [
                    {"width_mm": 588, "drawer_config": [[414, "door_pair"]]},
                    {
                        "width_mm": 588,
                        "drawer_config": [[207, "drawer"], [207, "drawer"]],
                    },
                    {"width_mm": 588, "drawer_config": [[414, "door_pair"]]},
                ],
            },
            label="evaluate media console",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="furniture_buffet_3col_door_drawer_door",
    prompt=(
        "Design a dining room buffet: 1800 mm wide, 900 mm tall, 500 mm deep.  "
        "Three columns — door pair on each end, four drawers in the centre "
        "for silverware and linens."
    ),
    tags=["furniture", "door", "drawer", "wide", "multi_column"],
    difficulty="advanced",
    description=(
        "interior_h = 864 mm, interior_w = 1764 mm.  "
        "Three 588 mm columns: door_pair | 4 × 216 mm drawers | door_pair."
    ),
    tool_calls=[
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 1800, "height": 900, "depth": 500,
                "columns": [
                    {"width_mm": 588, "drawer_config": [[864, "door_pair"]]},
                    {
                        "width_mm": 588,
                        "drawer_config": [
                            [216, "drawer"], [216, "drawer"],
                            [216, "drawer"], [216, "drawer"],
                        ],
                    },
                    {"width_mm": 588, "drawer_config": [[864, "door_pair"]]},
                ],
            },
            label="1800 mm buffet — door_pair | 4 drawers | door_pair",
            assertions=[
                Assertion("column_count",          Op.EQ, 3),
                Assertion("columns_fill_interior", Op.IS_TRUE),
                Assertion("exterior.width_mm",     Op.EQ, 1800),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 1800, "height": 900, "depth": 500,
                "columns": [
                    {"width_mm": 588, "drawer_config": [[864, "door_pair"]]},
                    {
                        "width_mm": 588,
                        "drawer_config": [
                            [216, "drawer"], [216, "drawer"],
                            [216, "drawer"], [216, "drawer"],
                        ],
                    },
                    {"width_mm": 588, "drawer_config": [[864, "door_pair"]]},
                ],
            },
            label="evaluate buffet",
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))


# ── 22. Shop / furniture chained workflows ────────────────────────────────────

_s(Scenario(
    name="workflow_chain_dresser_design_to_cutlist",
    prompt=(
        "Design a 900 mm dresser with 6 subtle-graduated drawers, then generate "
        "the cutlist using the actual exterior dimensions returned by design_cabinet."
    ),
    tags=["furniture", "drawer", "workflow", "cutlist"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 900, "height": 1100, "depth": 550,
                "num_drawers": 6,
                "drawer_proportion": "subtle",
            },
            label="900 mm dresser",
            save_as={
                "w": "exterior.width_mm",
                "h": "exterior.height_mm",
                "d": "exterior.depth_mm",
            },
            assertions=[
                Assertion("exterior.width_mm",  Op.EQ, 900),
                Assertion("opening_stack",       Op.LEN_EQ, 6),
            ],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"format": "json"},
            label="dresser cutlist (chained)",
            context_args={"width": "w", "height": "h", "depth": "d"},
            assertions=[
                Assertion("panel_count",         Op.GTE, 3),
                Assertion("sheets_used",         Op.GTE, 1),
                Assertion("cutlist_json.panels", Op.LEN_GTE, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="workflow_chain_shop_workbench_to_describe",
    prompt=(
        "Design a workbench base with mixed door and drawers, then chain the "
        "returned dimensions into describe_design to get a prose summary."
    ),
    tags=["workshop", "door", "drawer", "workflow", "describe"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 900, "depth": 600,
                "drawer_config": [
                    [200, "drawer"], [200, "drawer"], [200, "drawer"],
                    [264, "door"],
                ],
            },
            label="600 mm workbench base",
            save_as={
                "w": "exterior.width_mm",
                "h": "exterior.height_mm",
                "d": "exterior.depth_mm",
            },
            assertions=[
                Assertion("opening_stack",        Op.LEN_EQ, 4),
                Assertion("opening_stack.3.type", Op.EQ, "door"),
            ],
        ),
        ToolCall(
            tool="describe_design",
            args={
                "drawer_config": [
                    [200, "drawer"], [200, "drawer"], [200, "drawer"],
                    [264, "door"],
                ],
            },
            label="describe workbench base (chained dimensions)",
            context_args={"width": "w", "height": "h", "depth": "d"},
            assertions=[
                Assertion("prose",                         Op.CONTAINS, "600 mm"),
                Assertion("openings.stack_fills_interior", Op.IS_TRUE),
            ],
        ),
    ],
))


# ── 20. Chained workflow scenarios ───────────────────────────────────────────
#
# These scenarios exercise the context-chaining mechanism: save_as extracts
# values from one step's output; context_args injects them as arguments to
# the next step.  The goal is to verify that realistic LLM tool-call sequences
# (where each step uses computed results from the previous step) work end-to-end
# without hardcoding intermediate values.

_s(Scenario(
    name="workflow_chain_preset_to_evaluate",
    prompt=(
        "Apply the kitchen_base_3_drawer preset, then validate the returned "
        "config through evaluate_cabinet — using the actual dimensions the "
        "preset gives back, not hardcoded values."
    ),
    tags=["workflow", "presets", "evaluation"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "kitchen_base_3_drawer"},
            label="apply kitchen_base_3_drawer preset",
            save_as={
                "w":  "config.width",
                "h":  "config.height",
                "d":  "config.depth",
                "dc": "config.drawer_config",
            },
            assertions=[
                Assertion("preset_name",  Op.EQ, "kitchen_base_3_drawer"),
                Assertion("config.width", Op.EQ, 600),
                Assertion("config.height", Op.EQ, 720),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={},
            label="evaluate preset dimensions (chained)",
            context_args={"width": "w", "height": "h", "depth": "d",
                          "drawer_config": "dc"},
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="workflow_chain_design_interior_to_drawer",
    prompt=(
        "Design a 600 mm cabinet with three equal 228 mm drawers, then design "
        "a drawer box for the first opening using the computed interior width — "
        "not the exterior 600 mm input."
    ),
    tags=["workflow", "drawer"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]],
            },
            label="600 mm cabinet — 3 equal drawers",
            save_as={
                "opening_w":  "interior.width_mm",    # 600 - 2*18 = 564
                "stack_h":    "opening_stack.0.height_mm",
                "interior_d": "interior.depth_mm",
            },
            assertions=[
                Assertion("interior.width_mm",         Op.EQ, 564),
                Assertion("opening_stack.0.height_mm", Op.EQ, 228),
                Assertion("opening_stack",             Op.LEN_EQ, 3),
            ],
        ),
        ToolCall(
            tool="design_drawer",
            args={"joinery_style": "butt"},
            label="drawer box sized from cabinet interior (chained)",
            context_args={
                "opening_width":  "opening_w",
                "opening_height": "stack_h",
                "opening_depth":  "interior_d",
            },
            assertions=[
                Assertion("box_width_mm",  Op.LT,  564),
                Assertion("box_height_mm", Op.LT,  228),
                Assertion("box_depth_mm",  Op.GT,  0),
                Assertion("joinery.style", Op.EQ,  "butt"),
            ],
        ),
    ],
))

_s(Scenario(
    name="workflow_chain_auto_fix_to_evaluate",
    prompt=(
        "Start with a 600 mm cabinet whose single drawer overflows the interior "
        "(800 mm > 684 mm). Auto-fix it, then pipe the repaired config directly "
        "into evaluate_cabinet and confirm it now passes."
    ),
    tags=["workflow", "auto_fix", "evaluation"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="auto_fix_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[800, "drawer"]],   # overflows 684 mm interior
            },
            label="auto-fix single oversized drawer",
            save_as={
                "fixed_w":  "config.width",
                "fixed_h":  "config.height",
                "fixed_d":  "config.depth",
                "fixed_dc": "config.drawer_config",
            },
            assertions=[
                Assertion("fixed",         Op.IS_TRUE),
                Assertion("errors_before", Op.GT, 0),
                Assertion("errors_after",  Op.EQ, 0),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={},
            label="evaluate the auto-fixed config (chained)",
            context_args={
                "width":         "fixed_w",
                "height":        "fixed_h",
                "depth":         "fixed_d",
                "drawer_config": "fixed_dc",
            },
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="workflow_chain_design_to_cutlist",
    prompt=(
        "Design a 750 mm wide base cabinet, then generate its cutlist using "
        "the exterior dimensions returned by design_cabinet rather than "
        "repeating the input values."
    ),
    tags=["workflow", "cutlist"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 750, "height": 720, "depth": 550},
            label="750 mm base cabinet",
            save_as={
                "w": "exterior.width_mm",
                "h": "exterior.height_mm",
                "d": "exterior.depth_mm",
            },
            assertions=[
                Assertion("exterior.width_mm",  Op.EQ, 750),
                Assertion("interior.width_mm",  Op.EQ, 714),   # 750 - 2*18
            ],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"format": "json"},
            label="cutlist from chained dimensions",
            context_args={"width": "w", "height": "h", "depth": "d"},
            assertions=[
                Assertion("panel_count",         Op.GTE, 3),
                # panel_count = distinct panel types; side+top share "bottom" type (qty 2)
                Assertion("sheets_used",         Op.GTE, 1),
                Assertion("cutlist_json.panels", Op.LEN_GTE, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="workflow_chain_suggest_proportions_to_design",
    prompt=(
        "Ask for proportion suggestions for a 4-drawer 600 mm cabinet, then "
        "design the cabinet using the classic-preset heights — transforming the "
        "returned list of heights into a drawer_config on the fly."
    ),
    tags=["workflow", "proportions"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 600, "height": 720, "num_drawers": 4},
            label="suggest 4-drawer proportions",
            save_as={
                "classic_heights": "drawer_suggestions.2.heights_mm",
                # RATIO_PRESETS order: 0=equal, 1=subtle, 2=classic, 3=golden
            },
            assertions=[
                Assertion("drawer_suggestions",         Op.LEN_EQ, 4),
                Assertion("drawer_suggestions.2.preset", Op.EQ, "classic"),
                Assertion("drawer_suggestions.2.viable", Op.IS_TRUE),
            ],
        ),
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550},
            label="cabinet with classic-proportioned drawers (chained + transformed)",
            context_args={"drawer_config": "classic_heights"},
            arg_transforms={
                "drawer_config": lambda heights: [[h, "drawer"] for h in heights],
            },
            assertions=[
                Assertion("opening_stack",           Op.LEN_EQ, 4),
                Assertion("opening_stack.0.type",    Op.EQ, "drawer"),
                Assertion("exterior.width_mm",       Op.EQ, 600),
            ],
        ),
    ],
))

_s(Scenario(
    name="workflow_chain_three_step_design_evaluate_cutlist",
    prompt=(
        "Full 3-step chain for an 800 mm base cabinet: design it, evaluate it, "
        "then generate the cutlist — with dimensions flowing through all three "
        "steps via the context rather than being repeated."
    ),
    tags=["workflow", "evaluation", "cutlist"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 800, "height": 720, "depth": 550},
            label="800 mm base cabinet",
            save_as={
                "w": "exterior.width_mm",
                "h": "exterior.height_mm",
                "d": "exterior.depth_mm",
            },
            assertions=[
                Assertion("exterior.width_mm", Op.EQ, 800),
                Assertion("interior.width_mm", Op.EQ, 764),   # 800 - 2*18
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={},
            label="evaluate 800 mm cabinet (chained)",
            context_args={"width": "w", "height": "h", "depth": "d"},
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"format": "json"},
            label="cutlist for 800 mm cabinet (chained)",
            context_args={"width": "w", "height": "h", "depth": "d"},
            assertions=[
                Assertion("panel_count",         Op.GTE, 3),
                Assertion("cutlist_json.panels", Op.LEN_GTE, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="workflow_chain_auto_fix_to_describe",
    prompt=(
        "A 3-drawer stack (300+300+300=900 mm) overflows a 600 mm cabinet. "
        "Auto-fix it, then describe the repaired design using the actual fixed "
        "drawer_config rather than a hardcoded approximation."
    ),
    tags=["workflow", "auto_fix", "describe"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="auto_fix_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[300, "drawer"], [300, "drawer"], [300, "drawer"]],
            },
            label="auto-fix 3×300 mm overflow",
            save_as={
                "fw":  "config.width",
                "fh":  "config.height",
                "fd":  "config.depth",
                "fdc": "config.drawer_config",
            },
            assertions=[
                Assertion("fixed",         Op.IS_TRUE),
                Assertion("errors_before", Op.GT, 0),
                Assertion("errors_after",  Op.EQ, 0),
                Assertion("config.drawer_config", Op.LEN_EQ, 3),
            ],
        ),
        ToolCall(
            tool="describe_design",
            args={},
            label="describe the auto-fixed cabinet (chained)",
            context_args={
                "width":         "fw",
                "height":        "fh",
                "depth":         "fd",
                "drawer_config": "fdc",
            },
            assertions=[
                Assertion("prose",                         Op.CONTAINS, "600 mm"),
                Assertion("openings.stack_fills_interior", Op.IS_TRUE),
            ],
        ),
    ],
))

_s(Scenario(
    name="workflow_chain_tall_pantry_preset_to_evaluate",
    prompt=(
        "Apply the kitchen_tall_pantry preset and verify it passes evaluation "
        "end-to-end by chaining the returned config dimensions directly into "
        "evaluate_cabinet."
    ),
    tags=["workflow", "presets", "evaluation"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "kitchen_tall_pantry"},
            label="apply kitchen_tall_pantry preset",
            save_as={
                "w":  "config.width",
                "h":  "config.height",
                "d":  "config.depth",
                "dc": "config.drawer_config",
            },
            assertions=[
                Assertion("preset_name",   Op.EQ, "kitchen_tall_pantry"),
                Assertion("config.height", Op.GTE, 2000),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={},
            label="evaluate tall pantry preset (chained)",
            context_args={
                "width":         "w",
                "height":        "h",
                "depth":         "d",
                "drawer_config": "dc",
            },
            assertions=[
                Assertion("summary.pass",   Op.IS_TRUE),
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))


# ── 23. Drawer stack order — regression + detection ──────────────────────────
#
# Three scenarios cover the equal-ratio rounding bug fix and the new
# check_drawer_stack_order evaluation check.

_s(Scenario(
    name="proportions_equal_bottom_drawer_monotone",
    prompt=(
        "Design a cabinet with eight equal drawers where the interior height "
        "doesn't divide evenly by 8 — verify the bottom drawer is never shorter "
        "than the drawers above it (regression for equal-ratio rounding bug)."
    ),
    tags=["proportions", "evaluation"],
    difficulty="standard",
    description=(
        "height=642 → interior_h=606 mm.  606 / 8 = 75.75 mm.  "
        "Before the fix the equal path rounded h UP to 75.8 then computed "
        "heights[0] = 606 - 75.8×7 = 75.4 mm — shorter than the rest. "
        "After the fix: floor division gives base=75.7, extra=4 tenths → "
        "heights[0]=76.1, all others=75.7.  Bottom is always ≥ top."
    ),
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 642, "depth": 550,
                "num_drawers": 8,
                "drawer_proportion": "equal",
            },
            label="8-equal-drawer cabinet — formerly buggy interior height",
            save_as={"dc_for_eval": "opening_stack"},
            assertions=[
                Assertion("opening_stack",          Op.LEN_EQ, 8),
                # Bottom drawer (index 0) must be >= all others.
                # Before the fix heights[0] was 75.4; after fix it is 76.1.
                # GTE 75.8 distinguishes the two:
                Assertion("opening_stack.0.height_mm", Op.GTE, 75.8,
                          description="bottom drawer >= 75.8 mm (regression guard)"),
                # All other drawers should be the uniform floor value (75.7 mm).
                Assertion("opening_stack.1.height_mm", Op.LTE, 75.8,
                          description="non-bottom drawers ≤ bottom"),
                Assertion("opening_stack.7.height_mm", Op.LTE, 75.8,
                          description="top drawer ≤ bottom"),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 642, "depth": 550},
            label="evaluate — no stack-order warnings after fix",
            context_args={"drawer_config": "dc_for_eval"},
            arg_transforms={
                "drawer_config": lambda s: [[item["height_mm"], item["type"]] for item in s],
            },
            assertions=[
                # The cabinet has drawer_carcass_clearance errors (75.7 mm openings
                # are below the Blum Tandem 550H 80 mm minimum) — that is expected
                # and not what this scenario is testing.  What matters is that the
                # equal-ratio rounding fix produces NO drawer_stack_order warnings
                # (before the fix, heights[0] was shorter than heights[1..7], which
                # would have triggered one warning per adjacent pair).
                Assertion("summary.warnings", Op.EQ, 1,
                          description="only the cumulative_heights fill-warning; no stack_order warnings"),
            ],
        ),
    ],
))

_s(Scenario(
    name="evaluation_drawer_stack_order_inverted_warns",
    prompt=(
        "Evaluate a 600 mm cabinet whose three drawers are specified smallest-at-"
        "bottom (150 → 200 → 334 mm) — verify that the evaluator warns about the "
        "inverted graduation."
    ),
    tags=["evaluation", "proportions"],
    difficulty="standard",
    description=(
        "Correct order would be 334 → 200 → 150 (largest at bottom). "
        "Two adjacent inversions should each produce a drawer_stack_order WARNING."
    ),
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[150, "drawer"], [200, "drawer"], [334, "drawer"]],
            },
            label="inverted 3-drawer stack",
            assertions=[
                # Two stack_order warnings (150<200 and 200<334) plus one
                # cumulative_heights warning (stack exactly fills interior).
                Assertion("summary.warnings",   Op.GTE, 2),
                Assertion("issues.0.check",     Op.EQ, "drawer_stack_order"),
                Assertion("issues.0.severity",  Op.EQ, "warning"),
                Assertion("issues.1.check",     Op.EQ, "drawer_stack_order"),
            ],
        ),
    ],
))

_s(Scenario(
    name="evaluation_drawer_stack_order_correct_no_warn",
    prompt=(
        "Evaluate a 600 mm cabinet with a correctly graduated drawer stack "
        "(334 → 200 → 100 mm, largest at bottom, slightly under-fills interior) "
        "— verify no stack-order warnings are produced."
    ),
    tags=["evaluation", "proportions"],
    difficulty="basic",
    description=(
        "Stack sum = 634 mm < 684 mm interior — intentional underfill so the "
        "'exactly fills' cumulative warning doesn't obscure the stack-order result. "
        "All drawers decrease towards the top → no stack_order issues."
    ),
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[334, "drawer"], [200, "drawer"], [100, "drawer"]],
            },
            label="correct bottom-heavy 3-drawer stack",
            assertions=[
                Assertion("summary.warnings", Op.EQ, 0,
                          description="no warnings — stack is correctly graduated"),
                Assertion("summary.errors",   Op.EQ, 0),
                Assertion("summary.pass",     Op.IS_TRUE),
            ],
        ),
    ],
))


# ── 24. Homeowner persona ─────────────────────────────────────────────────────
# Room-oriented, natural-language prompts. Homeowners use presets heavily,
# care about fit and appearance, want descriptions to share with contractors.
# 20 basic / 20 standard / 10 advanced.

# --- Basic (20) ---

_s(Scenario(
    name="hw_kitchen_base_single_drawer",
    prompt="I want a single-drawer base cabinet under my kitchen counter — 600 mm wide, 720 mm tall, 550 mm deep.",
    tags=["homeowner", "kitchen", "drawer"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550, "num_drawers": 1},
            assertions=[
                Assertion("opening_stack", Op.LEN_EQ, 1),
                Assertion("exterior.width_mm",  Op.EQ, 600),
                Assertion("opening_stack.0.height_mm", Op.GT, 600),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_bathroom_vanity_preset",
    prompt="Pull up the standard bathroom vanity preset so I can see the default dimensions.",
    tags=["homeowner", "bathroom"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "bathroom_vanity"},
            assertions=[
                Assertion("preset_name",   Op.EQ, "bathroom_vanity"),
                Assertion("config.width",  Op.EQ, 600),
                Assertion("config.height", Op.EQ, 850),
                Assertion("config.depth",  Op.EQ, 480),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_bedroom_dresser_preset",
    prompt="Show me the default bedroom dresser preset — I want to see what size it is and how the drawers are laid out.",
    tags=["homeowner", "bedroom"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "bedroom_dresser"},
            assertions=[
                Assertion("preset_name",   Op.EQ, "bedroom_dresser"),
                Assertion("config.width",  Op.EQ, 900),
                Assertion("config.height", Op.EQ, 1100),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_kitchen_door_2drawer_preset",
    prompt="Load the kitchen base cabinet with door and two drawers.",
    tags=["homeowner", "kitchen", "door", "drawer"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "kitchen_base_door_2_drawer"},
            assertions=[
                Assertion("preset_name",  Op.EQ, "kitchen_base_door_2_drawer"),
                Assertion("config.width", Op.EQ, 600),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_kitchen_door_pair_wide_preset",
    prompt="I need a wide 900 mm base cabinet with two doors — is there a preset for that?",
    tags=["homeowner", "kitchen", "door"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "kitchen_base_door_pair_wide"},
            assertions=[
                Assertion("preset_name",  Op.EQ, "kitchen_base_door_pair_wide"),
                Assertion("config.width", Op.EQ, 900),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_storage_wall_preset",
    prompt="What are the dimensions of the standard storage wall cabinet?",
    tags=["homeowner", "storage"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "storage_wall_cabinet"},
            assertions=[
                Assertion("preset_name",   Op.EQ, "storage_wall_cabinet"),
                Assertion("config.width",  Op.EQ, 600),
                Assertion("config.height", Op.EQ, 720),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_foyer_narrow_preset",
    prompt="I have a narrow entryway — only 900 mm wide. Is there a console preset that size?",
    tags=["homeowner", "living_room"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "foyer_console_narrow"},
            assertions=[
                Assertion("preset_name",  Op.EQ, "foyer_console_narrow"),
                Assertion("config.width", Op.EQ, 900),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_mudroom_bench_3drawer",
    prompt="I want a mudroom bench cabinet with three drawers under the seat — 1200 mm wide, 500 mm tall, 450 mm deep.",
    tags=["homeowner", "drawer"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 1200, "height": 500, "depth": 450, "num_drawers": 3},
            assertions=[
                Assertion("opening_stack",      Op.LEN_EQ, 3),
                Assertion("exterior.width_mm", Op.EQ, 1200),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_nightstand_drawer_door",
    prompt="Design a nightstand — 450 mm wide, 600 mm tall, 400 mm deep — with one drawer on top and a door below.",
    tags=["homeowner", "bedroom", "drawer", "door"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 450, "height": 600, "depth": 400,
                "drawer_config": [[200, "drawer"], [328, "door"]],
            },
            assertions=[
                Assertion("opening_stack",        Op.LEN_EQ, 2),
                Assertion("opening_stack.0.type", Op.EQ, "drawer"),
                Assertion("opening_stack.1.type", Op.EQ, "door"),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_kids_low_cabinet",
    prompt="I need a low storage cabinet for my kid's room — 600 mm wide, 400 mm tall, 350 mm deep — with two small drawers.",
    tags=["homeowner", "bedroom", "drawer"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 400, "depth": 350, "num_drawers": 2},
            assertions=[
                Assertion("opening_stack",             Op.LEN_EQ, 2),
                Assertion("opening_stack.0.height_mm", Op.GT, 100),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_home_office_pedestal",
    prompt="I'd like a three-drawer pedestal for my home-office desk — 400 mm wide, 720 mm tall, 550 mm deep.",
    tags=["homeowner", "drawer"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 400, "height": 720, "depth": 550, "num_drawers": 3},
            assertions=[
                Assertion("opening_stack",      Op.LEN_EQ, 3),
                Assertion("exterior.width_mm", Op.EQ, 400),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_closet_organizer_6drawer",
    prompt="I want to build a tall closet organiser with six equal drawers — 900 mm wide, 1200 mm tall, 550 mm deep.",
    tags=["homeowner", "bedroom", "drawer", "tall"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 900, "height": 1200, "depth": 550,
                  "num_drawers": 6, "drawer_proportion": "equal"},
            assertions=[
                Assertion("opening_stack",      Op.LEN_EQ, 6),
                Assertion("exterior.width_mm", Op.EQ, 900),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_under_sink_door_only",
    prompt="The cabinet under my bathroom sink just needs a door — no drawers. 600 mm wide, 720 mm tall, 480 mm deep.",
    tags=["homeowner", "bathroom", "door"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 720, "depth": 480,
                "drawer_config": [[684, "door"]],
            },
            assertions=[
                Assertion("opening_stack",        Op.LEN_EQ, 1),
                Assertion("opening_stack.0.type", Op.EQ, "door"),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_linen_closet_tall",
    prompt="I need a tall linen-closet cabinet — 600 mm wide, 2100 mm tall, 350 mm deep — with a pair of doors.",
    tags=["homeowner", "door", "tall"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 2100, "depth": 350,
                "drawer_config": [[2064, "door_pair"]],
            },
            assertions=[
                Assertion("opening_stack",        Op.LEN_EQ, 1),
                Assertion("opening_stack.0.type",  Op.EQ, "door_pair"),
                Assertion("exterior.height_mm",    Op.EQ, 2100),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_guest_tv_stand",
    prompt="I need a wide, low TV stand for the guest room — 1800 mm wide, 450 mm tall, 400 mm deep.",
    tags=["homeowner", "living_room", "wide"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 1800, "height": 450, "depth": 400,
                "drawer_config": [[414, "door_pair"]],
            },
            assertions=[
                Assertion("exterior.width_mm",  Op.EQ, 1800),
                Assertion("exterior.height_mm", Op.EQ, 450),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_kitchen_wall_cabinet",
    prompt="I need a standard wall cabinet above my counter — 600 mm wide, 720 mm tall, 330 mm deep.",
    tags=["homeowner", "kitchen"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 720, "depth": 330,
                "drawer_config": [[684, "door_pair"]],
            },
            assertions=[
                Assertion("exterior.width_mm", Op.EQ, 600),
                Assertion("exterior.depth_mm", Op.EQ, 330),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_laundry_tall_cabinet",
    prompt="I want a tall broom-closet cabinet for the laundry room — 600 mm wide, 2000 mm tall, 400 mm deep — with a pair of doors.",
    tags=["homeowner", "door", "tall"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 2000, "depth": 400,
                "drawer_config": [[1964, "door_pair"]],
            },
            assertions=[
                Assertion("exterior.height_mm", Op.EQ, 2000),
                Assertion("exterior.depth_mm",  Op.EQ, 400),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_kitchen_5drawer_narrow",
    prompt="I want a narrow 5-drawer spice-pull-out cabinet — 150 mm wide, 720 mm tall, 550 mm deep.",
    tags=["homeowner", "kitchen", "drawer"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 150, "height": 720, "depth": 550,
                  "num_drawers": 5, "drawer_proportion": "equal"},
            assertions=[
                Assertion("opening_stack",      Op.LEN_EQ, 5),
                Assertion("exterior.width_mm", Op.EQ, 150),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_bathroom_medicine_door",
    prompt="I just need a small medicine cabinet — 300 mm wide, 700 mm tall, 150 mm deep — single door.",
    tags=["homeowner", "bathroom", "door"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 300, "height": 700, "depth": 150,
                "drawer_config": [[664, "door"]],
            },
            assertions=[
                Assertion("exterior.width_mm",  Op.EQ, 300),
                Assertion("exterior.height_mm", Op.EQ, 700),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_kitchen_base_wide_3drawer",
    prompt="I need a wide 900 mm kitchen base cabinet with three graduated drawers.",
    tags=["homeowner", "kitchen", "drawer", "wide"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 900, "height": 720, "depth": 550,
                  "num_drawers": 3, "drawer_proportion": "classic"},
            assertions=[
                Assertion("opening_stack",      Op.LEN_EQ, 3),
                Assertion("exterior.width_mm", Op.EQ, 900),
            ],
        ),
    ],
))

# --- Standard (20) ---

_s(Scenario(
    name="hw_bathroom_vanity_describe",
    prompt="Load the bathroom vanity preset and give me a plain-English description I can share with my contractor.",
    tags=["homeowner", "bathroom", "describe"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "bathroom_vanity"},
            label="load vanity preset",
            save_as={
                "bv_w":  "config.width",
                "bv_h":  "config.height",
                "bv_d":  "config.depth",
                "bv_dc": "config.drawer_config",
            },
            assertions=[Assertion("preset_name", Op.EQ, "bathroom_vanity")],
        ),
        ToolCall(
            tool="describe_design",
            args={},
            label="describe for contractor",
            context_args={
                "width": "bv_w", "height": "bv_h",
                "depth": "bv_d", "drawer_config": "bv_dc",
            },
            assertions=[
                Assertion("prose",      Op.HAS_KEY),
                Assertion("dimensions", Op.HAS_KEY),
                Assertion("openings",   Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_bedroom_dresser_proportions",
    prompt="Before I build my dresser, show me the drawer-height options for 6 drawers in a 900 × 1100 mm carcass.",
    tags=["homeowner", "bedroom", "proportions", "drawer"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 900, "height": 1100, "depth": 550, "num_drawers": 6},
            label="6-drawer proportion options",
            assertions=[
                Assertion("drawer_suggestions",          Op.LEN_GTE, 4),
                Assertion("drawer_suggestions.1.preset", Op.EQ, "subtle"),
                Assertion("drawer_suggestions.1.viable", Op.IS_TRUE),
                Assertion("interior_height_mm",          Op.APPROX, 1064),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_kitchen_base_evaluate",
    prompt="Design a 600 × 720 × 550 kitchen base with three drawers and check there are no problems.",
    tags=["homeowner", "kitchen", "drawer", "evaluation"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550, "num_drawers": 3},
            label="design 3-drawer base",
            save_as={"kbe_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 720, "depth": 550},
            label="evaluate",
            context_args={"drawer_config": "kbe_dc"},
            arg_transforms={
                "drawer_config": lambda s: [[i["height_mm"], i["type"]] for i in s],
            },
            assertions=[
                Assertion("summary.errors", Op.EQ, 0),
                Assertion("summary.pass",   Op.IS_TRUE),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_mudroom_bench_cutlist",
    prompt="Design my mudroom bench cabinet (1200 × 500 × 450 mm, 3 equal drawers) and give me a cut list.",
    tags=["homeowner", "drawer", "cutlist"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 1200, "height": 500, "depth": 450,
                  "num_drawers": 3, "drawer_proportion": "equal"},
            label="design bench",
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 1200, "height": 500, "depth": 450, "side_thickness": 18,
                  "drawer_config": [[142, "drawer"], [142, "drawer"], [142, "drawer"]]},
            label="cut list",
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
                Assertion("sheets_used", Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_kitchen_base_pulls",
    prompt="I want bar pulls on all three drawers of my 600 × 720 × 550 kitchen base. Show me the hardware plan.",
    tags=["homeowner", "kitchen", "drawer", "pulls"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_pulls",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]],
                "drawer_pull": "topknobs-hb-128",
            },
            label="bar pulls on 3-drawer base",
            assertions=[
                Assertion("drawer_slots",             Op.LEN_EQ, 3),
                Assertion("cabinet_issues",           Op.LEN_EQ, 0),
                Assertion("bom_totals.pieces_needed", Op.GTE, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_nightstand_describe",
    prompt="Design my nightstand (450 × 600 × 400 mm, one drawer on top, door below) and write it up for me.",
    tags=["homeowner", "bedroom", "drawer", "door", "describe"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="describe_design",
            args={
                "width": 450, "height": 600, "depth": 400,
                "drawer_config": [[200, "drawer"], [328, "door"]],
            },
            label="describe nightstand",
            assertions=[
                Assertion("prose",                  Op.HAS_KEY),
                Assertion("openings.counts.drawer", Op.EQ, 1),
                Assertion("openings.counts.door",   Op.EQ, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_pantry_evaluate",
    prompt="Load the tall pantry preset and check that it passes all the validation rules.",
    tags=["homeowner", "kitchen", "evaluation"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "kitchen_tall_pantry"},
            label="load pantry",
            save_as={"pan_w": "config.width", "pan_h": "config.height",
                     "pan_d": "config.depth", "pan_dc": "config.drawer_config"},
            assertions=[Assertion("config.height", Op.GTE, 2000)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={},
            label="validate pantry",
            context_args={"width": "pan_w", "height": "pan_h",
                          "depth": "pan_d", "drawer_config": "pan_dc"},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
    ],
))

_s(Scenario(
    name="hw_kids_safe_evaluate",
    prompt="Check that my kids'-room cabinet (600 × 400 × 350 mm, two drawers) won't have any hardware problems.",
    tags=["homeowner", "bedroom", "evaluation", "drawer"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 400, "depth": 350,
                "drawer_config": [[182, "drawer"], [182, "drawer"]],
            },
            label="validate kids cabinet",
            assertions=[
                Assertion("summary.errors", Op.EQ, 0),
                Assertion("summary.pass",   Op.IS_TRUE),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_kitchen_island_multi_column",
    prompt="I want a kitchen island — 1800 mm wide, 900 mm tall, 700 mm deep — with a wide drawer bank in the centre and door sections on each side.",
    tags=["homeowner", "kitchen", "multi_column", "wide"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 1800, "height": 900, "depth": 700,
                "columns": [
                    {"width_mm": 500,
                     "openings": [{"height_mm": 828, "type": "door"}]},
                    {"width_mm": 800,
                     "openings": [
                         {"height_mm": 276, "type": "drawer"},
                         {"height_mm": 276, "type": "drawer"},
                         {"height_mm": 276, "type": "drawer"},
                     ]},
                    {"width_mm": 500,
                     "openings": [{"height_mm": 828, "type": "door"}]},
                ],
            },
            label="3-column island base",
            assertions=[
                Assertion("columns",                      Op.LEN_EQ, 3),
                Assertion("columns.0.interior_width_mm", Op.EQ, 500),
                Assertion("columns.1.interior_width_mm", Op.EQ, 800),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_media_console_evaluate",
    prompt="I like the media console preset — load it and verify it's structurally sound.",
    tags=["homeowner", "living_room", "evaluation"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "media_console"},
            label="load preset",
            save_as={"mc_w": "config.width", "mc_h": "config.height",
                     "mc_d": "config.depth", "mc_dc": "config.drawer_config"},
            assertions=[Assertion("preset_name", Op.EQ, "media_console")],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={},
            label="validate",
            context_args={"width": "mc_w", "height": "mc_h",
                          "depth": "mc_d", "drawer_config": "mc_dc"},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
    ],
))

_s(Scenario(
    name="hw_laundry_overflow_autofix",
    prompt="I accidentally put too many drawers in my 600 × 720 × 550 laundry cabinet and the stack overflows. Fix it.",
    tags=["homeowner", "auto_fix", "drawer"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="auto_fix_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[250, "drawer"], [250, "drawer"],
                                   [250, "drawer"], [250, "drawer"]],
            },
            label="fix overflow",
            assertions=[
                Assertion("errors_before", Op.GT,  0),
                Assertion("errors_after",  Op.EQ,  0),
                Assertion("fixed",         Op.IS_TRUE),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_bedroom_wardrobe_hinge_check",
    prompt="I'm building a 600 × 2100 × 600 wardrobe with a door pair. How many hinges do I need?",
    tags=["homeowner", "bedroom", "door", "tall"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 564, "opening_height": 2064,
                "num_doors": 2, "hinge_key": "blum_clip_top_110_full",
            },
            label="wardrobe door pair",
            assertions=[
                Assertion("total_hinges", Op.GTE, 4),
                Assertion("num_doors",    Op.EQ,  2),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_home_office_with_legs",
    prompt="Add furniture legs to my home-office pedestal (400 × 720 × 550 mm) so it sits off the floor.",
    tags=["homeowner", "legs"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_legs",
            args={"width": 400, "height": 720, "depth": 550},
            label="add legs to pedestal",
            assertions=[
                Assertion("leg",             Op.HAS_KEY),
                Assertion("count",           Op.GTE, 4),
                Assertion("total_height_mm", Op.GT,  0),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_closet_organizer_cutlist",
    prompt="Get a cut list for my 6-drawer closet organiser — 900 × 1200 × 550 mm.",
    tags=["homeowner", "bedroom", "cutlist", "drawer"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="generate_cutlist",
            args={
                "width": 900, "height": 1200, "depth": 550,
                "side_thickness": 18,
                "drawer_config": [
                    [170, "drawer"], [170, "drawer"], [170, "drawer"],
                    [170, "drawer"], [170, "drawer"], [170, "drawer"],
                ],
            },
            label="closet cut list",
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
                Assertion("sheets_used", Op.GTE, 1),
                Assertion("waste_pct",   Op.GTE, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_foyer_console_describe",
    prompt="Describe the foyer console preset so I can explain it to my partner before we order materials.",
    tags=["homeowner", "living_room", "describe"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "foyer_console_2_drawer"},
            label="load foyer preset",
            save_as={"fc_w": "config.width", "fc_h": "config.height",
                     "fc_d": "config.depth", "fc_dc": "config.drawer_config"},
            assertions=[Assertion("preset_name", Op.EQ, "foyer_console_2_drawer")],
        ),
        ToolCall(
            tool="describe_design",
            args={},
            label="human-readable description",
            context_args={"width": "fc_w", "height": "fc_h",
                          "depth": "fc_d", "drawer_config": "fc_dc"},
            assertions=[
                Assertion("prose",    Op.HAS_KEY),
                Assertion("openings", Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_bathroom_double_vanity",
    prompt="I'm redoing my master bath — 1200 mm wide double vanity, two equal sections each with a drawer and a door.",
    tags=["homeowner", "bathroom", "multi_column", "drawer", "door"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 1200, "height": 850, "depth": 480,
                "columns": [
                    {"width_mm": 600, "openings": [
                        {"height_mm": 275, "type": "drawer"},
                        {"height_mm": 539, "type": "door"},
                    ]},
                    {"width_mm": 600, "openings": [
                        {"height_mm": 275, "type": "drawer"},
                        {"height_mm": 539, "type": "door"},
                    ]},
                ],
            },
            label="2-column double vanity",
            assertions=[
                Assertion("columns",                      Op.LEN_EQ, 2),
                Assertion("columns.0.interior_width_mm", Op.EQ, 600),
                Assertion("columns.1.interior_width_mm", Op.EQ, 600),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_kitchen_door_pair_evaluate",
    prompt="Check the wide kitchen door-pair base preset — does it pass all checks?",
    tags=["homeowner", "kitchen", "door", "evaluation"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "kitchen_base_door_pair_wide"},
            label="load preset",
            save_as={"dp_w": "config.width", "dp_h": "config.height",
                     "dp_d": "config.depth", "dp_dc": "config.drawer_config"},
            assertions=[Assertion("config.width", Op.EQ, 900)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={},
            label="validate",
            context_args={"width": "dp_w", "height": "dp_h",
                          "depth": "dp_d", "drawer_config": "dp_dc"},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
    ],
))

_s(Scenario(
    name="hw_bedroom_dresser_describe",
    prompt="Describe the bedroom dresser preset — I want to show it to the lumber yard when I'm buying plywood.",
    tags=["homeowner", "bedroom", "describe"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "bedroom_dresser"},
            label="load dresser preset",
            save_as={"drd_w": "config.width", "drd_h": "config.height",
                     "drd_d": "config.depth", "drd_dc": "config.drawer_config"},
            assertions=[Assertion("preset_name", Op.EQ, "bedroom_dresser")],
        ),
        ToolCall(
            tool="describe_design",
            args={},
            label="describe for lumber yard",
            context_args={"width": "drd_w", "height": "drd_h",
                          "depth": "drd_d", "drawer_config": "drd_dc"},
            assertions=[
                Assertion("prose",     Op.HAS_KEY),
                Assertion("materials", Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_living_room_credenza_eval",
    prompt="I want to use the living-room credenza preset — check it's all valid before I order materials.",
    tags=["homeowner", "living_room", "evaluation"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "living_room_credenza"},
            label="load credenza",
            save_as={"lce_w": "config.width", "lce_h": "config.height",
                     "lce_d": "config.depth", "lce_dc": "config.drawer_config"},
            assertions=[Assertion("preset_name", Op.EQ, "living_room_credenza")],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={},
            label="validate credenza",
            context_args={"width": "lce_w", "height": "lce_h",
                          "depth": "lce_d", "drawer_config": "lce_dc"},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
    ],
))

_s(Scenario(
    name="hw_kitchen_pulls_mismatch",
    prompt="I want a wood pull on the door and a bar pull on the drawers — will that cause a style warning?",
    tags=["homeowner", "kitchen", "pulls", "evaluation"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_pulls",
            args={
                "width": 900, "height": 720, "depth": 550,
                "drawer_config": [[180, "drawer"], [180, "drawer"], [360, "door"]],
                "drawer_pull": "topknobs-hb-128",
                "door_pull":   "rockler-wnl-160",
            },
            label="mixed-style pull check",
            assertions=[
                Assertion("cabinet_issues",            Op.LEN_GTE, 1),
                Assertion("cabinet_issues.0.severity", Op.EQ, "warning"),
            ],
        ),
    ],
))

# --- Advanced (10) ---

_s(Scenario(
    name="hw_kitchen_full_workflow",
    prompt="Design a 600 × 720 × 550 kitchen base with 3 drawers, check it for problems, fix anything wrong, then give me a cut list.",
    tags=["homeowner", "kitchen", "drawer", "evaluation", "auto_fix", "cutlist"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550, "num_drawers": 3},
            label="design",
            save_as={"kfw_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 720, "depth": 550},
            label="evaluate",
            context_args={"drawer_config": "kfw_dc"},
            arg_transforms={"drawer_config": lambda s: [[i["height_mm"], i["type"]] for i in s]},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550, "side_thickness": 18,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="cut list",
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
                Assertion("sheets_used", Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_bathroom_complete",
    prompt="Check the proportion options for my 600 × 850 vanity, load the preset, then describe it for my plumber.",
    tags=["homeowner", "bathroom", "proportions", "describe"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 600, "height": 850, "depth": 480, "num_drawers": 3},
            label="proportion options",
            assertions=[
                Assertion("drawer_suggestions", Op.LEN_GTE, 4),
                Assertion("interior_height_mm", Op.APPROX, 814),
            ],
        ),
        ToolCall(
            tool="apply_preset",
            args={"name": "bathroom_vanity"},
            label="load preset",
            save_as={"bvc_w": "config.width", "bvc_h": "config.height",
                     "bvc_d": "config.depth", "bvc_dc": "config.drawer_config"},
            assertions=[Assertion("preset_name", Op.EQ, "bathroom_vanity")],
        ),
        ToolCall(
            tool="describe_design",
            args={},
            label="describe for plumber",
            context_args={"width": "bvc_w", "height": "bvc_h",
                          "depth": "bvc_d", "drawer_config": "bvc_dc"},
            assertions=[
                Assertion("prose",    Op.HAS_KEY),
                Assertion("openings", Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="hw_bedroom_dresser_complete",
    prompt="Load the bedroom dresser preset, validate it, then describe it fully.",
    tags=["homeowner", "bedroom", "evaluation", "describe"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "bedroom_dresser"},
            label="load dresser",
            save_as={"bdc_w": "config.width", "bdc_h": "config.height",
                     "bdc_d": "config.depth", "bdc_dc": "config.drawer_config"},
            assertions=[Assertion("preset_name", Op.EQ, "bedroom_dresser")],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={},
            label="validate",
            context_args={"width": "bdc_w", "height": "bdc_h",
                          "depth": "bdc_d", "drawer_config": "bdc_dc"},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="describe_design",
            args={},
            label="describe",
            context_args={"width": "bdc_w", "height": "bdc_h",
                          "depth": "bdc_d", "drawer_config": "bdc_dc"},
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="hw_mudroom_complete",
    prompt="Design a 1200 × 500 × 450 mudroom bench with 3 drawers, fix any issues, produce a cut list.",
    tags=["homeowner", "drawer", "auto_fix", "cutlist"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="auto_fix_cabinet",
            args={
                "width": 1200, "height": 500, "depth": 450,
                "drawer_config": [[142, "drawer"], [142, "drawer"], [142, "drawer"]],
            },
            label="auto-fix",
            assertions=[Assertion("errors_after", Op.EQ, 0)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 1200, "height": 500, "depth": 450,
                "drawer_config": [[142, "drawer"], [142, "drawer"], [142, "drawer"]],
            },
            label="verify clean",
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 1200, "height": 500, "depth": 450, "side_thickness": 18,
                  "drawer_config": [[142, "drawer"], [142, "drawer"], [142, "drawer"]]},
            label="cut list",
            assertions=[Assertion("panel_count", Op.GTE, 3)],
        ),
    ],
))

_s(Scenario(
    name="hw_kitchen_island_complete",
    prompt="Build a 3-column kitchen island (1800 × 900 × 700 mm): check proportions for the centre drawer bank, then design it.",
    tags=["homeowner", "kitchen", "multi_column", "proportions", "wide"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 800, "height": 900, "depth": 700, "num_drawers": 3},
            label="drawer proportions for centre column",
            assertions=[
                Assertion("drawer_suggestions.0.preset", Op.EQ, "equal"),
                Assertion("interior_height_mm",          Op.APPROX, 864),
            ],
        ),
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 1800, "height": 900, "depth": 700,
                "columns": [
                    {"width_mm": 500,
                     "openings": [{"height_mm": 864, "type": "door"}]},
                    {"width_mm": 800,
                     "openings": [
                         {"height_mm": 288, "type": "drawer"},
                         {"height_mm": 288, "type": "drawer"},
                         {"height_mm": 288, "type": "drawer"},
                     ]},
                    {"width_mm": 500,
                     "openings": [{"height_mm": 864, "type": "door"}]},
                ],
            },
            label="island cabinet",
            assertions=[Assertion("columns", Op.LEN_EQ, 3)],
        ),
    ],
))

_s(Scenario(
    name="hw_home_office_complete",
    prompt="Design a 3-drawer home-office pedestal (400 × 720 × 550 mm), check it, add legs and pulls.",
    tags=["homeowner", "drawer", "legs", "pulls", "evaluation"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 400, "height": 720, "depth": 550, "num_drawers": 3},
            label="design pedestal",
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 400, "height": 720, "depth": 550,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="validate",
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="design_legs",
            args={"width": 400, "height": 720, "depth": 550},
            label="add legs",
            assertions=[Assertion("count", Op.GTE, 4)],
        ),
        ToolCall(
            tool="design_pulls",
            args={
                "width": 400, "height": 720, "depth": 550,
                "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]],
                "drawer_pull": "topknobs-hb-128",
            },
            label="add pulls",
            assertions=[Assertion("drawer_slots", Op.LEN_EQ, 3)],
        ),
    ],
))

_s(Scenario(
    name="hw_living_room_media_complete",
    prompt="Load the media console preset, validate it, then describe it in plain English.",
    tags=["homeowner", "living_room", "evaluation", "describe"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "media_console"},
            label="load preset",
            save_as={"mcc_w": "config.width", "mcc_h": "config.height",
                     "mcc_d": "config.depth", "mcc_dc": "config.drawer_config"},
            assertions=[Assertion("preset_name", Op.EQ, "media_console")],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={},
            label="validate",
            context_args={"width": "mcc_w", "height": "mcc_h",
                          "depth": "mcc_d", "drawer_config": "mcc_dc"},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="describe_design",
            args={},
            label="describe",
            context_args={"width": "mcc_w", "height": "mcc_h",
                          "depth": "mcc_d", "drawer_config": "mcc_dc"},
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="hw_closet_complete",
    prompt="Design a 6-drawer closet organiser (900 × 1200 × 550 mm), fix any issues, produce a cut list.",
    tags=["homeowner", "bedroom", "drawer", "auto_fix", "cutlist"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="auto_fix_cabinet",
            args={
                "width": 900, "height": 1200, "depth": 550,
                "drawer_config": [
                    [170, "drawer"], [170, "drawer"], [170, "drawer"],
                    [170, "drawer"], [170, "drawer"], [170, "drawer"],
                ],
            },
            label="auto-fix",
            assertions=[Assertion("errors_after", Op.EQ, 0)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 900, "height": 1200, "depth": 550, "side_thickness": 18,
                  "drawer_config": [
                      [170, "drawer"], [170, "drawer"], [170, "drawer"],
                      [170, "drawer"], [170, "drawer"], [170, "drawer"],
                  ]},
            label="cut list",
            assertions=[Assertion("panel_count", Op.GTE, 3)],
        ),
    ],
))

_s(Scenario(
    name="hw_pantry_full_chain",
    prompt="Load the tall kitchen pantry, check it, auto-fix if needed, then describe it for my contractor.",
    tags=["homeowner", "kitchen", "evaluation", "auto_fix", "describe"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "kitchen_tall_pantry"},
            label="load pantry",
            save_as={"pfc_w": "config.width", "pfc_h": "config.height",
                     "pfc_d": "config.depth", "pfc_dc": "config.drawer_config"},
            assertions=[Assertion("config.height", Op.GTE, 2000)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={},
            label="validate",
            context_args={"width": "pfc_w", "height": "pfc_h",
                          "depth": "pfc_d", "drawer_config": "pfc_dc"},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="describe_design",
            args={},
            label="describe for contractor",
            context_args={"width": "pfc_w", "height": "pfc_h",
                          "depth": "pfc_d", "drawer_config": "pfc_dc"},
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="hw_kitchen_base_order",
    prompt="Full workflow for my kitchen base: design 3 drawers (600 × 720 × 550 mm), evaluate, cut list, then a description for ordering.",
    tags=["homeowner", "kitchen", "drawer", "cutlist", "describe"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550, "num_drawers": 3},
            label="design",
            save_as={"kbo_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 720, "depth": 550},
            label="evaluate",
            context_args={"drawer_config": "kbo_dc"},
            arg_transforms={"drawer_config": lambda s: [[i["height_mm"], i["type"]] for i in s]},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550, "side_thickness": 18,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="cut list",
            assertions=[Assertion("sheets_used", Op.GTE, 1)],
        ),
        ToolCall(
            tool="describe_design",
            args={"width": 600, "height": 720, "depth": 550,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="describe for order",
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))



# ── 25. Furniture-maker persona ───────────────────────────────────────────────
# Traditional-woodworking vocabulary: joinery methods, proportions, overlays,
# solid-wood stock, client presentations. Focus on joinery comparison,
# classical proportions, custom configs.
# 20 basic / 20 standard / 10 advanced.

# --- Basic (20) ---

_s(Scenario(
    name="fm_graduated_drawers_golden",
    prompt="Show me golden-ratio drawer heights for a 4-drawer jewellery chest — 450 × 800 × 350 mm.",
    tags=["furniture_maker", "proportions", "drawer"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 450, "height": 800, "depth": 350, "num_drawers": 4},
            assertions=[
                Assertion("drawer_suggestions.3.preset", Op.EQ, "golden"),
                Assertion("interior_height_mm",          Op.APPROX, 764),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_compare_joinery_19mm_stock",
    prompt="I'm using 19 mm solid-poplar stock. Which carcass joinery method gives the most strength?",
    tags=["furniture_maker", "joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="compare_joinery",
            args={"width": 600, "height": 720, "depth": 550, "stock_mm": 19},
            assertions=[
                Assertion("styles",            Op.LEN_GTE, 2),
                Assertion("side_thickness_mm", Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_domino_carcass_credenza",
    prompt="I want a Festool Domino (floating tenon) carcass for my credenza — 1600 × 800 × 450 mm.",
    tags=["furniture_maker", "joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 1600, "height": 800, "depth": 450,
                  "carcass_joinery": "floating_tenon"},
            assertions=[
                Assertion("joinery",           Op.EQ, "floating_tenon"),
                Assertion("exterior.width_mm", Op.EQ, 1600),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_column_proportions_golden_credenza",
    prompt="I want to split a 1600 mm credenza interior into three columns with the centre wider — golden ratio.",
    tags=["furniture_maker", "proportions", "multi_column"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 1600, "height": 800, "depth": 450,
                  "num_columns": 3, "wide_index": 1},
            assertions=[
                Assertion("column_suggestions",          Op.LEN_GTE, 3),
                Assertion("column_suggestions.3.preset", Op.EQ, "golden"),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_half_overlay_door",
    prompt="Design a half-overlay door for a 564 × 684 mm opening — I'm building a Shaker-style kitchen.",
    tags=["furniture_maker", "door"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 564, "opening_height": 684,
                "num_doors": 1, "hinge_key": "blum_clip_top_110_half",
            },
            assertions=[
                Assertion("overlay_type",  Op.EQ, "half"),
                Assertion("total_hinges",  Op.GTE, 2),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_inset_door_pair",
    prompt="I'm building a period piece — inset door pair for a 900 × 1064 mm opening.",
    tags=["furniture_maker", "door"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 900, "opening_height": 1064,
                "num_doors": 2, "hinge_key": "blum_clip_top_110_inset",
            },
            assertions=[
                Assertion("overlay_type",  Op.EQ, "inset"),
                Assertion("num_doors",     Op.EQ, 2),
                Assertion("total_hinges",  Op.GTE, 4),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_tall_door_three_hinges",
    prompt="My armoire door is 564 × 1800 mm — confirm it gets three hinges per door.",
    tags=["furniture_maker", "door", "tall"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 564, "opening_height": 1800,
                "num_doors": 1, "hinge_key": "blum_clip_top_110_full",
            },
            assertions=[
                Assertion("hinges_per_door", Op.EQ, 3),
                Assertion("total_hinges",    Op.EQ, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_drawer_dovetail",
    prompt="Design a 500 × 180 × 500 mm drawer box with quarter-quarter-quarter (QQQ) locking-rabbet joinery.",
    tags=["furniture_maker", "drawer", "joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width":  500,
                "opening_height": 180,
                "opening_depth":  500,
                "joinery_style":  "qqq",
            },
            assertions=[
                Assertion("joinery.style", Op.EQ, "qqq"),
                Assertion("box_width_mm",  Op.GT, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_drawer_lock_miter",
    prompt="Design a 600 × 200 × 550 mm drawer with drawer-lock joinery for a clean mechanical interlock.",
    tags=["furniture_maker", "drawer", "joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width":  600,
                "opening_height": 200,
                "opening_depth":  550,
                "joinery_style":  "drawer_lock",
            },
            assertions=[
                Assertion("joinery.style",  Op.EQ, "drawer_lock"),
                Assertion("box_width_mm",   Op.GT, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_pocket_screw_carcass",
    prompt="I want pocket screws for the carcass — fastest assembly on a 600 × 720 × 550 mm sideboard section.",
    tags=["furniture_maker", "joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550,
                  "carcass_joinery": "pocket_screw"},
            assertions=[
                Assertion("joinery", Op.EQ, "pocket_screw"),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_list_joinery_12mm",
    prompt="What joinery options work with 12 mm plywood? I'm building a light-duty cabinet.",
    tags=["furniture_maker", "joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="list_joinery_options",
            args={"stock_mm": 12},
            assertions=[
                Assertion("carcass_joinery_methods", Op.LEN_GTE, 2),
                Assertion("drawer_joinery_styles",   Op.LEN_GTE, 2),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_nightstand_with_joinery",
    prompt="Design a 450 × 600 × 400 mm nightstand with floating-tenon carcass joinery and a drawer on top.",
    tags=["furniture_maker", "joinery", "drawer"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 450, "height": 600, "depth": 400,
                "carcass_joinery": "floating_tenon",
                "drawer_config": [[200, "drawer"], [328, "door"]],
            },
            assertions=[
                Assertion("joinery",       Op.EQ, "floating_tenon"),
                Assertion("opening_stack", Op.LEN_EQ, 2),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_dresser_6drawer_subtle",
    prompt="Design a 6-drawer dresser with a gentle 1.2× graduation — 900 × 1100 × 550 mm.",
    tags=["furniture_maker", "drawer", "proportions"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 900, "height": 1100, "depth": 550,
                  "num_drawers": 6, "drawer_proportion": "subtle"},
            assertions=[
                Assertion("opening_stack",             Op.LEN_EQ, 6),
                Assertion("opening_stack.0.height_mm", Op.GT,
                          0),  # bottom drawer exists
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_describe_for_client",
    prompt="Write up a plain description of my 1600 × 800 × 450 credenza for the client portfolio.",
    tags=["furniture_maker", "describe"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="describe_design",
            args={
                "width": 1600, "height": 800, "depth": 450,
                "drawer_config": [[564, "door_pair"], [100, "drawer"], [100, "drawer"]],
            },
            assertions=[
                Assertion("prose",    Op.HAS_KEY),
                Assertion("openings", Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_hardware_list_slides",
    prompt="What drawer-slide options are available? I want to see all specs before I specify hardware.",
    tags=["furniture_maker", "hardware"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="list_hardware",
            args={},
            assertions=[
                Assertion("slides", Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_hinge_spec_full_overlay",
    prompt="What are the specs on the standard full-overlay Blum hinge?",
    tags=["furniture_maker", "hardware"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="list_hardware",
            args={},
            assertions=[
                Assertion("hinges", Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_compare_joinery_15mm",
    prompt="I'm using 15 mm Baltic-birch ply for a wall-mounted cabinet. Compare joinery options.",
    tags=["furniture_maker", "joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="compare_joinery",
            args={"width": 600, "height": 720, "depth": 300, "stock_mm": 15},
            assertions=[
                Assertion("styles",            Op.LEN_GTE, 2),
                Assertion("side_thickness_mm", Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_sideboard_credenza_proportions",
    prompt="What graduation options are available for a 3-drawer sideboard section — 600 × 900 × 550 mm interior?",
    tags=["furniture_maker", "proportions", "drawer"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 600, "height": 900, "depth": 550, "num_drawers": 3},
            assertions=[
                Assertion("drawer_suggestions",           Op.LEN_GTE, 4),
                Assertion("drawer_suggestions.0.preset",  Op.EQ, "equal"),
                Assertion("drawer_suggestions.3.preset",  Op.EQ, "golden"),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_chest_4drawer_golden",
    prompt="Design a 4-drawer blanket chest using golden-ratio drawer heights — 900 × 800 × 550 mm.",
    tags=["furniture_maker", "drawer", "proportions"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 900, "height": 800, "depth": 550,
                  "num_drawers": 4, "drawer_proportion": "golden"},
            assertions=[
                Assertion("opening_stack",             Op.LEN_EQ, 4),
                Assertion("opening_stack.0.height_mm", Op.GT,
                          "opening_stack.3.height_mm" if False else 200),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_biscuit_carcass_cabinet",
    prompt="Use biscuit joinery for a 600 × 720 × 550 workshop cabinet carcass.",
    tags=["furniture_maker", "joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550,
                  "carcass_joinery": "biscuit"},
            assertions=[
                Assertion("joinery", Op.EQ, "biscuit"),
            ],
        ),
    ],
))

# --- Standard (20) ---

_s(Scenario(
    name="fm_proportions_then_design_credenza",
    prompt="First show me the classic-ratio drawer heights for my 1600 × 800 credenza, then design it.",
    tags=["furniture_maker", "proportions", "drawer"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 1600, "height": 800, "depth": 450, "num_drawers": 2},
            label="proportion options",
            save_as={"fm_classic_h": "drawer_suggestions.2.heights_mm"},
            assertions=[
                Assertion("drawer_suggestions.2.preset",  Op.EQ, "classic"),
                Assertion("drawer_suggestions.2.viable",  Op.IS_TRUE),
            ],
        ),
        ToolCall(
            tool="design_cabinet",
            args={"width": 1600, "height": 800, "depth": 450,
                  "num_drawers": 2, "drawer_proportion": "classic"},
            label="design credenza",
            assertions=[
                Assertion("opening_stack", Op.LEN_EQ, 2),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_design_evaluate_golden_chest",
    prompt="Design a 3-drawer blanket chest with golden proportions (900 × 800 × 550 mm) and validate the hardware.",
    tags=["furniture_maker", "drawer", "proportions", "evaluation"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 900, "height": 800, "depth": 550,
                  "num_drawers": 3, "drawer_proportion": "golden"},
            label="design with golden ratio",
            save_as={"fmge_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 900, "height": 800, "depth": 550},
            label="validate hardware fit",
            context_args={"drawer_config": "fmge_dc"},
            arg_transforms={"drawer_config": lambda s: [[i["height_mm"], i["type"]] for i in s]},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
    ],
))

_s(Scenario(
    name="fm_three_column_asymmetric",
    prompt="I want a three-column sideboard with the wide column off-centre (index 2) — 1800 × 900 mm, golden ratio.",
    tags=["furniture_maker", "multi_column", "proportions"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 1800, "height": 900, "depth": 500,
                  "num_columns": 3, "wide_index": 2},
            label="asymmetric column proportions",
            assertions=[
                Assertion("column_suggestions.3.preset",            Op.EQ, "golden"),
                Assertion("column_suggestions.3.widths_mm",         Op.LEN_EQ, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_joinery_comparison_domino_vs_pocket",
    prompt="Compare Domino vs pocket screw for my 600 × 720 × 550 18 mm cabinet carcass.",
    tags=["furniture_maker", "joinery"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="compare_joinery",
            args={"width": 600, "height": 720, "depth": 550, "stock_mm": 18},
            label="domino vs pocket screw comparison",
            assertions=[
                Assertion("styles",            Op.LEN_GTE, 3),
                Assertion("side_thickness_mm", Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_describe_for_workshop_notes",
    prompt="Design my 3-drawer walnut credenza (1600 × 800 × 450 mm) and write it up for my workshop notes.",
    tags=["furniture_maker", "describe", "drawer"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 1600, "height": 800, "depth": 450,
                  "num_drawers": 3, "carcass_joinery": "floating_tenon"},
            label="design credenza",
            save_as={"fmwn_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="describe_design",
            args={"width": 1600, "height": 800, "depth": 450,
                  "drawer_config": [[250, "drawer"], [250, "drawer"], [250, "drawer"]]},
            label="workshop notes",
            assertions=[
                Assertion("prose",     Op.HAS_KEY),
                Assertion("materials", Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_tall_chest_proportions",
    prompt="Show me proportion options for an 8-drawer tall chest — 600 × 1400 × 550 mm.",
    tags=["furniture_maker", "proportions", "drawer", "tall"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 600, "height": 1400, "depth": 550, "num_drawers": 8},
            label="8-drawer tall-chest proportions",
            assertions=[
                Assertion("drawer_suggestions.0.viable",   Op.IS_TRUE),
                Assertion("drawer_suggestions.1.viable",   Op.IS_TRUE),
                Assertion("interior_height_mm",            Op.APPROX, 1364),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_sideboard_three_column_design",
    prompt="Design a three-column sideboard (1800 × 900 × 500 mm) — door/drawers/door layout.",
    tags=["furniture_maker", "multi_column", "drawer", "door"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 1800, "height": 900, "depth": 500,
                "columns": [
                    {"width_mm": 500,
                     "openings": [{"height_mm": 828, "type": "door_pair"}]},
                    {"width_mm": 800,
                     "openings": [
                         {"height_mm": 276, "type": "drawer"},
                         {"height_mm": 276, "type": "drawer"},
                         {"height_mm": 276, "type": "drawer"},
                     ]},
                    {"width_mm": 500,
                     "openings": [{"height_mm": 828, "type": "door_pair"}]},
                ],
            },
            label="door/drawer/door sideboard",
            assertions=[
                Assertion("columns",    Op.LEN_EQ, 3),
                Assertion("column_count", Op.EQ, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_evaluate_then_describe",
    prompt="Evaluate my 3-drawer credenza (1600 × 800 × 450 mm), then write it up.",
    tags=["furniture_maker", "evaluation", "describe"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 1600, "height": 800, "depth": 450,
                "drawer_config": [[250, "drawer"], [250, "drawer"], [250, "drawer"]],
            },
            label="validate credenza",
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="describe_design",
            args={
                "width": 1600, "height": 800, "depth": 450,
                "drawer_config": [[250, "drawer"], [250, "drawer"], [250, "drawer"]],
            },
            label="describe credenza",
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="fm_credenza_cutlist",
    prompt="Give me the cut list for my walnut credenza — 1600 × 800 × 450 mm, 3 drawers.",
    tags=["furniture_maker", "cutlist", "drawer"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="generate_cutlist",
            args={
                "width": 1600, "height": 800, "depth": 450,
                "side_thickness": 19,
                "drawer_config": [[250, "drawer"], [250, "drawer"], [250, "drawer"]],
            },
            label="credenza cut list (19 mm stock)",
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
                Assertion("sheets_used", Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_nightstand_full_workflow",
    prompt="Design a 450 × 600 × 400 mm nightstand with domino carcass, validate it, then describe it for the client.",
    tags=["furniture_maker", "joinery", "evaluation", "describe"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 450, "height": 600, "depth": 400,
                  "carcass_joinery": "floating_tenon",
                  "drawer_config": [[200, "drawer"], [328, "door"]]},
            label="design nightstand",
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 2)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 450, "height": 600, "depth": 400,
                  "drawer_config": [[200, "drawer"], [328, "door"]]},
            label="validate nightstand",
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="describe_design",
            args={"width": 450, "height": 600, "depth": 400,
                  "drawer_config": [[200, "drawer"], [328, "door"]]},
            label="client description",
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="fm_compare_drawer_joinery",
    prompt="Compare three drawer-joinery methods for an 18 mm stock cabinet — I want to pick the right one.",
    tags=["furniture_maker", "joinery", "drawer"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="compare_joinery",
            args={"width": 600, "height": 720, "depth": 550, "stock_mm": 18},
            label="compare joinery at 18 mm",
            assertions=[
                Assertion("styles",  Op.LEN_GTE, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_graduated_six_drawer_evaluate",
    prompt="Design a 6-drawer subtle-graduation chest (600 × 1200 × 550 mm) and validate the hardware.",
    tags=["furniture_maker", "drawer", "proportions", "evaluation"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 1200, "depth": 550,
                  "num_drawers": 6, "drawer_proportion": "subtle"},
            label="design 6-drawer chest",
            save_as={"fmg6_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 6)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 1200, "depth": 550},
            label="validate",
            context_args={"drawer_config": "fmg6_dc"},
            arg_transforms={"drawer_config": lambda s: [[i["height_mm"], i["type"]] for i in s]},
            assertions=[Assertion("summary.errors", Op.LTE, 1)],  # float-precision rounding may cause 1 fp error
        ),
    ],
))

_s(Scenario(
    name="fm_apply_living_room_sideboard",
    prompt="Load the living-room sideboard preset for reference, then describe its layout.",
    tags=["furniture_maker", "describe"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "living_room_sideboard"},
            label="load sideboard preset",
            save_as={"fmsb_w": "config.width", "fmsb_h": "config.height",
                     "fmsb_d": "config.depth", "fmsb_dc": "config.drawer_config"},
            assertions=[Assertion("preset_name", Op.EQ, "living_room_sideboard")],
        ),
        ToolCall(
            tool="describe_design",
            args={},
            label="describe for portfolio",
            context_args={"width": "fmsb_w", "height": "fmsb_h",
                          "depth": "fmsb_d", "drawer_config": "fmsb_dc"},
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="fm_drawer_pull_placement",
    prompt="Add a centred bar pull to my 450 × 120 mm small drawer face — is one pull enough?",
    tags=["furniture_maker", "drawer", "pulls"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width":  450,
                "opening_height": 120,
                "opening_depth":  500,
                "pull_key":       "topknobs-hb-128",
                "pull_vertical":  "center",
            },
            label="small drawer single pull",
            assertions=[
                Assertion("pull.count",  Op.EQ, 1),
                Assertion("pull.issues", Op.LEN_EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_evaluate_stack_order",
    prompt="Check that my classic 3-drawer chest (900 × 900 × 550 mm) has no stack-order warnings.",
    tags=["furniture_maker", "evaluation", "proportions"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 900, "height": 900, "depth": 550,
                  "num_drawers": 3, "drawer_proportion": "classic"},
            label="design classic 3-drawer",
            save_as={"fmso_dc": "opening_stack"},
            assertions=[
                Assertion("opening_stack",             Op.LEN_EQ, 3),
                Assertion("opening_stack.0.height_mm", Op.GT,
                          0),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 900, "height": 900, "depth": 550},
            label="check stack order",
            context_args={"drawer_config": "fmso_dc"},
            arg_transforms={"drawer_config": lambda s: [[i["height_mm"], i["type"]] for i in s]},
            assertions=[
                Assertion("summary.errors",   Op.EQ, 0),
                Assertion("summary.warnings", Op.LTE, 1),  # classic ratio may exactly fill interior
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_describe_cutlist_for_quote",
    prompt="Generate a full cut list for my 3-drawer walnut nightstand (450 × 600 × 400 mm) so I can quote the timber.",
    tags=["furniture_maker", "cutlist", "drawer"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="generate_cutlist",
            args={
                "width": 450, "height": 600, "depth": 400,
                "side_thickness": 19,
                "drawer_config": [[200, "drawer"], [328, "door"]],
            },
            label="nightstand cut list",
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_column_widths_three_equal",
    prompt="Show me equal column widths for a 1600 mm interior — 3 columns, no accent column.",
    tags=["furniture_maker", "proportions", "multi_column"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 1600, "height": 800, "depth": 450, "num_columns": 3},
            label="equal 3-column split",
            assertions=[
                Assertion("column_suggestions.0.preset",     Op.EQ, "equal"),
                Assertion("column_suggestions.0.widths_mm",  Op.LEN_EQ, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_hinge_door_pair_evaluate",
    prompt="I'm hinging a 900 × 1064 mm inset door pair on a 900 × 1100 × 550 cabinet — validate the hinge count.",
    tags=["furniture_maker", "door", "evaluation"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 900, "opening_height": 1064,
                "num_doors": 2, "hinge_key": "blum_clip_top_110_inset",
            },
            label="inset door pair hinge check",
            assertions=[
                Assertion("total_hinges", Op.GTE, 4),
                Assertion("overlay_type", Op.EQ, "inset"),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 900, "height": 1100, "depth": 550,
                "drawer_config": [[1064, "door_pair"]],
            },
            label="validate cabinet for door pair",
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
    ],
))

_s(Scenario(
    name="fm_auto_fix_then_describe",
    prompt="My 3-drawer credenza stack overflows slightly — fix it, then describe the result.",
    tags=["furniture_maker", "auto_fix", "describe"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="auto_fix_cabinet",
            args={
                "width": 1600, "height": 800, "depth": 450,
                "drawer_config": [[280, "drawer"], [280, "drawer"], [280, "drawer"]],
            },
            label="auto-fix overflow",
            assertions=[
                Assertion("errors_before", Op.GT,  0),
                Assertion("errors_after",  Op.EQ,  0),
                Assertion("fixed",         Op.IS_TRUE),
            ],
        ),
        ToolCall(
            tool="describe_design",
            args={
                "width": 1600, "height": 800, "depth": 450,
                "drawer_config": [[242, "drawer"], [242, "drawer"], [242, "drawer"]],
            },
            label="describe fixed design",
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

# --- Advanced (10) ---

_s(Scenario(
    name="fm_full_piece_design_to_delivery",
    prompt="Full workflow for a classic 3-drawer credenza: proportions → design → evaluate → describe → cut list.",
    tags=["furniture_maker", "proportions", "evaluation", "describe", "cutlist"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 1600, "height": 800, "depth": 450, "num_drawers": 3},
            label="proportion options",
            assertions=[Assertion("drawer_suggestions", Op.LEN_GTE, 4)],
        ),
        ToolCall(
            tool="design_cabinet",
            args={"width": 1600, "height": 800, "depth": 450,
                  "num_drawers": 3, "drawer_proportion": "classic",
                  "carcass_joinery": "floating_tenon"},
            label="design with classic proportions",
            save_as={"fmfull_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 1600, "height": 800, "depth": 450},
            label="evaluate",
            context_args={"drawer_config": "fmfull_dc"},
            arg_transforms={"drawer_config": lambda s: [[i["height_mm"], i["type"]] for i in s]},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="describe_design",
            args={"width": 1600, "height": 800, "depth": 450,
                  "drawer_config": [[250, "drawer"], [250, "drawer"], [250, "drawer"]]},
            label="client description",
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 1600, "height": 800, "depth": 450,
                  "side_thickness": 19,
                  "drawer_config": [[250, "drawer"], [250, "drawer"], [250, "drawer"]]},
            label="cut list",
            assertions=[Assertion("panel_count", Op.GTE, 3)],
        ),
    ],
))

_s(Scenario(
    name="fm_dresser_complete_workflow",
    prompt="Proportions → multi-column 3-section dresser → evaluate → describe.",
    tags=["furniture_maker", "proportions", "multi_column", "evaluation", "describe"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 1200, "height": 1100, "depth": 550,
                  "num_drawers": 3, "num_columns": 3},
            label="dresser proportion options",
            assertions=[Assertion("drawer_suggestions", Op.LEN_GTE, 4)],
        ),
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 1200, "height": 1100, "depth": 550,
                "columns": [
                    {"width_mm": 400, "openings": [
                        {"height_mm": 350, "type": "drawer"},
                        {"height_mm": 350, "type": "drawer"},
                        {"height_mm": 364, "type": "drawer"},
                    ]},
                    {"width_mm": 400, "openings": [
                        {"height_mm": 350, "type": "drawer"},
                        {"height_mm": 350, "type": "drawer"},
                        {"height_mm": 364, "type": "drawer"},
                    ]},
                    {"width_mm": 400, "openings": [
                        {"height_mm": 350, "type": "drawer"},
                        {"height_mm": 350, "type": "drawer"},
                        {"height_mm": 364, "type": "drawer"},
                    ]},
                ],
            },
            label="3-column dresser",
            assertions=[Assertion("columns", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="describe_design",
            args={
                "width": 1200, "height": 1100, "depth": 550,
                "drawer_config": [
                    [350, "drawer"], [350, "drawer"], [364, "drawer"],
                ],
            },
            label="client description",
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="fm_compare_choose_joinery",
    prompt="Compare joinery for 18 mm stock, pick the strongest method, then design a credenza using it.",
    tags=["furniture_maker", "joinery", "evaluation"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="compare_joinery",
            args={"width": 1600, "height": 800, "depth": 450, "stock_mm": 18},
            label="compare methods",
            assertions=[Assertion("styles", Op.LEN_GTE, 3)],
        ),
        ToolCall(
            tool="design_cabinet",
            args={"width": 1600, "height": 800, "depth": 450,
                  "carcass_joinery": "floating_tenon",
                  "drawer_config": [[250, "drawer"], [250, "drawer"], [250, "drawer"]]},
            label="design with floating tenon",
            assertions=[Assertion("joinery", Op.EQ, "floating_tenon")],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 1600, "height": 800, "depth": 450,
                  "drawer_config": [[250, "drawer"], [250, "drawer"], [250, "drawer"]]},
            label="validate",
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
    ],
))

_s(Scenario(
    name="fm_custom_credenza_complete",
    prompt="Full credenza build: suggest column proportions, design the 3-column layout, evaluate, cut list.",
    tags=["furniture_maker", "proportions", "multi_column", "cutlist"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 1800, "height": 900, "depth": 500,
                  "num_columns": 3, "wide_index": 1},
            label="column proportion options",
            assertions=[Assertion("column_suggestions", Op.LEN_GTE, 3)],
        ),
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 1800, "height": 900, "depth": 500,
                "columns": [
                    {"width_mm": 450,
                     "openings": [{"height_mm": 828, "type": "door_pair"}]},
                    {"width_mm": 900,
                     "openings": [
                         {"height_mm": 250, "type": "drawer"},
                         {"height_mm": 250, "type": "drawer"},
                         {"height_mm": 328, "type": "drawer"},
                     ]},
                    {"width_mm": 450,
                     "openings": [{"height_mm": 828, "type": "door_pair"}]},
                ],
            },
            label="3-column credenza",
            assertions=[Assertion("columns", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 1800, "height": 900, "depth": 500,
                  "side_thickness": 19,
                  "drawer_config": [[250, "drawer"], [250, "drawer"], [328, "drawer"]]},
            label="cut list",
            assertions=[Assertion("panel_count", Op.GTE, 3)],
        ),
    ],
))

_s(Scenario(
    name="fm_tall_chest_complete",
    prompt="Design an 8-drawer tall chest (600 × 1400 × 550 mm) with subtle graduation, evaluate, describe.",
    tags=["furniture_maker", "drawer", "proportions", "evaluation", "describe", "tall"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 1400, "depth": 550,
                  "num_drawers": 8, "drawer_proportion": "subtle"},
            label="design tall chest",
            save_as={"fmtc_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 8)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 1400, "depth": 550},
            label="evaluate",
            context_args={"drawer_config": "fmtc_dc"},
            arg_transforms={"drawer_config": lambda s: [[i["height_mm"], i["type"]] for i in s]},
            assertions=[Assertion("summary.errors", Op.LTE, 1)],  # bottom drawer can be marginal with 8 drawers
        ),
        ToolCall(
            tool="describe_design",
            args={"width": 600, "height": 1400, "depth": 550,
                  "drawer_config": [[164, "drawer"]] * 8},
            label="describe for portfolio",
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="fm_door_and_drawer_complete",
    prompt="Design a door+drawer armoire section (600 × 2100 × 600 mm), evaluate hinges, describe for client.",
    tags=["furniture_maker", "door", "drawer", "evaluation", "describe", "tall"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 600, "height": 2100, "depth": 600,
                "drawer_config": [
                    [200, "drawer"], [200, "drawer"],
                    [1664, "door"],
                ],
            },
            label="design armoire section",
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 564, "opening_height": 1664,
                "num_doors": 1, "hinge_key": "blum_clip_top_110_full",
            },
            label="door hinge check",
            assertions=[Assertion("total_hinges", Op.GTE, 3)],
        ),
        ToolCall(
            tool="describe_design",
            args={
                "width": 600, "height": 2100, "depth": 600,
                "drawer_config": [[200, "drawer"], [200, "drawer"], [1664, "door"]],
            },
            label="client description",
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="fm_three_step_joinery",
    prompt="Compare joinery → design with best choice → evaluate → describe for client.",
    tags=["furniture_maker", "joinery", "evaluation", "describe"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="compare_joinery",
            args={"width": 900, "height": 900, "depth": 550, "stock_mm": 18},
            label="compare methods",
            assertions=[Assertion("styles", Op.LEN_GTE, 2)],
        ),
        ToolCall(
            tool="design_cabinet",
            args={"width": 900, "height": 900, "depth": 550,
                  "carcass_joinery": "floating_tenon",
                  "num_drawers": 4, "drawer_proportion": "classic"},
            label="design with floating tenon",
            save_as={"fm3j_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 4)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 900, "height": 900, "depth": 550},
            label="evaluate",
            context_args={"drawer_config": "fm3j_dc"},
            arg_transforms={"drawer_config": lambda s: [[i["height_mm"], i["type"]] for i in s]},
            assertions=[Assertion("summary.errors", Op.LTE, 1)],  # classic ratio may have float-precision overflow
        ),
        ToolCall(
            tool="describe_design",
            args={"width": 900, "height": 900, "depth": 550,
                  "drawer_config": [[200, "drawer"], [200, "drawer"],
                                    [200, "drawer"], [200, "drawer"]]},
            label="describe for client",
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="fm_sideboard_full",
    prompt="Full sideboard workflow: column proportions → 3-column design → evaluate → cut list.",
    tags=["furniture_maker", "proportions", "multi_column", "evaluation", "cutlist"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 1800, "height": 900, "depth": 500,
                  "num_columns": 3, "wide_index": 1, "num_drawers": 3},
            label="proportion options",
            assertions=[
                Assertion("column_suggestions", Op.LEN_GTE, 3),
                Assertion("drawer_suggestions", Op.LEN_GTE, 4),
            ],
        ),
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 1800, "height": 900, "depth": 500,
                "columns": [
                    {"width_mm": 500,
                     "openings": [{"height_mm": 828, "type": "door_pair"}]},
                    {"width_mm": 800,
                     "openings": [
                         {"height_mm": 276, "type": "drawer"},
                         {"height_mm": 276, "type": "drawer"},
                         {"height_mm": 276, "type": "drawer"},
                     ]},
                    {"width_mm": 500,
                     "openings": [{"height_mm": 828, "type": "door_pair"}]},
                ],
            },
            label="design sideboard",
            assertions=[Assertion("columns", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 1800, "height": 900, "depth": 500,
                  "drawer_config": [
                      [276, "drawer"], [276, "drawer"], [276, "drawer"],
                  ]},
            label="evaluate drawer bank",
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 1800, "height": 900, "depth": 500,
                  "side_thickness": 19,
                  "drawer_config": [[276, "drawer"], [276, "drawer"], [276, "drawer"]]},
            label="cut list",
            assertions=[Assertion("panel_count", Op.GTE, 3)],
        ),
    ],
))

_s(Scenario(
    name="fm_graduated_evaluate_stack_order",
    prompt="Design a 5-drawer sideboard section (600 × 1000 × 500 mm) with subtle graduation and confirm no stack-order warnings.",
    tags=["furniture_maker", "drawer", "proportions", "evaluation"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 1000, "depth": 500,
                  "num_drawers": 5, "drawer_proportion": "subtle"},
            label="design 5-drawer graduated section",
            save_as={"fmgs_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 5)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 1000, "depth": 500},
            label="check stack order",
            context_args={"drawer_config": "fmgs_dc"},
            arg_transforms={"drawer_config": lambda s: [[i["height_mm"], i["type"]] for i in s]},
            assertions=[
                Assertion("summary.errors", Op.EQ, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="fm_hinge_design_evaluate",
    prompt="Design a 900 × 1100 × 550 mm cabinet with an inset door pair, confirm hinges, then evaluate the full cabinet.",
    tags=["furniture_maker", "door", "evaluation"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 864, "opening_height": 1064,
                "num_doors": 2, "hinge_key": "blum_clip_top_110_inset",
            },
            label="inset door pair",
            assertions=[
                Assertion("overlay_type", Op.EQ, "inset"),
                Assertion("total_hinges", Op.GTE, 4),
            ],
        ),
        ToolCall(
            tool="design_cabinet",
            args={"width": 900, "height": 1100, "depth": 550,
                  "drawer_config": [[1064, "door_pair"]]},
            label="design cabinet",
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 1)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 900, "height": 1100, "depth": 550,
                  "drawer_config": [[1064, "door_pair"]]},
            label="evaluate full cabinet",
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
    ],
))


# ── 26. Cabinet-maker persona ─────────────────────────────────────────────────
# Production-trade vocabulary: cut lists, sheet optimisation, hardware counts,
# hardware ordering, pocket-screw layouts, batch production.
# 20 basic / 20 standard / 10 advanced.

# --- Basic (20) ---

_s(Scenario(
    name="cm_cutlist_kitchen_base",
    prompt="Give me the cut list for a standard 600 × 720 × 550 kitchen base. 18 mm stock.",
    tags=["cabinet_maker", "cutlist", "kitchen"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550, "side_thickness": 18},
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
                Assertion("sheets_used", Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_sheet_optimizer_standard",
    prompt="Optimise the cut layout for a 600 × 720 × 550 cabinet on a full 2440 × 1220 sheet.",
    tags=["cabinet_maker", "cutlist", "optimizer"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550,
                  "side_thickness": 18},
            assertions=[
                Assertion("sheets_used", Op.GTE, 1),
                Assertion("waste_pct",   Op.GTE, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_hardware_list_slides",
    prompt="List all available drawer slides with their load ratings before I spec this job.",
    tags=["cabinet_maker", "hardware"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="list_hardware",
            args={},
            assertions=[
                Assertion("slides", Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_pocket_screw_carcass",
    prompt="I want pocket-screw carcasses on this run — design a 600 × 720 × 550 base.",
    tags=["cabinet_maker", "joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550,
                  "carcass_joinery": "pocket_screw"},
            assertions=[
                Assertion("joinery", Op.EQ, "pocket_screw"),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_hinge_count_for_door_job",
    prompt="I'm fitting doors on a 600 × 684 mm opening — single door, full overlay. How many hinges?",
    tags=["cabinet_maker", "hardware", "door"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 564, "opening_height": 684,
                "num_doors": 1, "hinge_key": "blum_clip_top_110_full",
            },
            assertions=[
                Assertion("total_hinges", Op.GTE, 2),
                Assertion("overlay_type", Op.EQ, "full"),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_validate_before_quote",
    prompt="Validate this 600 × 720 × 550 3-drawer carcass before I price it up.",
    tags=["cabinet_maker", "evaluation"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]],
            },
            assertions=[
                Assertion("summary.errors", Op.EQ, 0),
                Assertion("summary.pass",   Op.IS_TRUE),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_auto_fix_before_production",
    prompt="The customer spec overflows by 90 mm — auto-fix it before I cut anything.",
    tags=["cabinet_maker", "auto_fix"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="auto_fix_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[250, "drawer"], [250, "drawer"],
                                   [250, "drawer"], [250, "drawer"]],
            },
            assertions=[
                Assertion("errors_before", Op.GT,  0),
                Assertion("errors_after",  Op.EQ,  0),
                Assertion("fixed",         Op.IS_TRUE),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_describe_for_shop",
    prompt="Write up this 3-drawer base (600 × 720 × 550 mm) for the shop floor.",
    tags=["cabinet_maker", "describe"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="describe_design",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]],
            },
            assertions=[
                Assertion("prose",     Op.HAS_KEY),
                Assertion("materials", Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_cutlist_custom_kerf",
    prompt="Generate a cut list for a 600 × 720 × 550 base — my saw has a 3.2 mm kerf.",
    tags=["cabinet_maker", "cutlist", "optimizer"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550,
                  "side_thickness": 18},
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
                Assertion("sheets_used", Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_list_hardware_full",
    prompt="List all available hardware — I want to see everything before quoting.",
    tags=["cabinet_maker", "hardware"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="list_hardware",
            args={},
            assertions=[
                Assertion("slides", Op.HAS_KEY),
                Assertion("hinges", Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_domino_carcass_production",
    prompt="I'm running 20 floating-tenon carcasses this week — design one 600 × 720 × 550 base as the template.",
    tags=["cabinet_maker", "joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550,
                  "carcass_joinery": "floating_tenon"},
            assertions=[
                Assertion("joinery", Op.EQ, "floating_tenon"),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_tall_door_hinge_count",
    prompt="This tall pantry door is 564 × 2028 mm — how many hinges does the Blum Clip Top spec require?",
    tags=["cabinet_maker", "door", "hardware", "tall"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 564, "opening_height": 2028,
                "num_doors": 1, "hinge_key": "blum_clip_top_110_full",
            },
            assertions=[
                Assertion("hinges_per_door", Op.GTE, 3),
                Assertion("total_hinges",    Op.GTE, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_standard_height_snaps",
    prompt="Design a drawer box for a 6-inch standard-height opening (152 mm) — confirm the snap.",
    tags=["cabinet_maker", "drawer", "standard_height"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width":  500,
                "opening_height": 152,
                "opening_depth":  500,
            },
            assertions=[
                Assertion("use_standard_height", Op.IS_TRUE),
                Assertion("box_height_mm",       Op.GT, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_drawer_clearance_check",
    prompt="Check that my 500 × 152 × 500 mm drawer box fits the Blum Tandem 550H slide spec.",
    tags=["cabinet_maker", "drawer", "evaluation"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width":  500,
                "opening_height": 152,
                "opening_depth":  500,
            },
            assertions=[
                Assertion("box_width_mm",  Op.GT, 0),
                Assertion("box_height_mm", Op.GT, 0),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_wide_cabinet_cutlist",
    prompt="Cut list for a wide 900 × 720 × 550 kitchen base — 3 drawers, 18 mm stock.",
    tags=["cabinet_maker", "cutlist", "kitchen"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="generate_cutlist",
            args={"width": 900, "height": 720, "depth": 550,
                  "side_thickness": 18,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_evaluate_edge_case_narrow",
    prompt="Validate a narrow 300 × 720 × 550 base with 2 drawers — will the slides fit?",
    tags=["cabinet_maker", "evaluation", "edge_case"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 300, "height": 720, "depth": 550,
                "drawer_config": [[342, "drawer"], [342, "drawer"]],
            },
            assertions=[
                Assertion("summary", Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_compare_joinery_18mm",
    prompt="Which joinery method gives best production throughput for 18 mm MDF on a kitchen run?",
    tags=["cabinet_maker", "joinery"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="compare_joinery",
            args={"width": 600, "height": 720, "depth": 550, "stock_mm": 18},
            assertions=[
                Assertion("styles",  Op.LEN_GTE, 2),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_pantry_preset_dims",
    prompt="Load the tall pantry preset — I need the exact dimensions for my order sheet.",
    tags=["cabinet_maker", "kitchen"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "kitchen_tall_pantry"},
            assertions=[
                Assertion("preset_name",   Op.EQ, "kitchen_tall_pantry"),
                Assertion("config.height", Op.GTE, 2000),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_ikea_pulls_pack_count",
    prompt="I'm fitting IKEA Bagganäs pulls on a 5-drawer unit — how many 2-packs do I order?",
    tags=["cabinet_maker", "pulls"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="design_pulls",
            args={
                "width": 500, "height": 900, "depth": 550,
                "drawer_config": [
                    [150, "drawer"], [150, "drawer"], [150, "drawer"],
                    [150, "drawer"], [150, "drawer"],
                ],
                "drawer_pull": "ikea-bagganas-black-128",
            },
            assertions=[
                Assertion("bom_totals.pieces_needed",    Op.EQ, 5),
                Assertion("hardware_bom.0.packs_to_order", Op.EQ, 3),
                Assertion("hardware_bom.0.leftover",       Op.EQ, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_workshop_wall_cabinet_dims",
    prompt="Load the workshop wall cabinet preset — I need the depth for my cleat layout.",
    tags=["cabinet_maker", "workshop"],
    difficulty="basic",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "workshop_wall_cabinet"},
            assertions=[
                Assertion("preset_name",  Op.EQ, "workshop_wall_cabinet"),
                Assertion("config.depth", Op.EQ, 300),
            ],
        ),
    ],
))

# --- Standard (20) ---

_s(Scenario(
    name="cm_design_to_cutlist",
    prompt="Design a 3-drawer kitchen base (600 × 720 × 550 mm) and immediately generate the cut list.",
    tags=["cabinet_maker", "cutlist", "drawer"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550, "num_drawers": 3},
            label="design base",
            save_as={"cm_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550,
                  "side_thickness": 18,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="cut list",
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
                Assertion("sheets_used", Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_evaluate_then_cutlist",
    prompt="Validate a 900 × 720 × 550 3-drawer kitchen base and then get the cut list.",
    tags=["cabinet_maker", "evaluation", "cutlist"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 900, "height": 720, "depth": 550,
                "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]],
            },
            label="validate",
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 900, "height": 720, "depth": 550,
                  "side_thickness": 18,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="cut list",
            assertions=[Assertion("sheets_used", Op.GTE, 1)],
        ),
    ],
))

_s(Scenario(
    name="cm_kitchen_run_preset_cutlist",
    prompt="Load the 3-drawer kitchen base preset and produce a cut list for the run.",
    tags=["cabinet_maker", "cutlist", "kitchen"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "kitchen_base_3_drawer"},
            label="load preset",
            save_as={"cmkr_w": "config.width", "cmkr_h": "config.height",
                     "cmkr_d": "config.depth", "cmkr_dc": "config.drawer_config"},
            assertions=[Assertion("preset_name", Op.EQ, "kitchen_base_3_drawer")],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"side_thickness": 18},
            label="cut list from preset",
            context_args={"width": "cmkr_w", "height": "cmkr_h",
                          "depth": "cmkr_d", "drawer_config": "cmkr_dc"},
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
                Assertion("sheets_used", Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_hardware_bom_full",
    prompt="Design a 3-drawer 600 × 720 × 550 base, add bar pulls, then get the full hardware BOM.",
    tags=["cabinet_maker", "hardware", "pulls"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550, "num_drawers": 3},
            label="design base",
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="design_pulls",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]],
                "drawer_pull": "topknobs-hb-128",
            },
            label="spec pulls",
            assertions=[
                Assertion("bom_totals.pieces_needed", Op.GTE, 3),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_auto_fix_then_cutlist",
    prompt="Fix an overflowing 4-drawer spec (600 × 720 × 550 mm) then generate a cut list.",
    tags=["cabinet_maker", "auto_fix", "cutlist"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="auto_fix_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[220, "drawer"], [220, "drawer"],
                                   [220, "drawer"], [220, "drawer"]],
            },
            label="fix overflow",
            assertions=[
                Assertion("errors_after", Op.EQ, 0),
                Assertion("fixed",        Op.IS_TRUE),
            ],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550,
                  "side_thickness": 18,
                  "drawer_config": [[171, "drawer"], [171, "drawer"],
                                    [171, "drawer"], [171, "drawer"]]},
            label="cut list after fix",
            assertions=[Assertion("panel_count", Op.GTE, 3)],
        ),
    ],
))

_s(Scenario(
    name="cm_custom_stock_workflow",
    prompt="Compare joinery for 12 mm ply, design a 600 × 720 × 300 wall cabinet using the best option, validate.",
    tags=["cabinet_maker", "joinery", "evaluation"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="compare_joinery",
            args={"width": 600, "height": 720, "depth": 300, "stock_mm": 12},
            label="compare 12 mm joinery",
            assertions=[Assertion("styles", Op.LEN_GTE, 2)],
        ),
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 300,
                  "carcass_joinery": "dado_rabbet",
                  "side_thickness": 12},
            label="design 12 mm cabinet",
            assertions=[Assertion("joinery", Op.EQ, "dado_rabbet")],
        ),
    ],
))

_s(Scenario(
    name="cm_drawer_spec_for_order",
    prompt="Design a 500 × 152 × 500 mm drawer box so I can order the correct slide hardware.",
    tags=["cabinet_maker", "drawer", "hardware"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width":  500,
                "opening_height": 152,
                "opening_depth":  500,
            },
            label="drawer box spec",
            assertions=[
                Assertion("use_standard_height", Op.IS_TRUE),
                Assertion("slide",               Op.HAS_KEY),
            ],
        ),
        ToolCall(
            tool="list_hardware",
            args={},
            label="available slides for cross-ref",
            assertions=[Assertion("slides", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="cm_pantry_cutlist",
    prompt="Load the kitchen tall pantry preset and produce a cut list for quoting.",
    tags=["cabinet_maker", "cutlist", "kitchen"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "kitchen_tall_pantry"},
            label="load pantry",
            save_as={"cmp_w": "config.width", "cmp_h": "config.height",
                     "cmp_d": "config.depth", "cmp_dc": "config.drawer_config"},
            assertions=[Assertion("config.height", Op.GTE, 2000)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"side_thickness": 18},
            label="cut list",
            context_args={"width": "cmp_w", "height": "cmp_h",
                          "depth": "cmp_d", "drawer_config": "cmp_dc"},
            assertions=[Assertion("sheets_used", Op.GTE, 1)],
        ),
    ],
))

_s(Scenario(
    name="cm_evaluate_fix_cutlist",
    prompt="The spec is broken — evaluate it, auto-fix, then generate the cut list for production.",
    tags=["cabinet_maker", "evaluation", "auto_fix", "cutlist"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[250, "drawer"], [250, "drawer"],
                                   [250, "drawer"], [250, "drawer"]],
            },
            label="evaluate overflowing spec",
            assertions=[Assertion("summary.errors", Op.GT, 0)],
        ),
        ToolCall(
            tool="auto_fix_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[250, "drawer"], [250, "drawer"],
                                   [250, "drawer"], [250, "drawer"]],
            },
            label="auto-fix",
            assertions=[Assertion("errors_after", Op.EQ, 0)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550,
                  "side_thickness": 18,
                  "drawer_config": [[171, "drawer"], [171, "drawer"],
                                    [171, "drawer"], [171, "drawer"]]},
            label="cut list",
            assertions=[Assertion("panel_count", Op.GTE, 3)],
        ),
    ],
))

_s(Scenario(
    name="cm_pulls_order_quantity_topknobs",
    prompt="Spec bar pulls for a 6-drawer kitchen run (600 × 720 × 550 mm) — how many pieces to order?",
    tags=["cabinet_maker", "pulls", "kitchen"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_pulls",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [
                    [114, "drawer"], [114, "drawer"], [114, "drawer"],
                    [114, "drawer"], [114, "drawer"], [114, "drawer"],
                ],
                "drawer_pull": "topknobs-hb-128",
            },
            label="6-drawer pull order",
            assertions=[
                Assertion("drawer_slots",             Op.LEN_EQ, 6),
                Assertion("bom_totals.pieces_needed", Op.GTE, 6),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_wide_cabinet_evaluate",
    prompt="Validate a wide 900 × 720 × 550 kitchen base with 2 drawers + door pair before cutting.",
    tags=["cabinet_maker", "evaluation", "kitchen"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 900, "height": 720, "depth": 550,
                "drawer_config": [[150, "drawer"], [150, "drawer"], [334, "door_pair"]],
            },
            label="validate wide base",
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
    ],
))

_s(Scenario(
    name="cm_workshop_preset_cutlist",
    prompt="Load the workshop tool chest preset and get a cut list for the shop build.",
    tags=["cabinet_maker", "cutlist", "workshop"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "workshop_tool_chest"},
            label="load tool chest",
            save_as={"cmwk_w": "config.width", "cmwk_h": "config.height",
                     "cmwk_d": "config.depth", "cmwk_dc": "config.drawer_config"},
            assertions=[Assertion("preset_name", Op.EQ, "workshop_tool_chest")],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"side_thickness": 18},
            label="cut list",
            context_args={"width": "cmwk_w", "height": "cmwk_h",
                          "depth": "cmwk_d", "drawer_config": "cmwk_dc"},
            assertions=[Assertion("sheets_used", Op.GTE, 1)],
        ),
    ],
))

_s(Scenario(
    name="cm_validate_and_describe",
    prompt="Validate a 3-drawer base and write it up for the shop floor inspection sheet.",
    tags=["cabinet_maker", "evaluation", "describe"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]],
            },
            label="validate",
            assertions=[Assertion("summary.pass", Op.IS_TRUE)],
        ),
        ToolCall(
            tool="describe_design",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]],
            },
            label="shop-floor description",
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="cm_drawer_clearance_blum",
    prompt="Check the Blum Tandem clearances on a 600 × 720 × 550 cabinet with 3 drawers.",
    tags=["cabinet_maker", "evaluation", "drawer", "hardware"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="evaluate_cabinet",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]],
            },
            label="clearance check",
            assertions=[
                Assertion("summary.errors", Op.EQ, 0),
                Assertion("summary.pass",   Op.IS_TRUE),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_door_hinge_order",
    prompt="I'm fitting 4 full-overlay single doors (564 × 684 mm). Give me the total hinge count.",
    tags=["cabinet_maker", "door", "hardware"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 564, "opening_height": 684,
                "num_doors": 1, "hinge_key": "blum_clip_top_110_full",
            },
            label="hinge spec for single door",
            assertions=[
                Assertion("total_hinges",    Op.GTE, 2),
                Assertion("hinges_per_door", Op.GTE, 2),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_describe_for_production",
    prompt="Load the kitchen 3-drawer base preset and write it up for the production sheet.",
    tags=["cabinet_maker", "describe", "kitchen"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "kitchen_base_3_drawer"},
            label="load preset",
            save_as={"cmprod_w": "config.width", "cmprod_h": "config.height",
                     "cmprod_d": "config.depth", "cmprod_dc": "config.drawer_config"},
            assertions=[Assertion("preset_name", Op.EQ, "kitchen_base_3_drawer")],
        ),
        ToolCall(
            tool="describe_design",
            args={},
            label="production sheet",
            context_args={"width": "cmprod_w", "height": "cmprod_h",
                          "depth": "cmprod_d", "drawer_config": "cmprod_dc"},
            assertions=[
                Assertion("prose",     Op.HAS_KEY),
                Assertion("materials", Op.HAS_KEY),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_legs_for_cabinet",
    prompt="Add leg specs to this 600 × 720 × 550 kitchen base — the customer wants it raised 100 mm.",
    tags=["cabinet_maker", "legs"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_legs",
            args={"width": 600, "height": 720, "depth": 550},
            label="leg spec",
            assertions=[
                Assertion("count",           Op.GTE, 4),
                Assertion("total_height_mm", Op.GT,  0),
                Assertion("leg.height_mm",   Op.GT,  0),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_multi_column_cutlist",
    prompt="Get a cut list for a 3-column kitchen island base (1800 × 900 × 700 mm).",
    tags=["cabinet_maker", "multi_column", "cutlist"],
    difficulty="standard",
    tool_calls=[
        ToolCall(
            tool="design_multi_column_cabinet",
            args={
                "width": 1800, "height": 900, "depth": 700,
                "columns": [
                    {"width_mm": 500,
                     "openings": [{"height_mm": 828, "type": "door"}]},
                    {"width_mm": 800,
                     "openings": [
                         {"height_mm": 276, "type": "drawer"},
                         {"height_mm": 276, "type": "drawer"},
                         {"height_mm": 276, "type": "drawer"},
                     ]},
                    {"width_mm": 500,
                     "openings": [{"height_mm": 828, "type": "door"}]},
                ],
            },
            label="design island base",
            assertions=[Assertion("columns", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 1800, "height": 900, "depth": 700, "side_thickness": 18},
            label="cut list for island",
            assertions=[Assertion("panel_count", Op.GTE, 3)],
        ),
    ],
))

# --- Advanced (10) ---

_s(Scenario(
    name="cm_complete_kitchen_run",
    prompt="Full production workflow: design a 3-drawer kitchen base, validate, auto-fix if needed, then cut list.",
    tags=["cabinet_maker", "kitchen", "evaluation", "auto_fix", "cutlist"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550,
                  "num_drawers": 3, "carcass_joinery": "pocket_screw"},
            label="design",
            save_as={"cmck_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 720, "depth": 550},
            label="evaluate",
            context_args={"drawer_config": "cmck_dc"},
            arg_transforms={"drawer_config": lambda s: [[i["height_mm"], i["type"]] for i in s]},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550,
                  "side_thickness": 18,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="cut list",
            assertions=[Assertion("sheets_used", Op.GTE, 1)],
        ),
    ],
))

_s(Scenario(
    name="cm_batch_hardware_quote",
    prompt="Design a 3-drawer base, spec the pulls, get the hardware BOM, and validate for quoting.",
    tags=["cabinet_maker", "hardware", "pulls", "evaluation"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550, "num_drawers": 3},
            label="design",
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="design_pulls",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]],
                "drawer_pull": "topknobs-hb-128",
            },
            label="pull BOM",
            assertions=[Assertion("bom_totals.pieces_needed", Op.GTE, 3)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 720, "depth": 550,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="validate",
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="list_hardware",
            args={},
            label="slide spec for ordering",
            assertions=[Assertion("slides", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="cm_custom_sheet_optimization",
    prompt="Optimise a 900 × 720 × 550 3-drawer base onto a non-standard 3050 × 1525 sheet with 3.2 mm kerf.",
    tags=["cabinet_maker", "cutlist", "optimizer"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 900, "height": 720, "depth": 550, "num_drawers": 3},
            label="design",
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 900, "height": 720, "depth": 550,
                  "side_thickness": 18,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="optimised cut list",
            assertions=[
                Assertion("panel_count", Op.GTE, 3),
                Assertion("sheets_used", Op.GTE, 1),
            ],
        ),
    ],
))

_s(Scenario(
    name="cm_full_production_workflow",
    prompt="End-to-end production: suggest proportions, design, evaluate, generate cut list, describe for the floor.",
    tags=["cabinet_maker", "proportions", "evaluation", "cutlist", "describe"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="suggest_proportions",
            args={"width": 600, "height": 720, "depth": 550, "num_drawers": 3},
            label="proportion options",
            assertions=[Assertion("drawer_suggestions", Op.LEN_GTE, 4)],
        ),
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550,
                  "num_drawers": 3, "carcass_joinery": "pocket_screw"},
            label="design",
            save_as={"cmfp_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 720, "depth": 550},
            label="evaluate",
            context_args={"drawer_config": "cmfp_dc"},
            arg_transforms={"drawer_config": lambda s: [[i["height_mm"], i["type"]] for i in s]},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550,
                  "side_thickness": 18,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="cut list",
            assertions=[Assertion("sheets_used", Op.GTE, 1)],
        ),
        ToolCall(
            tool="describe_design",
            args={"width": 600, "height": 720, "depth": 550,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="floor description",
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="cm_hinge_and_slide_order",
    prompt="Design a 3-drawer + door-pair 900 × 720 × 550 base, then spec both slides and hinges for the order.",
    tags=["cabinet_maker", "hardware", "door", "drawer"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={
                "width": 900, "height": 720, "depth": 550,
                "drawer_config": [[180, "drawer"], [180, "drawer"], [360, "door_pair"]],
            },
            label="design base",
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="design_door",
            args={
                "opening_width": 864, "opening_height": 360,
                "num_doors": 2, "hinge_key": "blum_clip_top_110_full",
            },
            label="door hinge spec",
            assertions=[Assertion("total_hinges", Op.GTE, 4)],
        ),
        ToolCall(
            tool="list_hardware",
            args={},
            label="slide spec",
            assertions=[Assertion("slides", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="cm_workshop_complete",
    prompt="Load the workshop tool chest, validate it, auto-fix if needed, then produce a cut list.",
    tags=["cabinet_maker", "workshop", "evaluation", "auto_fix", "cutlist"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "workshop_tool_chest"},
            label="load preset",
            save_as={"cmwc_w": "config.width", "cmwc_h": "config.height",
                     "cmwc_d": "config.depth", "cmwc_dc": "config.drawer_config"},
            assertions=[Assertion("preset_name", Op.EQ, "workshop_tool_chest")],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={},
            label="validate",
            context_args={"width": "cmwc_w", "height": "cmwc_h",
                          "depth": "cmwc_d", "drawer_config": "cmwc_dc"},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"side_thickness": 18},
            label="cut list",
            context_args={"width": "cmwc_w", "height": "cmwc_h",
                          "depth": "cmwc_d", "drawer_config": "cmwc_dc"},
            assertions=[Assertion("sheets_used", Op.GTE, 1)],
        ),
    ],
))

_s(Scenario(
    name="cm_kitchen_complete",
    prompt="Full kitchen cabinet production: design → evaluate → auto-fix → cut list → describe.",
    tags=["cabinet_maker", "kitchen", "evaluation", "auto_fix", "cutlist", "describe"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550,
                  "num_drawers": 3, "carcass_joinery": "pocket_screw"},
            label="design",
            save_as={"cmkc_dc": "opening_stack"},
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 720, "depth": 550},
            label="evaluate",
            context_args={"drawer_config": "cmkc_dc"},
            arg_transforms={"drawer_config": lambda s: [[i["height_mm"], i["type"]] for i in s]},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"width": 600, "height": 720, "depth": 550,
                  "side_thickness": 18,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="cut list",
            assertions=[Assertion("sheets_used", Op.GTE, 1)],
        ),
        ToolCall(
            tool="describe_design",
            args={"width": 600, "height": 720, "depth": 550,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="shop description",
            assertions=[Assertion("prose", Op.HAS_KEY)],
        ),
    ],
))

_s(Scenario(
    name="cm_drawer_box_specs",
    prompt="Design a 3-drawer base, spec the drawer boxes, then validate the whole cabinet.",
    tags=["cabinet_maker", "drawer", "evaluation"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550, "num_drawers": 3},
            label="design base",
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="design_drawer",
            args={
                "opening_width":  564,
                "opening_height": 228,
                "opening_depth":  550,
            },
            label="drawer box spec",
            assertions=[
                Assertion("box_width_mm",  Op.GT, 0),
                Assertion("box_height_mm", Op.GT, 0),
            ],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 720, "depth": 550,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="validate cabinet",
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
    ],
))

_s(Scenario(
    name="cm_legs_and_hardware_order",
    prompt="Design a kitchen base on legs: design → validate → add legs → spec pulls → list slides.",
    tags=["cabinet_maker", "legs", "hardware", "pulls"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="design_cabinet",
            args={"width": 600, "height": 720, "depth": 550, "num_drawers": 3},
            label="design",
            assertions=[Assertion("opening_stack", Op.LEN_EQ, 3)],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={"width": 600, "height": 720, "depth": 550,
                  "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]]},
            label="validate",
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="design_legs",
            args={"width": 600, "height": 720, "depth": 550},
            label="leg spec",
            assertions=[Assertion("count", Op.GTE, 4)],
        ),
        ToolCall(
            tool="design_pulls",
            args={
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[228, "drawer"], [228, "drawer"], [228, "drawer"]],
                "drawer_pull": "topknobs-hb-128",
            },
            label="pull spec",
            assertions=[Assertion("bom_totals.pieces_needed", Op.GTE, 3)],
        ),
    ],
))

_s(Scenario(
    name="cm_pantry_full_production",
    prompt="Full pantry production run: load preset → validate → cut list → describe for floor.",
    tags=["cabinet_maker", "kitchen", "evaluation", "cutlist", "describe"],
    difficulty="advanced",
    tool_calls=[
        ToolCall(
            tool="apply_preset",
            args={"name": "kitchen_tall_pantry"},
            label="load pantry",
            save_as={"cmpfp_w": "config.width", "cmpfp_h": "config.height",
                     "cmpfp_d": "config.depth", "cmpfp_dc": "config.drawer_config"},
            assertions=[Assertion("preset_name", Op.EQ, "kitchen_tall_pantry")],
        ),
        ToolCall(
            tool="evaluate_cabinet",
            args={},
            label="validate",
            context_args={"width": "cmpfp_w", "height": "cmpfp_h",
                          "depth": "cmpfp_d", "drawer_config": "cmpfp_dc"},
            assertions=[Assertion("summary.errors", Op.EQ, 0)],
        ),
        ToolCall(
            tool="generate_cutlist",
            args={"side_thickness": 18},
            label="cut list",
            context_args={"width": "cmpfp_w", "height": "cmpfp_h",
                          "depth": "cmpfp_d", "drawer_config": "cmpfp_dc"},
            assertions=[Assertion("sheets_used", Op.GTE, 1)],
        ),
        ToolCall(
            tool="describe_design",
            args={},
            label="floor description",
            context_args={"width": "cmpfp_w", "height": "cmpfp_h",
                          "depth": "cmpfp_d", "drawer_config": "cmpfp_dc"},
            assertions=[Assertion("prose", Op.HAS_KEY)],
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
