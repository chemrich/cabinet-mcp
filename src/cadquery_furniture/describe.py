"""Human-readable design summaries for CabinetConfig.

Generates a concise prose description suitable for presenting to the user
during the review step of the design workflow.  The output is deliberately
plain English — dimensions in familiar terms, hardware by name, joinery
method, opening layout — so the user can approve or request changes before
moving to the visualizer.

The module has no CadQuery dependency.
"""

from __future__ import annotations

from .cabinet import CabinetConfig
from .drawer import DrawerConfig, DrawerJoineryStyle
from .hardware import HINGES, PULLS, SLIDES
from .joinery import CarcassJoinery


# ── Formatting helpers ───────────────────────────────────────────────────────

def _mm_to_ft_in(mm: float) -> str:
    """Return a natural imperial rendering for the given millimetre value.

    Examples: 1800 → "5 ft 11 in", 600 → "1 ft 11½ in", 18 → "¾ in".
    """
    total_in = mm / 25.4
    if total_in < 6:
        # Small dimensions → fractional inches to nearest 1/16.
        sixteenths = round(total_in * 16)
        whole = sixteenths // 16
        frac  = sixteenths % 16
        frac_str = {
            0:  "", 1: "¹⁄₁₆", 2: "⅛", 3: "³⁄₁₆", 4: "¼", 5: "⁵⁄₁₆",
            6: "⅜", 7: "⁷⁄₁₆", 8: "½", 9: "⁹⁄₁₆", 10: "⅝", 11: "¹¹⁄₁₆",
            12: "¾", 13: "¹³⁄₁₆", 14: "⅞", 15: "¹⁵⁄₁₆",
        }[frac]
        if whole and frac_str:
            return f"{whole}{frac_str} in"
        if whole:
            return f"{whole} in"
        return f"{frac_str or '0'} in"

    feet = int(total_in // 12)
    inches = total_in - feet * 12
    if inches < 0.1:
        return f"{feet} ft"
    return f"{feet} ft {inches:.0f} in"


def _fmt_dim(mm: float) -> str:
    """Combined metric + imperial formatting, e.g. '1800 mm (5 ft 11 in)'."""
    return f"{mm:.0f} mm ({_mm_to_ft_in(mm)})"


def _joinery_name(j: CarcassJoinery) -> str:
    return {
        CarcassJoinery.DADO_RABBET:    "dado-and-rabbet",
        CarcassJoinery.FLOATING_TENON: "floating-tenon (Domino)",
        CarcassJoinery.POCKET_SCREW:   "pocket-screw",
        CarcassJoinery.BISCUIT:        "biscuit",
        CarcassJoinery.DOWEL:          "dowel",
    }.get(j, j.value)


def _drawer_joinery_name(j: DrawerJoineryStyle) -> str:
    return {
        DrawerJoineryStyle.BUTT:         "butt joint",
        DrawerJoineryStyle.QQQ:          "lock-rabbet (QQQ)",
        DrawerJoineryStyle.HALF_LAP:     "half-lap",
        DrawerJoineryStyle.DRAWER_LOCK:  "drawer-lock joint",
    }.get(j, j.value)


def _default_drawer_joinery() -> DrawerJoineryStyle:
    """Return the current default DrawerJoineryStyle from DrawerConfig."""
    return DrawerConfig.__dataclass_fields__["joinery_style"].default


def _slot_phrase(count: int, label: str) -> str:
    """Pluralize a slot label.  2, 'drawer' → 'two drawers'."""
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
             6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
    n = words.get(count, str(count))
    if count == 1:
        return f"{n} {label}"
    # Simple pluralization — works for the vocabulary we use.
    plural = label + ("s" if not label.endswith("s") else "")
    if label == "door_pair":
        plural = "door pairs"
    return f"{n} {plural}"


# ── Public API ───────────────────────────────────────────────────────────────

def describe_design(cfg: CabinetConfig) -> dict:
    """Return a structured description + a prose summary of a CabinetConfig.

    The return value includes both a human-readable ``prose`` string (for
    dropping straight into a chat message) and the structured bits that
    generated it (``dimensions``, ``openings``, ``hardware``, ``materials``)
    so a client can rearrange or re-render the information if desired.
    """
    # ── 1. Dimensions ─────────────────────────────────────────────────────────
    dimensions = {
        "exterior": {
            "width_mm":  cfg.width,
            "height_mm": cfg.height,
            "depth_mm":  cfg.depth,
            "pretty":    f"{_fmt_dim(cfg.width)} wide × "
                         f"{_fmt_dim(cfg.height)} tall × "
                         f"{_fmt_dim(cfg.depth)} deep",
        },
        "interior": {
            "width_mm":  cfg.interior_width,
            "height_mm": cfg.interior_height,
            "depth_mm":  cfg.interior_depth,
        },
    }

    # ── 2. Opening layout ────────────────────────────────────────────────────
    ops = list(cfg.openings)
    counts: dict[str, int] = {}
    for op in ops:
        counts[op.opening_type] = counts.get(op.opening_type, 0) + 1
    stack_total = sum(op.height_mm for op in ops)

    openings = {
        "stack_from_bottom": [
            {"height_mm": float(op.height_mm), "type": op.opening_type} for op in ops
        ],
        "total_stack_height_mm":  stack_total,
        "interior_height_mm":     cfg.interior_height,
        "stack_fills_interior":   abs(stack_total - cfg.interior_height) < 0.5,
        "counts": counts,
    }

    if ops:
        parts = [_slot_phrase(counts[k], k) for k in sorted(counts)]
        layout_phrase = ", ".join(parts[:-1])
        if layout_phrase:
            layout_phrase = f"{layout_phrase} and {parts[-1]}"
        else:
            layout_phrase = parts[-1]
        stack_desc = (
            f"{layout_phrase} stacked from bottom to top — "
            + ", ".join(f"{int(op.height_mm)} mm {op.opening_type}" for op in ops)
        )
    else:
        stack_desc = "an open carcass with no fixed openings"

    # ── 3. Hardware ──────────────────────────────────────────────────────────
    slide = SLIDES.get(cfg.drawer_slide)
    hinge = HINGES.get(cfg.door_hinge)
    has_drawers = any(op.opening_type == "drawer" for op in ops)
    has_doors   = any(op.opening_type in ("door", "door_pair") for op in ops)

    hardware: dict = {}
    hardware_phrases: list[str] = []
    if slide and has_drawers:
        hardware["drawer_slide"] = {
            "key":          cfg.drawer_slide,
            "name":         slide.name,
            "max_load_kg":  slide.max_load_kg,
        }
        soft = " (soft-close)" if "soft" in slide.name.lower() or "blumotion" in slide.name.lower() else ""
        hardware_phrases.append(f"{slide.name}{soft} drawer slides rated to {slide.max_load_kg:.0f} kg")
    if hinge and has_doors:
        hardware["door_hinge"] = {
            "key":          cfg.door_hinge,
            "name":         hinge.name,
            "overlay_type": hinge.overlay_type.value,
            "soft_close":   hinge.soft_close,
        }
        soft = " soft-close" if hinge.soft_close else ""
        overlay = hinge.overlay_type.value.replace("_", "-")
        hardware_phrases.append(f"{hinge.name}{soft} hinges ({overlay} overlay)")

    pull_selection_required = False
    drawer_pull_spec = PULLS.get(cfg.drawer_pull or "")
    door_pull_spec   = PULLS.get(cfg.door_pull or "")
    if drawer_pull_spec and has_drawers:
        hardware["drawer_pull"] = {
            "key":  cfg.drawer_pull,
            "name": drawer_pull_spec.name,
        }
        hardware_phrases.append(f"{drawer_pull_spec.name} drawer pulls")
    elif has_drawers and not cfg.drawer_pull:
        pull_selection_required = True
    if door_pull_spec and has_doors:
        hardware["door_pull"] = {
            "key":  cfg.door_pull,
            "name": door_pull_spec.name,
        }
        if not drawer_pull_spec:
            hardware_phrases.append(f"{door_pull_spec.name} door pulls")
    elif has_doors and not cfg.door_pull:
        pull_selection_required = True

    # ── 4. Materials + joinery ───────────────────────────────────────────────
    drawer_joinery = getattr(cfg, "drawer_joinery", _default_drawer_joinery())
    materials = {
        "carcass_joinery":        cfg.carcass_joinery.value,
        "drawer_box_joinery":     drawer_joinery.value,
        "side_thickness_mm":      cfg.side_thickness,
        "back_thickness_mm":      cfg.back_thickness,
        "shelf_thickness_mm":     cfg.shelf_thickness,
        "adj_shelf_holes":        cfg.adj_shelf_holes,
    }
    material_phrase = (
        f"{_mm_to_ft_in(cfg.side_thickness)} carcass panels with a "
        f"{_mm_to_ft_in(cfg.back_thickness)} back, "
        f"{_joinery_name(cfg.carcass_joinery)} carcass joinery"
    )
    if has_drawers:
        material_phrase += f", {_drawer_joinery_name(drawer_joinery)} drawer-box corners"
    if cfg.adj_shelf_holes:
        material_phrase += ", 32-mm adjustable shelf-pin holes"
    if cfg.fixed_shelf_positions:
        n = len(cfg.fixed_shelf_positions)
        material_phrase += f", {n} fixed shelf{'es' if n > 1 else ''}"

    # ── 5. Prose summary ─────────────────────────────────────────────────────
    lines = [
        f"Cabinet: {dimensions['exterior']['pretty']}.",
        f"Layout: {stack_desc}.",
    ]
    if hardware_phrases:
        lines.append("Hardware: " + "; ".join(hardware_phrases) + ".")
    lines.append("Construction: " + material_phrase + ".")

    if not openings["stack_fills_interior"] and ops:
        delta = stack_total - cfg.interior_height
        lines.append(
            f"⚠ Opening stack does not fill interior "
            f"(off by {delta:+.0f} mm). Run auto_fix_cabinet or adjust "
            f"drawer_config before visualizing."
        )
    if pull_selection_required:
        lines.append(
            "⚠ No pull hardware selected. Ask the user to choose a pull style "
            "(call list_pull_presets) before calling visualize_cabinet."
        )

    prose = " ".join(lines)

    return {
        "prose":                   prose,
        "dimensions":              dimensions,
        "openings":                openings,
        "hardware":                hardware,
        "materials":               materials,
        "pull_selection_required": pull_selection_required,
    }
