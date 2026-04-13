"""
CLI entry point for running cabinet-mcp evaluations.

Usage::

    python -m evals                      # run all scenarios
    python -m evals --tag kitchen        # only kitchen scenarios
    python -m evals --tag drawer --tag door  # drawer + door
    python -m evals --difficulty basic    # only basic scenarios
    python -m evals --json               # JSON output (for CI / scripting)
    python -m evals --verbose            # show passing assertions too
    python -m evals --list               # list scenarios without running
"""

import argparse
import json
import sys

from .harness import run_all, print_report
from .scenarios import SCENARIOS, ALL_TAGS


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m evals",
        description="Run the cabinet-mcp evaluation suite.",
    )
    parser.add_argument(
        "--tag", action="append", dest="tags", metavar="TAG",
        help=f"Only run scenarios with this tag. Repeatable. Tags: {', '.join(ALL_TAGS)}",
    )
    parser.add_argument(
        "--difficulty", choices=["basic", "standard", "advanced"],
        help="Only run scenarios at this difficulty.",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output machine-readable JSON instead of the human-readable table.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show details for passing assertions too.",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_only",
        help="List available scenarios and exit.",
    )
    parser.add_argument(
        "--name", action="append", dest="names", metavar="SCENARIO",
        help="Run only the named scenario(s). Repeatable.",
    )

    args = parser.parse_args()

    if args.list_only:
        print(f"\n{'Name':40s} {'Difficulty':12s} {'Tags':30s} Calls")
        print("-" * 92)
        for s in SCENARIOS:
            print(f"{s.name:40s} {s.difficulty:12s} {', '.join(s.tags):30s} {len(s.tool_calls)}")
        print(f"\n{len(SCENARIOS)} scenarios total.  Tags: {', '.join(ALL_TAGS)}\n")
        return

    # Filter by name if provided
    pool = SCENARIOS
    if args.names:
        name_set = set(args.names)
        pool = [s for s in pool if s.name in name_set]
        if not pool:
            print(f"No scenarios matched: {args.names}", file=sys.stderr)
            sys.exit(1)

    report = run_all(scenarios=pool, tags=args.tags, difficulty=args.difficulty)

    if args.json_output:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report, verbose=args.verbose)

    # Exit code: 0 if everything passed, 1 if any failures
    sys.exit(0 if report.scenarios_passed == report.scenarios_total else 1)


if __name__ == "__main__":
    main()
