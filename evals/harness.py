"""
Evaluation harness for the cabinet-design MCP server.

Runs each scenario's tool calls through the server handlers, evaluates
assertions, collects timing data, and produces a structured report.

The harness is pure Python — no actual MCP transport is involved.  It imports
the server handler functions directly, which means the eval runs in < 1 s even
for the full scenario catalogue.

Usage from Python::

    from evals.harness import run_all, print_report
    report = run_all()
    print_report(report)

Usage from the CLI::

    python -m evals                  # run everything
    python -m evals --tag kitchen    # only kitchen scenarios
    python -m evals --json           # machine-readable output
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any

from .scenarios import (
    ALL_TAGS,
    Assertion,
    Op,
    Scenario,
    ToolCall,
    SCENARIOS,
    scenarios_by_tag,
    scenarios_by_difficulty,
)

from cadquery_furniture.server import (
    _tool_list_hardware,
    _tool_list_joinery,
    _tool_design_cabinet,
    _tool_design_multi_column_cabinet,
    _tool_evaluate_cabinet,
    _tool_design_door,
    _tool_design_drawer,
    _tool_generate_cutlist,
    _tool_compare_joinery,
    _tool_list_presets,
    _tool_apply_preset,
    _tool_auto_fix_cabinet,
    _tool_describe_design,
    _tool_design_legs,
    _tool_design_pulls,
    _tool_suggest_proportions,
)

# ─── Tool dispatch ────────────────────────────────────────────────────────────

TOOL_DISPATCH = {
    "list_hardware":        _tool_list_hardware,
    "list_joinery_options": _tool_list_joinery,
    "design_cabinet":       _tool_design_cabinet,
    "evaluate_cabinet":     _tool_evaluate_cabinet,
    "design_door":          _tool_design_door,
    "design_drawer":        _tool_design_drawer,
    "generate_cutlist":     _tool_generate_cutlist,
    "compare_joinery":      _tool_compare_joinery,
    "list_presets":         _tool_list_presets,
    "apply_preset":         _tool_apply_preset,
    "auto_fix_cabinet":     _tool_auto_fix_cabinet,
    "describe_design":              _tool_describe_design,
    "design_legs":                  _tool_design_legs,
    "design_multi_column_cabinet":  _tool_design_multi_column_cabinet,
    "design_pulls":                 _tool_design_pulls,
    "suggest_proportions":          _tool_suggest_proportions,
}


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass
class AssertionResult:
    assertion: Assertion
    passed: bool
    actual: Any = None
    error: str = ""


@dataclass
class ToolCallResult:
    tool_call: ToolCall
    data: dict | None = None
    error: str = ""
    duration_ms: float = 0.0
    assertion_results: list[AssertionResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.error == ""
            and all(a.passed for a in self.assertion_results)
        )

    @property
    def assertions_passed(self) -> int:
        return sum(1 for a in self.assertion_results if a.passed)

    @property
    def assertions_total(self) -> int:
        return len(self.assertion_results)


@dataclass
class ScenarioResult:
    scenario: Scenario
    tool_results: list[ToolCallResult] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return all(t.passed for t in self.tool_results)

    @property
    def assertions_passed(self) -> int:
        return sum(t.assertions_passed for t in self.tool_results)

    @property
    def assertions_total(self) -> int:
        return sum(t.assertions_total for t in self.tool_results)

    @property
    def tool_calls_passed(self) -> int:
        return sum(1 for t in self.tool_results if t.passed)


@dataclass
class EvalReport:
    results: list[ScenarioResult] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def scenarios_passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def scenarios_total(self) -> int:
        return len(self.results)

    @property
    def assertions_passed(self) -> int:
        return sum(r.assertions_passed for r in self.results)

    @property
    def assertions_total(self) -> int:
        return sum(r.assertions_total for r in self.results)

    @property
    def pass_rate(self) -> float:
        if self.assertions_total == 0:
            return 1.0
        return self.assertions_passed / self.assertions_total

    @property
    def score(self) -> float:
        """Weighted score: each scenario contributes equally regardless of assertion count."""
        if not self.results:
            return 1.0
        per_scenario = []
        for r in self.results:
            if r.assertions_total == 0:
                per_scenario.append(1.0)
            else:
                per_scenario.append(r.assertions_passed / r.assertions_total)
        return sum(per_scenario) / len(per_scenario)

    def to_dict(self) -> dict:
        return {
            "summary": {
                "scenarios_passed": self.scenarios_passed,
                "scenarios_total":  self.scenarios_total,
                "assertions_passed": self.assertions_passed,
                "assertions_total": self.assertions_total,
                "pass_rate":        round(self.pass_rate, 4),
                "score":            round(self.score, 4),
                "duration_ms":      round(self.duration_ms, 1),
            },
            "scenarios": [
                {
                    "name":     r.scenario.name,
                    "passed":   r.passed,
                    "tags":     r.scenario.tags,
                    "difficulty": r.scenario.difficulty,
                    "assertions_passed": r.assertions_passed,
                    "assertions_total":  r.assertions_total,
                    "duration_ms": round(r.duration_ms, 1),
                    "failures": [
                        {
                            "tool": tr.tool_call.tool,
                            "label": tr.tool_call.label,
                            "assertion": ar.assertion.path,
                            "op":       ar.assertion.op.value,
                            "expected": ar.assertion.expected,
                            "actual":   ar.actual,
                            "error":    ar.error,
                        }
                        for tr in r.tool_results
                        for ar in tr.assertion_results
                        if not ar.passed
                    ] + (
                        [{"tool": tr.tool_call.tool, "label": tr.tool_call.label,
                          "error": tr.error}
                         for tr in r.tool_results if tr.error]
                    ),
                }
                for r in self.results
            ],
        }


# ─── Assertion evaluator ─────────────────────────────────────────────────────

class _MissingSentinel:
    """Singleton sentinel returned when a path does not resolve."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "<MISSING>"

    def __bool__(self):
        return False


