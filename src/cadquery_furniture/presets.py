"""
Named cabinet presets — validated starting configurations for common cabinet types.

Each preset is a fully-specified ``CabinetConfig`` that passes evaluation out of
the box. They are the intended entry-point for a design session: pick a preset,
review the opening stack and hardware, then tweak individual parameters rather
than starting from scratch.

All dimensions are millimetres. Opening-stack heights are calculated so they sum
exactly to ``interior_height = height - bottom_thickness - top_thickness``.

Usage via MCP
-------------
  list_presets             — browse the catalogue (name, category, description, dims)
  apply_preset name=…      — load a preset's full config dict, ready for design_cabinet
  apply_preset name=… overrides={"width": 750}  — load and override specific fields
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .cabinet import CabinetConfig, ColumnConfig, OpeningConfig
from .joinery import CarcassJoinery


# ─── Preset dataclass ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CabinetPreset:
    """A named, documented, validated cabinet configuration."""

    name: str           # slug used with apply_preset  (e.g. "kitchen_base_3_drawer")
    display_name: str   # human-readable label          (e.g. "Kitchen Base — 3 Drawer")
    description: str    # one-line use-case description
    category: str       # kitchen | workshop | bedroom | bathroom | storage
    tags: list[str]     # searchable tags
    difficulty: str     # basic | standard | advanced
    config: CabinetConfig

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Compact summary for list_presets — no interior geometry computed."""
        cfg = self.config
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "difficulty": self.difficulty,
            "dimensions": {
                "width_mm": cfg.width,
                "height_mm": cfg.height,
                "depth_mm": cfg.depth,
            },
            "opening_stack": [
                {"height_mm": op.height_mm, "type": op.opening_type}
                for op in cfg.openings
            ],
            "drawer_slide": cfg.drawer_slide,
            "door_hinge": cfg.door_hinge,
            "carcass_joinery": cfg.carcass_joinery.value,
            "adj_shelf_holes": cfg.adj_shelf_holes,
        }

    def config_dict(self) -> dict[str, Any]:
        """Full config as a flat dict — suitable for passing to design_cabinet / apply_preset."""
        cfg = self.config
        result: dict[str, Any] = {
            "width": cfg.width,
            "height": cfg.height,
            "depth": cfg.depth,
            "side_thickness": cfg.side_thickness,
            "bottom_thickness": cfg.bottom_thickness,
            "top_thickness": cfg.top_thickness,
            "shelf_thickness": cfg.shelf_thickness,
            "back_thickness": cfg.back_thickness,
            "dado_depth": cfg.dado_depth,
            "back_rabbet_width": cfg.back_rabbet_width,
            "back_rabbet_depth": cfg.back_rabbet_depth,
            "drawer_config": [[op.height_mm, op.opening_type] for op in cfg.openings],
            "carcass_joinery": cfg.carcass_joinery.value,
            "fixed_shelf_positions": list(cfg.fixed_shelf_positions),
            "adj_shelf_holes": cfg.adj_shelf_holes,
            "drawer_slide": cfg.drawer_slide,
            "door_hinge": cfg.door_hinge,
            "drawer_pull": cfg.drawer_pull,
            "door_pull": cfg.door_pull,
            "door_hinge_side": cfg.door_hinge_side,
            "door_pull_inset_mm": cfg.door_pull_inset_mm,
        }
        if cfg.columns:
            result["columns"] = [
                {
                    "width_mm": col.width_mm,
                    "drawer_config": [[op.height_mm, op.opening_type] for op in col.openings],
                }
                for col in cfg.columns
            ]
        return result


# ─── Registry ─────────────────────────────────────────────────────────────────

PRESETS: dict[str, CabinetPreset] = {}


def _p(preset: CabinetPreset) -> CabinetPreset:
    """Register and return a preset."""
    PRESETS[preset.name] = preset
    return preset


