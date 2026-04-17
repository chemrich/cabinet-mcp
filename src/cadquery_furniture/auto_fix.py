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
from dataclasses import dataclass, field
from typing import Callable

from .cabinet import CabinetConfig
from .evaluation import Issue, Severity, evaluate_cabinet


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

def _fix_cumulative_heights(
    cfg: CabinetConfig,
    issues: list[Issue],
) -> tuple[CabinetConfig, list[str]]:
    """Scale the opening stack so its heights sum exactly to ``interior_height``.

    We handle both directions:
      - overage  (stack > interior) → shrink every slot proportionally
      - shortfall (stack < interior) → grow the tallest slot to absorb the gap

    Proportional scaling preserves the designer's intent (ratio of drawer
    heights to door heights) while making the arithmetic close.  We nudge the
    largest residual mm onto the biggest slot so the sum is *exact* and
    re-evaluation passes cleanly.
    """
    if not cfg.drawer_config:
        return cfg, []

    interior = cfg.interior_height
    total    = sum(h for h, _ in cfg.drawer_config)
    if abs(total - interior) < 0.01:
        return cfg, []

    notes: list[str] = []
    stack = [(float(h), t) for h, t in cfg.drawer_config]

    if total > interior:
        # Shrink every slot proportionally, then round to 1 mm.
        scale = interior / total
        new_stack = [(round(h * scale), t) for h, t in stack]
        reason = "overshoots interior"
    else:
        # Grow the tallest slot to absorb the whole gap.
        new_stack = stack.copy()
        idx = max(range(len(stack)), key=lambda k: stack[k][0])
        new_h = round(stack[idx][0] + (interior - total))
        new_stack[idx] = (new_h, stack[idx][1])
        reason = "underruns interior"

    # Reconcile residuals so the new sum is exactly the interior height.
    drift = round(interior - sum(h for h, _ in new_stack))
    if drift != 0:
        idx = max(range(len(new_stack)), key=lambda k: new_stack[k][0])
        h, t = new_stack[idx]
        new_stack[idx] = (h + drift, t)

    cfg.drawer_config = new_stack
    notes.append(
        f"Opening stack {reason} ({total:.0f} mm vs {interior:.0f} mm). "
        f"Rebalanced to: {[f'{int(h)}mm {t}' for h, t in new_stack]}."
    )
    return cfg, notes


def _fix_back_panel_fit(
    cfg: CabinetConfig,
    issues: list[Issue],
) -> tuple[CabinetConfig, list[str]]:
    """Align back-panel rabbet depth with the back-panel thickness.

    The evaluator flags ``back_panel_fit`` when
    ``back_rabbet_depth != back_thickness`` — a geometry mismatch that makes
    the back panel sit proud or recessed.  Aligning them is safe and
    deterministic.
    """
    if abs(cfg.back_rabbet_depth - cfg.back_thickness) < 0.01:
        return cfg, []

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