MISSING = _MissingSentinel()


def _resolve_path(data: Any, path: str) -> Any:
    """Walk a dot-separated path into a nested dict/list structure.

    Supports integer indices for lists (e.g. ``"opening_stack.0.type"``).
    Returns ``MISSING`` if the path doesn't exist.
    """
    if not path:
        return data
    current = data
    for key in path.split("."):
        if isinstance(current, dict):
            current = current.get(key, MISSING)
        elif isinstance(current, list):
            try:
                current = current[int(key)]
            except (ValueError, IndexError):
                return MISSING
        else:
            return MISSING
        if current is MISSING:
            return MISSING
    return current


def evaluate_assertion(data: dict, assertion: Assertion) -> AssertionResult:
    """Evaluate a single assertion against tool output."""
    value = _resolve_path(data, assertion.path)
    missing = value is MISSING

    try:
        op = assertion.op
        exp = assertion.expected

        if op == Op.HAS_KEY:
            # The path itself must resolve to something
            passed = not missing
        elif missing:
            return AssertionResult(assertion, False, actual="<MISSING>",
                                   error=f"Path '{assertion.path}' not found in result")
        elif op == Op.EQ:
            passed = (value == exp)
        elif op == Op.APPROX:
            passed = abs(float(value) - float(exp)) < 0.15
        elif op == Op.GT:
            passed = float(value) > float(exp)
        elif op == Op.GTE:
            passed = float(value) >= float(exp)
        elif op == Op.LT:
            passed = float(value) < float(exp)
        elif op == Op.LTE:
            passed = float(value) <= float(exp)
        elif op == Op.IN:
            passed = value in exp
        elif op == Op.CONTAINS:
            passed = exp in value
        elif op == Op.LEN_EQ:
            passed = len(value) == int(exp)
        elif op == Op.LEN_GTE:
            passed = len(value) >= int(exp)
        elif op == Op.IS_TRUE:
            passed = bool(value) is True
        elif op == Op.IS_FALSE:
            passed = bool(value) is False
        elif op == Op.NO_ERRORS:
            passed = _resolve_path(data, "summary.errors") == 0
        elif op == Op.HAS_ERROR:
            passed = (_resolve_path(data, "summary.errors") or 0) > 0
        elif op == Op.HAS_WARNING:
            passed = (_resolve_path(data, "summary.warnings") or 0) > 0
        else:
            return AssertionResult(assertion, False, error=f"Unknown op: {op}")

        return AssertionResult(assertion, passed, actual=value)

    except Exception as exc:
        return AssertionResult(assertion, False, actual=value, error=str(exc))


# ─── Runner ───────────────────────────────────────────────────────────────────

