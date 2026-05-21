"""
Multi-cabinet projects.

A :class:`CabinetProject` bundles several :class:`CabinetConfig` instances
that are designed to live together (e.g. three matching sideboards, a wall
of base cabinets, a built-in run). The project owns a :class:`SharedDesign`
block of optional design tokens that get merged into each child cabinet at
construction time, so material thicknesses, joinery method, and hardware
brand stay consistent without having to repeat them on every child.

Downstream tools (``evaluate_project``, ``generate_project_cutlist``)
operate on the merged result — every child cabinet picks up the shared
tokens, then anything the child explicitly declared in its ``overrides``
set wins back.

The module is pure-Python — no CadQuery dependency — so it loads in lite
mode and can be exercised by the eval harness directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Optional

from .cabinet import CabinetConfig, ColumnConfig, OpeningConfig
from .joinery import (
    CarcassJoinery,
    DrawerJoineryStyle,
    DominoSpec,
    PocketScrewSpec,
    BiscuitSpec,
    DownelSpec,
)

# joinery.py spells the dowel spec class ``DownelSpec``; expose it under both
# names internally for clarity but use the canonical spelling externally.
DowelSpec = DownelSpec


# Fields on SharedDesign that map 1:1 to a CabinetConfig attribute.
# pull_preset is handled specially because it expands into two attributes.
_SHARED_FIELDS = (
    "side_thickness",
    "bottom_thickness",
    "top_thickness",
    "shelf_thickness",
    "back_thickness",
    "carcass_joinery",
    "drawer_joinery",
    "domino_spec",
    "pocket_screw_spec",
    "biscuit_spec",
    "dowel_spec",
    "drawer_slide",
    "door_hinge",
    "drawer_pull",
    "door_pull",
    "leg_key",
)


@dataclass(frozen=True)
class SharedDesign:
    """Design tokens that apply across every cabinet in a project.

    Every field is ``Optional[...]`` — ``None`` means "do not override; the
    child config keeps its own value." Anything set here is merged into each
    child :class:`CabinetConfig` at project-resolution time.
    """
    # Materials
    side_thickness:   Optional[float] = None
    bottom_thickness: Optional[float] = None
    top_thickness:    Optional[float] = None
    shelf_thickness:  Optional[float] = None
    back_thickness:   Optional[float] = None

    # Joinery
    carcass_joinery:  Optional[CarcassJoinery]     = None
    drawer_joinery:   Optional[DrawerJoineryStyle] = None
    domino_spec:        Optional[DominoSpec]       = None
    pocket_screw_spec:  Optional[PocketScrewSpec]  = None
    biscuit_spec:       Optional[BiscuitSpec]      = None
    dowel_spec:         Optional[DowelSpec]        = None

    # Hardware
    drawer_slide: Optional[str] = None
    door_hinge:   Optional[str] = None
    drawer_pull:  Optional[str] = None
    door_pull:    Optional[str] = None
    leg_key:      Optional[str] = None

    # Pull preset (resolved into drawer_pull / door_pull at merge time)
    pull_preset:  Optional[str] = None


@dataclass(frozen=True)
class ProjectCabinet:
    """One cabinet slot inside a project.

    ``name`` is the user-facing identifier (e.g. "left", "center", "right").
    It's used to tag generated outputs and to disambiguate evaluation issues.

    ``config`` carries the per-cabinet :class:`CabinetConfig`. Any field set
    on the project's ``shared`` block overrides the corresponding field on
    this config — UNLESS the child declared it via ``overrides``, in which
    case the child's value wins.
    """
    name: str
    config: CabinetConfig
    overrides: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class CabinetProject:
    """A set of cabinets designed to live together."""
    name: str
    cabinets: tuple[ProjectCabinet, ...]
    shared:   SharedDesign = field(default_factory=SharedDesign)
    notes:    str = ""

    def resolved(self) -> tuple[tuple[str, CabinetConfig], ...]:
        """Return ``((name, merged_config), ...)`` with shared tokens applied."""
        return tuple(
            (pc.name, _merge(pc.config, self.shared, pc.overrides))
            for pc in self.cabinets
        )


def _merge(
    cfg: CabinetConfig,
    shared: SharedDesign,
    overrides: frozenset[str],
) -> CabinetConfig:
    """Apply non-None shared tokens onto cfg, skipping anything in overrides."""
    updates: dict[str, Any] = {}

    # Handle pull_preset first — it expands into drawer_pull + door_pull, but
    # only if those two aren't already pinned by shared or by the child override.
    if shared.pull_preset is not None:
        from .hardware import get_pull_preset
        preset = get_pull_preset(shared.pull_preset)
        if "drawer_pull" not in overrides and shared.drawer_pull is None:
            updates["drawer_pull"] = preset.drawer_pull
        if "door_pull" not in overrides and shared.door_pull is None:
            updates["door_pull"] = preset.door_pull

    for name in _SHARED_FIELDS:
        value = getattr(shared, name)
        if value is None or name in overrides:
            continue
        updates[name] = value

    return replace(cfg, **updates) if updates else cfg


# ─── Persistence ──────────────────────────────────────────────────────────────


def project_dir() -> Path:
    """Directory under ~/.cabinet-mcp where serialized projects live."""
    return Path.home() / ".cabinet-mcp" / "projects"


def project_path(name: str) -> Path:
    """Filesystem path for a project's JSON snapshot."""
    return project_dir() / f"{name}.json"