# ═══════════════════════════════════════════════════════════════════════════════
# Preset catalogue
#
# Opening-stack heights must sum to: height - bottom_thickness(18) - top_thickness(18)
# Standard base:    720 - 36 = 684 mm interior height
# ═══════════════════════════════════════════════════════════════════════════════

# ── Kitchen ───────────────────────────────────────────────────────────────────

_p(CabinetPreset(
    name="kitchen_base_3_drawer",
    display_name="Kitchen Base — 3 Drawer",
    description=(
        "Classic 600 mm base cabinet with three drawers: "
        "large bottom drawer for pots/pans, two narrow utensil drawers above. "
        "Blum Tandem undermount slides, dado-rabbet carcass."
    ),
    category="kitchen",
    tags=["kitchen", "base", "drawer", "blum", "dado_rabbet"],
    difficulty="basic",
    config=CabinetConfig(
        width=600,
        height=720,
        depth=550,
        # Opening stack sums to 684 mm (720 - 18 - 18)
        openings=[
            (300, "drawer"),   # large bottom — pots/pans
            (192, "drawer"),   # mid utensil
            (192, "drawer"),   # top utensil
        ],
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))

_p(CabinetPreset(
    name="kitchen_base_door_2_drawer",
    display_name="Kitchen Base — Door + 2 Drawer",
    description=(
        "600 mm base cabinet with a deep door compartment below "
        "and two shallow drawers at the top — ideal for trash pull-out or pots. "
        "Blum Tandem slides, Blum Clip Top hinges."
    ),
    category="kitchen",
    tags=["kitchen", "base", "door", "drawer", "blum"],
    difficulty="basic",
    config=CabinetConfig(
        width=600,
        height=720,
        depth=550,
        # Opening stack sums to 684 mm
        openings=[
            (434, "door"),    # tall door compartment at bottom
            (125, "drawer"),  # drawer
            (125, "drawer"),  # drawer
        ],
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))

_p(CabinetPreset(
    name="kitchen_base_door_pair_wide",
    display_name="Kitchen Base — Door Pair (900 mm wide)",
    description=(
        "900 mm wide base cabinet with a full-width door pair below "
        "and two drawers at the top. Common for sinks or large storage bays. "
        "Half-overlay hinges for shared partition walls."
    ),
    category="kitchen",
    tags=["kitchen", "base", "door_pair", "drawer", "wide", "blum"],
    difficulty="standard",
    config=CabinetConfig(
        width=900,
        height=720,
        depth=550,
        # Opening stack sums to 684 mm
        openings=[
            (434, "door_pair"),  # door pair at bottom
            (125, "drawer"),
            (125, "drawer"),
        ],
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_110_half",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))

_p(CabinetPreset(
    name="kitchen_tall_pantry",
    display_name="Kitchen Tall Pantry",
    description=(
        "Full-height 2100 mm pantry cabinet with a door pair on the top half "
        "and a door pair on the bottom half, separated by a fixed shelf. "
        "Adjustable shelf pin holes throughout. Blum BLUMOTION soft-close hinges."
    ),
    category="kitchen",
    tags=["kitchen", "pantry", "tall", "door_pair", "shelf", "soft_close", "blum"],
    difficulty="standard",
    config=CabinetConfig(
        width=600,
        height=2100,
        depth=550,
        # Opening stack sums to 2064 mm (2100 - 18 - 18)
        openings=[
            (700, "door_pair"),   # lower door pair
            (664, "shelf"),       # mid shelf section
            (700, "door_pair"),   # upper door pair
        ],
        adj_shelf_holes=True,
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))


# ── Workshop ──────────────────────────────────────────────────────────────────

_p(CabinetPreset(
    name="workshop_tool_chest",
    display_name="Workshop Tool Chest — 6 Drawer",
    description=(
        "Heavy-duty 600×900 mm tool chest with six equal-height drawers. "
        "Blum Movento 769 heavy-duty slides rated 77 kg each. "
        "Pocket-screw carcass for fast shop assembly."
    ),
    category="workshop",
    tags=["workshop", "tool_chest", "drawer", "heavy_duty", "blum_movento"],
    difficulty="standard",
    config=CabinetConfig(
        width=600,
        height=900,
        depth=550,
        # Opening stack sums to 864 mm (900 - 18 - 18); 6 × 144
        openings=[
            (144, "drawer"),
            (144, "drawer"),
            (144, "drawer"),
            (144, "drawer"),
            (144, "drawer"),
            (144, "drawer"),
        ],
        drawer_slide="blum_movento_769",
        door_hinge="blum_clip_top_110_full",
        carcass_joinery=CarcassJoinery.POCKET_SCREW,
    ),
))

_p(CabinetPreset(
    name="workshop_wall_cabinet",
    display_name="Workshop Wall Cabinet — Door Pair",
    description=(
        "Shallow 300 mm deep wall cabinet, 600×720 mm, with a full-width door pair "
        "and adjustable shelf holes. Good for hardware bins or finishing supplies."
    ),
    category="workshop",
    tags=["workshop", "wall", "door_pair", "shallow", "shelf"],
    difficulty="basic",
    config=CabinetConfig(
        width=600,
        height=720,
        depth=300,
        # Opening stack sums to 684 mm
        openings=[
            (684, "door_pair"),
        ],
        adj_shelf_holes=True,
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_110_full",
        carcass_joinery=CarcassJoinery.POCKET_SCREW,
    ),
))


# ── Bedroom ───────────────────────────────────────────────────────────────────

_p(CabinetPreset(
    name="bedroom_dresser",
    display_name="Bedroom Dresser — 6 Drawer",
    description=(
        "900 mm wide, 1100 mm tall dresser with six drawers in two column heights: "
        "two taller drawers at the bottom for folded clothes, "
        "four narrower drawers above for shirts and accessories. "
        "Blum Tandem+ full-extension slides."
    ),
    category="bedroom",
    tags=["bedroom", "dresser", "drawer", "blum", "full_extension"],
    difficulty="standard",
    config=CabinetConfig(
        width=900,
        height=1100,
        depth=550,
        # Opening stack sums to 1064 mm (1100 - 18 - 18); 2×178 + 4×177
        openings=[
            (178, "drawer"),  # bottom large
            (178, "drawer"),  # bottom large
            (177, "drawer"),
            (177, "drawer"),
            (177, "drawer"),
            (177, "drawer"),  # top narrow
        ],
        drawer_slide="blum_tandem_plus_563h",
        door_hinge="blum_clip_top_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))


# ── Bathroom ──────────────────────────────────────────────────────────────────

_p(CabinetPreset(
    name="bathroom_vanity",
    display_name="Bathroom Vanity — Door + 2 Drawer",
    description=(
        "600×850 mm bathroom vanity: door below (plumbing access or waste bin) "
        "and two drawers above for toiletries. "
        "Shallower 480 mm depth for standard vanity clearance. "
        "Blum BLUMOTION soft-close on both slides and hinges."
    ),
    category="bathroom",
    tags=["bathroom", "vanity", "door", "drawer", "soft_close", "shallow", "blum"],
    difficulty="standard",
    config=CabinetConfig(
        width=600,
        height=850,
        depth=480,
        # Opening stack sums to 814 mm (850 - 18 - 18)
        openings=[
            (264, "door"),    # door at bottom — plumbing or waste
            (275, "drawer"),  # upper drawer
            (275, "drawer"),  # top drawer
        ],
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))


# ── Storage ───────────────────────────────────────────────────────────────────

_p(CabinetPreset(
    name="storage_wall_cabinet",
    display_name="Storage Wall Cabinet — Adjustable Shelves",
    description=(
        "600×720 mm wall cabinet with a full-width door pair and adjustable shelf "
        "pin holes on the 32 mm European system. Versatile all-purpose storage. "
        "Blum BLUMOTION soft-close hinges."
    ),
    category="storage",
    tags=["storage", "wall", "door_pair", "shelf", "adjustable", "soft_close"],
    difficulty="basic",
    config=CabinetConfig(
        width=600,
        height=720,
        depth=300,
        # Single full-height opening — interior = 684 mm
        openings=[
            (684, "door_pair"),
        ],
        adj_shelf_holes=True,
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))


# ── Living room / foyer ───────────────────────────────────────────────────────

_p(CabinetPreset(
    name="foyer_console_2_drawer",
    display_name="Foyer Console — 2 Drawer",
    description=(
        "1200×800 mm console table with two shallow drawers at the top "
        "and an open display shelf below — typical for entryways and sofa tables. "
        "Shallow 350 mm depth fits against a wall without blocking circulation. "
        "Blum Tandem 550H undermount slides, dado-rabbet carcass."
    ),
    category="living_room",
    tags=["living_room", "foyer", "console", "drawer", "open", "shallow"],
    difficulty="standard",
    config=CabinetConfig(
        width=1200,
        height=800,
        depth=350,
        # Opening stack sums to 764 mm (800 - 18 - 18)
        openings=[
            (564, "open"),    # large open display shelf at bottom
            (100, "drawer"),  # drawer
            (100, "drawer"),  # drawer
        ],
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))

_p(CabinetPreset(
    name="foyer_console_narrow",
    display_name="Foyer Console — Narrow Single Drawer",
    description=(
        "900×850 mm narrow console for tight entryways: one slim drawer at the top "
        "for keys and mail, open shelf below for baskets or displays. "
        "Extra-shallow 300 mm depth. Dado-rabbet carcass."
    ),
    category="living_room",
    tags=["living_room", "foyer", "console", "drawer", "open", "shallow", "narrow"],
    difficulty="basic",
    config=CabinetConfig(
        width=900,
        height=850,
        depth=300,
        # Opening stack sums to 814 mm (850 - 18 - 18)
        openings=[
            (700, "open"),    # open shelf at bottom
            (114, "drawer"),  # single slim drawer at top
        ],
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))

_p(CabinetPreset(
    name="living_room_credenza",
    display_name="Living Room Credenza",
    description=(
        "1600×800 mm credenza with a full-width door pair at the bottom "
        "for concealed storage and two frieze drawers at the top for small items. "
        "450 mm depth, Blum Tandem+ full-extension slides, BLUMOTION soft-close hinges. "
        "Adjustable shelf pin holes inside the door section."
    ),
    category="living_room",
    tags=["living_room", "credenza", "door_pair", "drawer", "soft_close", "full_extension"],
    difficulty="standard",
    config=CabinetConfig(
        width=1600,
        height=800,
        depth=450,
        # Opening stack sums to 764 mm (800 - 18 - 18)
        openings=[
            (564, "door_pair"),  # large door-pair cabinet at bottom
            (100, "drawer"),     # frieze drawer
            (100, "drawer"),     # frieze drawer
        ],
        adj_shelf_holes=True,
        drawer_slide="blum_tandem_plus_563h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))

_p(CabinetPreset(
    name="living_room_sideboard",
    display_name="Living Room Sideboard",
    description=(
        "1800×900 mm sideboard: wider and taller than a credenza, "
        "suitable for dining rooms or living rooms. Door pair below for deep storage, "
        "two full-width drawers above for linens or serving ware. "
        "500 mm depth, Blum Tandem+ full-extension slides, BLUMOTION hinges."
    ),
    category="living_room",
    tags=["living_room", "sideboard", "door_pair", "drawer", "soft_close", "full_extension", "wide"],
    difficulty="standard",
    config=CabinetConfig(
        width=1800,
        height=900,
        depth=500,
        # Opening stack sums to 864 mm (900 - 18 - 18)
        openings=[
            (614, "door_pair"),  # deep door-pair cabinet at bottom
            (125, "drawer"),     # drawer
            (125, "drawer"),     # drawer
        ],
        adj_shelf_holes=True,
        drawer_slide="blum_tandem_plus_563h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))

_p(CabinetPreset(
    name="media_console",
    display_name="Media Console / TV Stand",
    description=(
        "1800×600 mm low media console: door pair below for AV equipment storage "
        "and an open shelf above for a soundbar, books, or display objects. "
        "450 mm depth, low 600 mm height keeps the TV at a comfortable viewing angle. "
        "BLUMOTION soft-close hinges."
    ),
    category="living_room",
    tags=["living_room", "media", "console", "door_pair", "open", "low", "soft_close"],
    difficulty="basic",
    config=CabinetConfig(
        width=1800,
        height=600,
        depth=450,
        # Opening stack sums to 564 mm (600 - 18 - 18)
        openings=[
            (264, "door_pair"),  # door pair at bottom for AV gear
            (300, "open"),       # open shelf at top for soundbar / display
        ],
        adj_shelf_holes=False,
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))


# ── Bedroom ───────────────────────────────────────────────────────────────────

_p(CabinetPreset(
    name="bedroom_armoire",
    display_name="Bedroom Armoire — Door Pair + 2 Drawer",
    description=(
        "1100×1900 mm single-cabinet armoire: a large door-pair compartment "
        "above for hanging space and shelves, two base drawers below for "
        "folded garments. 580 mm depth. Covers armoire, wardrobe, schrank, "
        "and armadio. BLUMOTION soft-close hinges, dado-rabbet carcass."
    ),
    category="bedroom",
    tags=["bedroom", "armoire", "wardrobe", "door_pair", "drawer", "tall", "soft_close"],
    difficulty="standard",
    config=CabinetConfig(
        width=1100,
        height=1900,
        depth=580,
        # Opening stack sums to 1864 mm (1900 - 18 - 18)
        openings=[
            (1614, "door_pair"),  # large door-pair compartment (hanging + shelves)
            (125,  "drawer"),
            (125,  "drawer"),
        ],
        adj_shelf_holes=True,
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))

_p(CabinetPreset(
    name="bedroom_chiffoniere",
    display_name="Bedroom Chiffonière — Door + 6 Drawer",
    description=(
        "500×1350 mm tall narrow chiffonière: a small door compartment at "
        "the top (for a mirror or personal items) above six shallow drawers "
        "for folded garments and accessories. 450 mm depth. The defining "
        "feature that distinguishes it from a lingerie chest. BLUMOTION "
        "soft-close, dado-rabbet carcass."
    ),
    category="bedroom",
    tags=["bedroom", "chiffoniere", "chiffonier", "drawer", "door", "tall", "narrow",
          "soft_close"],
    difficulty="standard",
    config=CabinetConfig(
        width=500,
        height=1350,
        depth=450,
        # Opening stack sums to 1314 mm (1350 - 18 - 18)
        # Bottom-to-top: 6 drawers (4×186 + 2×185 = 1114) + 1 top door (200)
        openings=[
            (185, "drawer"),
            (185, "drawer"),
            (186, "drawer"),
            (186, "drawer"),
            (186, "drawer"),
            (186, "drawer"),
            (200, "door"),    # small top compartment — mirror or display
        ],
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))

_p(CabinetPreset(
    name="armoire_2col",
    display_name="Armoire — 2-Column Drawer Base + Doors",
    description=(
        "44\" × 71\" tall armoire (100 mm legs included) with two equal columns of "
        "three drawers at the base (10\"/6\"/4\") and a full-width two-door section "
        "above. A transition shelf separates the drawer and door zones. "
        "21\" deep, floating-tenon carcass, Blum Tandem 550H slides. "
        "Pass this preset's columns array to design_multi_column_cabinet or "
        "visualize_cabinet (with divider_full_height=false)."
    ),
    category="bedroom",
    tags=["bedroom", "armoire", "wardrobe", "door", "drawer", "multi_column", "legs"],
    difficulty="advanced",
    config=CabinetConfig(
        width=1117.6,
        height=1703.4,   # carcass only — 100 mm legs bring the total to 71"
        depth=533.4,
        openings=[],
        columns=[
            ColumnConfig(
                width_mm=531.8,
                openings=(
                    (254.0,  "drawer"),   # 10" bottom
                    (152.4,  "drawer"),   # 6"  middle
                    (101.6,  "drawer"),   # 4"  top of drawer zone
                    (1159.4, "door"),     # door zone (transition shelf accounts for 18 mm)
                ),
            ),
            ColumnConfig(
                width_mm=531.8,
                openings=(
                    (254.0,  "drawer"),
                    (152.4,  "drawer"),
                    (101.6,  "drawer"),
                    (1159.4, "door"),
                ),
            ),
        ],
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_110_full",
        carcass_joinery=CarcassJoinery.FLOATING_TENON,
        drawer_pull="topknobs-hb-96",
        door_pull="topknobs-hb-96",
    ),
))


# ── Nightstand ────────────────────────────────────────────────────────────────

_p(CabinetPreset(
    name="bedroom_nightstand",
    display_name="Bedroom Nightstand — Drawer + Door",
    description=(
        "550×650 mm bedside cabinet with one shallow drawer at the top for "
        "books and remotes, and a door compartment below for a charger or "
        "small items. 400 mm depth. BLUMOTION soft-close on both. "
        "Dado-rabbet carcass."
    ),
    category="bedroom",
    tags=["bedroom", "nightstand", "bedside", "drawer", "door", "soft_close", "small"],
    difficulty="basic",
    config=CabinetConfig(
        width=550,
        height=650,
        depth=400,
        # Opening stack sums to 614 mm (650 - 18 - 18)
        openings=[
            (464, "door"),    # door compartment at bottom
            (150, "drawer"),  # shallow drawer at top
        ],
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))

# ── Tall chest of drawers ─────────────────────────────────────────────────────

_p(CabinetPreset(
    name="bedroom_tall_chest",
    display_name="Bedroom Tall Chest — 8 Drawer",
    description=(
        "600×1400 mm tall chest with eight graduated drawers: two deep "
        "bottom drawers for bulky items, tapering to narrower drawers at the "
        "top. 550 mm depth. Blum Tandem+ full-extension slides, dado-rabbet "
        "carcass. Covers tallboy, highboy, chest-on-chest, and chest of drawers."
    ),
    category="bedroom",
    tags=["bedroom", "chest", "tallboy", "highboy", "drawer", "tall", "full_extension"],
    difficulty="standard",
    config=CabinetConfig(
        width=600,
        height=1400,
        depth=550,
        # Opening stack sums to 1364 mm (1400 - 18 - 18)
        # Graduated bottom-to-top: 200, 200, 175, 175, 160, 160, 148, 146
        openings=[
            (200, "drawer"),
            (200, "drawer"),
            (175, "drawer"),
            (175, "drawer"),
            (160, "drawer"),
            (160, "drawer"),
            (148, "drawer"),
            (146, "drawer"),
        ],
        drawer_slide="blum_tandem_plus_563h",
        door_hinge="blum_clip_top_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))

# ── Lingerie chest / semainier ────────────────────────────────────────────────

_p(CabinetPreset(
    name="bedroom_lingerie_chest",
    display_name="Bedroom Lingerie Chest — 7 Drawer",
    description=(
        "500×1350 mm tall narrow chest with seven equal shallow drawers for "
        "folded garments and delicates. 450 mm depth. Covers chiffonier, "
        "semainier, and lingerie chest. BLUMOTION undermount slides, "
        "dado-rabbet carcass."
    ),
    category="bedroom",
    tags=["bedroom", "lingerie_chest", "chiffonier", "semainier", "drawer", "tall", "narrow"],
    difficulty="standard",
    config=CabinetConfig(
        width=500,
        height=1350,
        depth=450,
        # Opening stack sums to 1314 mm (1350 - 18 - 18); 5×188 + 2×187
        openings=[
            (188, "drawer"),
            (188, "drawer"),
            (188, "drawer"),
            (188, "drawer"),
            (188, "drawer"),
            (187, "drawer"),
            (187, "drawer"),
        ],
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))

# ── Gentleman's chest / chifforobe ────────────────────────────────────────────

_p(CabinetPreset(
    name="bedroom_gentleman_chest",
    display_name="Bedroom Gentleman's Chest — Door + 5 Drawer (2-Column)",
    description=(
        "1400×1200 mm two-column chest: left column is a full-height wardrobe "
        "door compartment (600 mm wide) for hanging garments; right column has "
        "five graduated drawers (746 mm wide). 550 mm depth. Covers "
        "gentleman's chest and chifforobe. Blum Tandem+ full-extension slides, "
        "floating-tenon carcass."
    ),
    category="bedroom",
    tags=["bedroom", "gentleman_chest", "chifforobe", "wardrobe", "door", "drawer",
          "multi_column", "wide", "full_extension"],
    difficulty="advanced",
    config=CabinetConfig(
        width=1400,
        height=1200,
        depth=550,
        openings=[],
        columns=[
            ColumnConfig(
                width_mm=600,
                # Left: single tall door = interior height 1164 mm
                openings=((1164, "door"),),
            ),
            ColumnConfig(
                width_mm=746,
                # Right: 5 drawers; 4×233 + 1×232 = 1164 mm
                openings=(
                    (233, "drawer"),
                    (233, "drawer"),
                    (233, "drawer"),
                    (233, "drawer"),
                    (232, "drawer"),
                ),
            ),
        ],
        drawer_slide="blum_tandem_plus_563h",
        door_hinge="blum_clip_top_110_full",
        carcass_joinery=CarcassJoinery.FLOATING_TENON,
    ),
))


# ── Bathroom linen tower ──────────────────────────────────────────────────────

_p(CabinetPreset(
    name="bathroom_linen_tower",
    display_name="Bathroom Linen Tower — Door + 2 Drawer",
    description=(
        "400×1900 mm tall narrow linen tower with a large door compartment "
        "below for towels and linens (adjustable shelves) and two drawers at "
        "the top for toiletries. 350 mm depth. Covers linen cabinet, linen "
        "tower, and linen press. BLUMOTION soft-close on both."
    ),
    category="bathroom",
    tags=["bathroom", "linen_tower", "linen_cabinet", "door", "drawer",
          "tall", "narrow", "soft_close", "shelf"],
    difficulty="standard",
    config=CabinetConfig(
        width=400,
        height=1900,
        depth=350,
        # Opening stack sums to 1864 mm (1900 - 18 - 18)
        openings=[
            (1514, "door"),   # tall door compartment at bottom
            (175,  "drawer"),
            (175,  "drawer"),
        ],
        adj_shelf_holes=True,
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))


# ── Bar / cocktail cabinet ────────────────────────────────────────────────────

_p(CabinetPreset(
    name="living_room_bar_cabinet",
    display_name="Living Room Bar Cabinet — Door Pair + 2 Drawer",
    description=(
        "900×1000 mm drinks cabinet with a door pair below for bottles and "
        "glassware storage and two drawers above for bar accessories. "
        "450 mm depth, adjustable shelves inside. Covers cocktail cabinet, "
        "bar cabinet, and drinks cabinet. BLUMOTION soft-close hinges."
    ),
    category="living_room",
    tags=["living_room", "bar_cabinet", "cocktail", "door_pair", "drawer",
          "shelf", "soft_close"],
    difficulty="standard",
    config=CabinetConfig(
        width=900,
        height=1000,
        depth=450,
        # Opening stack sums to 964 mm (1000 - 18 - 18)
        openings=[
            (600, "door_pair"),  # door pair at bottom for bottles/glassware
            (182, "drawer"),
            (182, "drawer"),
        ],
        adj_shelf_holes=True,
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))


# ── Filing cabinet ────────────────────────────────────────────────────────────

_p(CabinetPreset(
    name="office_filing_cabinet",
    display_name="Office Filing Cabinet — 4 Drawer",
    description=(
        "460×1300 mm vertical filing cabinet with four equal deep drawers "
        "for letter or legal files. 600 mm depth accommodates full-depth "
        "hanging file frames. Blum Movento heavy-duty full-extension slides "
        "rated for file loads. Pocket-screw carcass."
    ),
    category="office",
    tags=["office", "filing_cabinet", "drawer", "deep", "heavy_duty", "blum_movento"],
    difficulty="standard",
    config=CabinetConfig(
        width=460,
        height=1300,
        depth=600,
        # Opening stack sums to 1264 mm (1300 - 18 - 18); 4 × 316
        openings=[
            (316, "drawer"),
            (316, "drawer"),
            (316, "drawer"),
            (316, "drawer"),
        ],
        drawer_slide="blum_movento_769",
        door_hinge="blum_clip_top_110_full",
        carcass_joinery=CarcassJoinery.POCKET_SCREW,
    ),
))


# ── Entryway entry cabinet ────────────────────────────────────────────────────

_p(CabinetPreset(
    name="entryway_entry_cabinet",
    display_name="Entryway Entry Cabinet — Door Pair + Drawer",
    description=(
        "900×900 mm entryway cabinet with a door pair below for bags and "
        "shoes and one slim drawer at the top for keys and mail. "
        "350 mm shallow depth fits against a hallway wall. "
        "BLUMOTION soft-close hinges. Dado-rabbet carcass."
    ),
    category="entryway",
    tags=["entryway", "entry_cabinet", "console", "door_pair", "drawer",
          "shallow", "soft_close"],
    difficulty="basic",
    config=CabinetConfig(
        width=900,
        height=900,
        depth=350,
        # Opening stack sums to 864 mm (900 - 18 - 18)
        openings=[
            (764, "door_pair"),  # door pair at bottom
            (100, "drawer"),     # slim drawer at top
        ],
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))


# ── Hall tree ─────────────────────────────────────────────────────────────────

_p(CabinetPreset(
    name="entryway_hall_tree",
    display_name="Entryway Hall Tree — Door Pair + Drawers + Open",
    description=(
        "900×1900 mm tall entryway hall tree: door pair at the base for "
        "shoes and umbrellas, two drawers in the middle for keys and "
        "accessories, and a large open compartment at the top that sits "
        "behind coat hooks or a mirror. 380 mm depth. "
        "BLUMOTION soft-close. Dado-rabbet carcass."
    ),
    category="entryway",
    tags=["entryway", "hall_tree", "door_pair", "drawer", "open", "tall", "soft_close"],
    difficulty="standard",
    config=CabinetConfig(
        width=900,
        height=1900,
        depth=380,
        # Opening stack sums to 1864 mm (1900 - 18 - 18)
        openings=[
            (700,  "door_pair"),  # door pair at bottom
            (100,  "drawer"),     # drawer
            (100,  "drawer"),     # drawer
            (964,  "open"),       # open compartment at top (behind hooks / mirror)
        ],
        drawer_slide="blum_tandem_550h",
        door_hinge="blum_clip_top_blumotion_110_full",
        carcass_joinery=CarcassJoinery.DADO_RABBET,
    ),
))


# ─── Public API ───────────────────────────────────────────────────────────────

def get_preset(name: str) -> CabinetPreset:
    """Return the preset with the given slug, or raise KeyError."""
    if name not in PRESETS:
        available = ", ".join(sorted(PRESETS))
        raise KeyError(f"Unknown preset {name!r}. Available: {available}")
    return PRESETS[name]


def list_presets(
    category: str | None = None,
    tag: str | None = None,
) -> list[CabinetPreset]:
    """Return presets, optionally filtered by category and/or tag."""
    results = list(PRESETS.values())
    if category:
        results = [p for p in results if p.category == category]
    if tag:
        results = [p for p in results if tag in p.tags]
    return results