def _run_sync(coro):
    """Run a coroutine; reuse an existing loop if available."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def run_tool_call(tc: ToolCall) -> ToolCallResult:
    """Execute a single tool call and evaluate its assertions."""
    handler = TOOL_DISPATCH.get(tc.tool)
    if handler is None:
        return ToolCallResult(tc, error=f"Unknown tool: {tc.tool}")

    t0 = time.perf_counter()
    try:
        result = _run_sync(handler(dict(tc.args)))
        duration_ms = (time.perf_counter() - t0) * 1000
    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        return ToolCallResult(tc, error=f"{type(exc).__name__}: {exc}",
                              duration_ms=duration_ms)

    # Parse the TextContent response
    text = result[0].text
    if text.startswith("ERROR:"):
        return ToolCallResult(tc, error=text, duration_ms=duration_ms)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return ToolCallResult(tc, error=f"JSON parse error: {exc}",
                              duration_ms=duration_ms)

    # Evaluate assertions
    assertion_results = [evaluate_assertion(data, a) for a in tc.assertions]

    return ToolCallResult(
        tool_call=tc,
        data=data,
        duration_ms=duration_ms,
        assertion_results=assertion_results,
    )


def run_scenario(scenario: Scenario) -> ScenarioResult:
    """Run all tool calls in a scenario and return results."""
    t0 = time.perf_counter()
    tool_results = [run_tool_call(tc) for tc in scenario.tool_calls]
    duration_ms = (time.perf_counter() - t0) * 1000
    return ScenarioResult(scenario=scenario, tool_results=tool_results,
                          duration_ms=duration_ms)


def run_all(
    scenarios: list[Scenario] | None = None,
    tags: list[str] | None = None,
    difficulty: str | None = None,
) -> EvalReport:
    """Run the eval suite and return a report.

    Parameters
    ----------
    scenarios : list, optional
        Explicit list of scenarios.  If None, uses the full catalogue.
    tags : list[str], optional
        Only run scenarios matching any of these tags.
    difficulty : str, optional
        Only run scenarios at this difficulty level.
    """
    pool = scenarios or SCENARIOS

    if tags:
        pool = [s for s in pool if any(t in s.tags for t in tags)]
    if difficulty:
        pool = [s for s in pool if s.difficulty == difficulty]

    t0 = time.perf_counter()
    results = [run_scenario(s) for s in pool]
    duration_ms = (time.perf_counter() - t0) * 1000

    return EvalReport(results=results, duration_ms=duration_ms)


# ─── Reporter ─────────────────────────────────────────────────────────────────

def print_report(report: EvalReport, verbose: bool = False) -> None:
    """Print a human-readable eval report to stdout."""
    print()
    print("=" * 72)
    print("  CABINET-MCP EVALUATION REPORT")
    print("=" * 72)
    print()
    print(f"  Scenarios:   {report.scenarios_passed}/{report.scenarios_total} passed")
    print(f"  Assertions:  {report.assertions_passed}/{report.assertions_total} passed")
    print(f"  Pass rate:   {report.pass_rate:.1%}")
    print(f"  Score:       {report.score:.1%}")
    print(f"  Duration:    {report.duration_ms:.0f} ms")
    print()

    # Per-scenario summary
    for r in report.results:
        status = "PASS" if r.passed else "FAIL"
        marker = "  " if r.passed else ">>"
        print(f"  {marker} [{status}] {r.scenario.name}"
              f"  ({r.assertions_passed}/{r.assertions_total})"
              f"  {r.duration_ms:.0f}ms"
              f"  [{', '.join(r.scenario.tags)}]")

        if not r.passed or verbose:
            for tr in r.tool_results:
                if not tr.passed or verbose:
                    label = tr.tool_call.label or tr.tool_call.tool
                    if tr.error:
                        print(f"       {label}: {tr.error}")
                    for ar in tr.assertion_results:
                        if not ar.passed:
                            desc = ar.assertion.description or ar.assertion.path
                            print(f"       FAIL  {desc}")
                            print(f"             {ar.assertion.op.value} "
                                  f"expected={ar.assertion.expected!r} "
                                  f"actual={ar.actual!r}")
                            if ar.error:
                                print(f"             error: {ar.error}")

    print()
    print("-" * 72)

    # Tag breakdown
    tag_stats: dict[str, tuple[int, int]] = {}
    for r in report.results:
        for tag in r.scenario.tags:
            p, t = tag_stats.get(tag, (0, 0))
            tag_stats[tag] = (p + (1 if r.passed else 0), t + 1)

    if tag_stats:
        print("  By tag:")
        for tag in sorted(tag_stats):
            p, t = tag_stats[tag]
            print(f"    {tag:20s} {p}/{t}")

    # Difficulty breakdown
    diff_stats: dict[str, tuple[int, int]] = {}
    for r in report.results:
        d = r.scenario.difficulty
        p, t = diff_stats.get(d, (0, 0))
        diff_stats[d] = (p + (1 if r.passed else 0), t + 1)

    if diff_stats:
        print("  By difficulty:")
        for d in ("basic", "standard", "advanced"):
            if d in diff_stats:
                p, t = diff_stats[d]
                print(f"    {d:20s} {p}/{t}")

    print("=" * 72)
    print()
