"""Deterministic single-pass auto-fix for common cabinet configuration errors.

The evaluator (``evaluation.evaluate_cabinet``) returns ``Issue`` objects.  A
subset of those issues can be resolved mechanically — e.g. a drawer stack that
overshoots the interior height can be scaled down, a back-panel rabbet mismatch
can be realigned, etc.  Everything else is left alone for a human (or the LLM)
to address.

Design choices:
- Returns a NEW ``CabinetConfig`` rather than mutating in place, so callers can
  diff the before/after if they want.
- Every change is recorded as a human-readable string in ``AutoFixResult.changes``
  so the calling tool can narrate what happened.
- Each fixer targets a single ``check`` name from ``evaluation.py`` and is only
  invoked when that issue is present.  Adding new fixers is a matter of writing
  another ``_fix_<check>`` function and registering it in ``_FIXERS``.

The module has no CadQuery dependency and runs in pure-Python environments.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Callable

from .cabinet import CabinetConfig
from .drawer import DrawerConfig
from .evaluation import Issue, Severity, evaluate_cabinet

# Leave a hair of the interior unfilled so a successfully-rebalanced stack does
# not itself trip the "stack exactly fills interior" warning in
# check_cumulative_heights.  1 mm is imperceptible and comfortably above the
# 0.01 mm tolerance that check uses.
_FILL_EPSILON_MM: float = 1.0


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class AutoFixResult:
    """Outcome of a single auto-fix pass."""
    config: CabinetConfig                           # possibly-modified config
    changes: list[str] = field(default_factory=list)
    initial_issues: list[Issue] = field(default_factory=list)
    final_issues: list[Issue] = field(default_factory=list)

    @property
    def fixed(self) -> bool:
        """True iff we resolved at least one error-severity issue."""
        initial_errors = sum(1 for i in self.initial_issues if i.severity == Severity.ERROR)
        final_errors   = sum(1 for i in self.final_issues   if i.severity == Severity.ERROR)
        return final_errors < initial_errors

    @property
    def clean(self) -> bool:
        """True iff no error-severity issues remain."""
        return not any(i.severity == Severity.ERROR for i in self.final_issues)


# ── Public entry point ───────────────────────────────────────────────────────

def auto_fix_cabinet(cfg: CabinetConfig, issues: list[Issue] | None = None) -> AutoFixResult:
    """Run a single auto-fix pass on ``cfg``.

    If ``issues`` is omitted, the evaluator is run first.  After attempting
    fixes, the evaluator is re-run so ``result.final_issues`` reflects the
    new state.

    Only ERROR-severity issues trigger fixes; WARNINGs and INFOs are left
    alone (they may become errors in a later pass but aren't worth the churn
    of a single-shot fixer).
    """
    if issues is None:
        issues = evaluate_cabinet(cab_cfg=cfg)

    new_cfg = copy.deepcopy(cfg)
    changes: list[str] = []

    # Apply fixers in deterministic order.  Each fixer filters the issues list
    # itself so we don't need to pre-group.
    for check_name, fixer in _FIXERS.items():
        relevant = [i for i in issues if i.check == check_name and i.severity == Severity.ERROR]
        if not relevant:
            continue
        new_cfg, fix_notes = fixer(new_cfg, relevant)
        changes.extend(fix_notes)

    # Re-evaluate to produce final_issues.
    final_issues = evaluate_cabinet(cab_cfg=new_cfg)

    return AutoFixResult(
        config=new_cfg,
        changes=changes,
        initial_issues=issues,
        final_issues=final_issues,
    )


# ── Individual fixers ────────────────────────────────────────────────────────

def _min_opening_height(cfg: CabinetConfig, opening_type: str) -> float:
    """Smallest opening height that keeps a slot within hardware limits.

    Only drawer slots have a meaningful floor: the slide's minimum box height
    plus the deductions ``box_height`` applies (bottom clearance + vertical
    gap).  Non-drawer slots (door/shelf/open) return 0 — they have no lower
    bound imposed by this fixer.
    """
    if opening_type != "drawer":
        return 0.0
    slide = DrawerConfig(
        opening_width=cfg.interior_width,
        opening_height=1.0,  # placeholder; only slide-derived constants are read
        opening_depth=cfg.interior_depth,
        slide_key=cfg.drawer_slide,
    ).slide
    return slide.min_drawer_height + slide.min_bottom_clearance + DrawerConfig.vertical_gap


def _fix_cumulative_heights(
    cfg: CabinetConfig,
    issues: list[Issue],
) -> tuple[CabinetConfig, list[str]]:
    """Rebalance the opening stack so its heights fit within ``interior_height``.

    We handle both directions:
      - overage  (stack > interior) → shrink every slot proportionally
      - shortfall (stack < interior) → grow the tallest slot to absorb the gap

    Design guarantees (see review findings #4/#5/#9):
      * **Fits, doesn't overfill.** The target is ``interior − epsilon`` so a
        successful fix does not itself trip the "stack exactly fills interior"
        warning.  All rounding uses whole-mm floors and distributes the leftover
        onto slots, so the final sum is ``≤ target`` even for fractional
        interiors (imperial ¾″ stock).
      * **Respects hardware minimums.** Drawer slots are clamped to the slide's
        minimum opening height; if the clamped minimums already exceed the
        target the fixer shrinks what it can and reports that it could not fully
        resolve the overage.
      * **Preserves graduation.** Leftover millimetres are handed to the tallest
        slots first, so the bottom (largest) drawer stays largest.
    """
    if not cfg.openings:
        return cfg, []

    from .cabinet import OpeningConfig
    interior = cfg.interior_height
    total    = sum(op.height_mm for op in cfg.openings)
    if abs(total - interior) < 0.01:
        return cfg, []

    target = interior - _FILL_EPSILON_MM
    mins = [_min_opening_height(cfg, op.opening_type) for op in cfg.openings]
    notes: list[str] = []

    if total > interior:
        # Proportionally scale toward the target, then floor each to whole mm and
        # clamp up to the per-slot hardware minimum.
        scale = target / total
        heights = [max(mins[i], math.floor(op.height_mm * scale))
                   for i, op in enumerate(cfg.openings)]
        reason = "overshoots interior"
    else:
        # Shortfall: grow the tallest opening to absorb the gap (floored so we
        # never cross the target).
        heights = [op.height_mm for op in cfg.openings]
        idx = max(range(len(heights)), key=lambda k: heights[k])
        heights[idx] = math.floor(heights[idx] + (target - total))
        reason = "underruns interior"

    # Distribute the leftover (target − sum) one mm at a time onto the tallest
    # slots that are still allowed to grow, preserving the tallest-at-bottom
    # graduation.  Because we floored above, leftover is ≥ 0 in the overage case.
    leftover = int(math.floor(target - sum(heights)))
    order = sorted(range(len(heights)), key=lambda k: heights[k], reverse=True)
    j = 0
    while leftover > 0 and order:
        heights[order[j % len(order)]] += 1
        leftover -= 1
        j += 1

    new_sum = sum(heights)
    if new_sum > interior + 0.01:
        # Clamping to hardware minimums prevented a full fit; report honestly.
        notes.append(
            f"Opening stack {reason} ({total:.0f} mm vs interior {interior:.0f} mm). "
            f"Shrank to {new_sum:.0f} mm, but per-slot slide minimums prevent "
            f"fitting within the interior — increase cabinet height or reduce the "
            f"number of drawers."
        )
    else:
        notes.append(
            f"Opening stack {reason} ({total:.0f} mm vs interior {interior:.0f} mm). "
            f"Rebalanced to {new_sum:.0f} mm: "
            f"{[f'{int(h)}mm {op.opening_type}' for h, op in zip(heights, cfg.openings)]}."
        )

    cfg.openings = [
        OpeningConfig(
            height_mm=h, opening_type=op.opening_type,
            hinge_key=op.hinge_key, hinge_side=op.hinge_side,
            pull_key=op.pull_key, num_doors=op.num_doors,
            door_thickness=op.door_thickness,
        )
        for h, op in zip(heights, cfg.openings)
    ]
    return cfg, notes


def _fix_back_panel_fit(
    cfg: CabinetConfig,
    issues: list[Issue],
) -> tuple[CabinetConfig, list[str]]:
    """Align back-panel rabbet depth with the back-panel thickness.

    The evaluator flags ``back_panel_fit`` when ``back_thickness >
    back_rabbet_depth`` (the back would sit proud) or when ``back_rabbet_depth >
    side_thickness`` (the rabbet can't be cut that deep).  Setting the rabbet
    depth equal to the back thickness resolves the "proud" case.

    But if ``back_thickness ≥ side_thickness`` we cannot make the rabbet as deep
    as the back without blowing through the side panel — so we refuse to create
    an impossible geometry (which the evaluator now catches) and instead report
    that the back stock is too thick for the side panel.
    """
    if abs(cfg.back_rabbet_depth - cfg.back_thickness) < 0.01:
        return cfg, []

    if cfg.back_thickness >= cfg.side_thickness:
        # Deepening the rabbet to back_thickness would make it ≥ side_thickness
        # (rabbet blows through the side panel). Leave the config unchanged and
        # let the human pick thinner back stock or thicker sides.
        return cfg, [
            f"Cannot align back_rabbet_depth to back_thickness "
            f"({cfg.back_thickness:.0f} mm): that meets or exceeds side "
            f"thickness ({cfg.side_thickness:.0f} mm), so the rabbet would blow "
            f"through the side panel. Use thinner back stock or thicker sides."
        ]

    old_depth = cfg.back_rabbet_depth
    cfg.back_rabbet_depth = cfg.back_thickness
    return cfg, [
        f"Aligned back_rabbet_depth ({old_depth:.0f} mm → "
        f"{cfg.back_thickness:.0f} mm) with back_thickness."
    ]


# Ordered registry: the fix for cumulative heights runs first because it can
# change panel counts/positions that other fixers might inspect.
_FIXERS: dict[str, Callable[[CabinetConfig, list[Issue]], tuple[CabinetConfig, list[str]]]] = {
    "cumulative_heights": _fix_cumulative_heights,
    "back_panel_fit":     _fix_back_panel_fit,
}


# ── Introspection helpers ────────────────────────────────────────────────────

def fixable_checks() -> list[str]:
    """Return the list of ``Issue.check`` names this module knows how to fix."""
    return list(_FIXERS.keys())