def save_project(project: CabinetProject) -> Path:
    """Serialize a resolved project to ~/.cabinet-mcp/projects/<name>.json.

    Persisted form is the *resolved* configs — what the project actually
    designs to — alongside the original shared block and per-cabinet
    override sets. Downstream tools can reload via :func:`load_project`.
    """
    project_dir().mkdir(parents=True, exist_ok=True)
    path = project_path(project.name)
    path.write_text(json.dumps(project_to_dict(project), indent=2))
    return path


def load_project(name: str) -> CabinetProject:
    """Reconstruct a :class:`CabinetProject` from disk."""
    path = project_path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"Project {name!r} not found at {path}. "
            "Run design_project first or pass the inline 'project' payload."
        )
    return project_from_dict(json.loads(path.read_text()))


# ─── Dict <-> object conversion ───────────────────────────────────────────────


def _opening_to_dict(op: OpeningConfig) -> dict:
    out = {"height_mm": op.height_mm, "opening_type": op.opening_type}
    for k in ("hinge_key", "hinge_side", "pull_key", "num_doors", "door_thickness"):
        v = getattr(op, k)
        if v is not None:
            out[k] = v
    return out


def _column_to_dict(col: ColumnConfig) -> dict:
    return {
        "width_mm": col.width_mm,
        "openings": [_opening_to_dict(op) for op in col.openings],
    }


def _config_to_dict(cfg: CabinetConfig) -> dict:
    """Flatten a CabinetConfig back to a JSON-friendly dict (round-trippable
    via :func:`config_from_dict`)."""
    return {
        "width": cfg.width,
        "height": cfg.height,
        "depth": cfg.depth,
        "side_thickness":   cfg.side_thickness,
        "bottom_thickness": cfg.bottom_thickness,
        "top_thickness":    cfg.top_thickness,
        "shelf_thickness":  cfg.shelf_thickness,
        "back_thickness":   cfg.back_thickness,
        "dado_depth":         cfg.dado_depth,
        "back_rabbet_width":  cfg.back_rabbet_width,
        "back_rabbet_depth":  cfg.back_rabbet_depth,
        "fixed_shelf_positions": list(cfg.fixed_shelf_positions),
        "adj_shelf_holes":       cfg.adj_shelf_holes,
        "openings": [_opening_to_dict(op) for op in cfg.openings],
        "columns":  [_column_to_dict(col) for col in cfg.columns],
        "drawer_slide": cfg.drawer_slide,
        "door_hinge":   cfg.door_hinge,
        "drawer_pull":  cfg.drawer_pull,
        "door_pull":    cfg.door_pull,
        "door_hinge_side":    cfg.door_hinge_side,
        "door_pull_inset_mm": cfg.door_pull_inset_mm,
        "leg_key":   cfg.leg_key,
        "leg_count": cfg.leg_count,
        "leg_inset": cfg.leg_inset,
        "carcass_joinery": cfg.carcass_joinery.value,
        "drawer_joinery":  cfg.drawer_joinery.value,
    }


def config_from_dict(d: dict) -> CabinetConfig:
    """Inverse of :func:`_config_to_dict`. Also accepts the lighter shape
    produced by the ``design_cabinet`` MCP tool input — i.e. anything the
    server's ``_build_cabinet_config`` would accept."""
    # Import here to avoid a hard dependency cycle.
    from .server import _build_cabinet_config  # type: ignore[import-not-found]
    return _build_cabinet_config(dict(d))


def _shared_to_dict(shared: SharedDesign) -> dict:
    out: dict[str, Any] = {}
    for name in _SHARED_FIELDS + ("pull_preset",):
        v = getattr(shared, name)
        if v is None:
            continue
        if name in ("carcass_joinery", "drawer_joinery"):
            out[name] = v.value
        elif hasattr(v, "__dataclass_fields__"):
            # joinery specs — serialize as their field dict
            out[name] = {fk: getattr(v, fk) for fk in v.__dataclass_fields__}
        else:
            out[name] = v
    return out


def shared_from_dict(d: dict | None) -> SharedDesign:
    if not d:
        return SharedDesign()
    kwargs: dict[str, Any] = {}
    for k, v in d.items():
        if k == "carcass_joinery" and isinstance(v, str):
            kwargs[k] = CarcassJoinery(v)
        elif k == "drawer_joinery" and isinstance(v, str):
            kwargs[k] = DrawerJoineryStyle(v)
        elif k in ("domino_spec", "pocket_screw_spec", "biscuit_spec", "dowel_spec") and isinstance(v, dict):
            spec_cls = {
                "domino_spec": DominoSpec,
                "pocket_screw_spec": PocketScrewSpec,
                "biscuit_spec": BiscuitSpec,
                "dowel_spec": DowelSpec,
            }[k]
            kwargs[k] = spec_cls(**v)
        else:
            kwargs[k] = v
    return SharedDesign(**kwargs)


def project_to_dict(project: CabinetProject) -> dict:
    return {
        "name": project.name,
        "notes": project.notes,
        "shared": _shared_to_dict(project.shared),
        "cabinets": [
            {
                "name": pc.name,
                "config": _config_to_dict(pc.config),
                "overrides": sorted(pc.overrides),
            }
            for pc in project.cabinets
        ],
    }


def project_from_dict(d: dict) -> CabinetProject:
    shared = shared_from_dict(d.get("shared"))
    cabinets = tuple(
        ProjectCabinet(
            name=str(c["name"]),
            config=config_from_dict(c["config"]),
            overrides=frozenset(c.get("overrides", [])),
        )
        for c in d["cabinets"]
    )
    return CabinetProject(
        name=str(d["name"]),
        cabinets=cabinets,
        shared=shared,
        notes=str(d.get("notes", "")),
    )


# ─── Project builder from raw MCP-tool input ─────────────────────────────────


def build_project(payload: dict) -> CabinetProject:
    """Build a :class:`CabinetProject` from the MCP-tool payload.

    Expected shape::

        {
          "name": "kitchen_run",
          "shared": {... SharedDesign fields ...},
          "notes": "optional human-readable notes",
          "cabinets": [
            {"name": "left",   "config": {... design_cabinet args ...}},
            {"name": "center", "config": {...}},
            {"name": "right",  "config": {...}},
          ],
        }

    For each child cabinet, any key explicitly set in ``config`` and also
    present on ``shared`` is recorded as an override — so the child's value
    wins even though the shared tokens are merged in.
    """
    name = str(payload["name"])
    shared = shared_from_dict(payload.get("shared"))
    notes = str(payload.get("notes", ""))

    cabinets: list[ProjectCabinet] = []
    shared_keys = {
        k for k in _SHARED_FIELDS + ("pull_preset",)
        if getattr(shared, k) is not None
    }

    for entry in payload.get("cabinets", []):
        child_name = str(entry["name"])
        cfg_dict = dict(entry.get("config", {}))
        explicit_keys = set(cfg_dict.keys())
        overrides = frozenset(shared_keys & explicit_keys)
        cfg = config_from_dict(cfg_dict)
        cabinets.append(ProjectCabinet(
            name=child_name,
            config=cfg,
            overrides=overrides,
        ))

    return CabinetProject(
        name=name,
        cabinets=tuple(cabinets),
        shared=shared,
        notes=notes,
    )


# ─── Cross-cabinet checks ─────────────────────────────────────────────────────


def check_project_consistency(project: CabinetProject) -> list[dict]:
    """Run cross-cabinet sanity checks. Returns a list of issue dicts.

    Current checks:
      - depth match: every cabinet in the project shares the same depth
      - height match: every cabinet shares the same exterior height

    Both are warnings (not errors) — cabinets *can* legally differ on
    these axes, but in a matched run they almost always shouldn't.
    """
    issues: list[dict] = []
    resolved = project.resolved()
    if not resolved:
        return issues

    base_name, base_cfg = resolved[0]

    for name, cfg in resolved[1:]:
        if abs(cfg.depth - base_cfg.depth) > 0.5:
            issues.append({
                "severity": "warning",
                "check": "project_depth_match",
                "message": (
                    f"Cabinet {name!r} depth ({cfg.depth:.1f} mm) differs from "
                    f"{base_name!r} ({base_cfg.depth:.1f} mm) — adjacent cabinets "
                    "in a matched run usually share depth."
                ),
                "part_a": name,
                "part_b": base_name,
                "value": cfg.depth,
                "limit": base_cfg.depth,
            })
        if abs(cfg.height - base_cfg.height) > 0.5:
            issues.append({
                "severity": "warning",
                "check": "project_height_match",
                "message": (
                    f"Cabinet {name!r} height ({cfg.height:.1f} mm) differs from "
                    f"{base_name!r} ({base_cfg.height:.1f} mm) — cabinets in a "
                    "flush run usually share height."
                ),
                "part_a": name,
                "part_b": base_name,
                "value": cfg.height,
                "limit": base_cfg.height,
            })

    return issues
