# cabinet-mcp

Design kitchen and furniture cabinets conversationally. Talk to Claude, get back validated configurations, optimised cutlists, and 3D geometry — with real Blum/Accuride/Salice hardware specs, five carcass joinery methods, and proportions rooted in traditional cabinet-making.

## Get started in two commands

```bash
uv pip install -e ".[full]"
claude mcp add cabinet -- uv --directory $(pwd) run cabinet-mcp
```

Then ask Claude anything:

> Design a 900 mm 3-drawer kitchen base with BLUMOTION slides and a classic drawer graduation.

> Make me a bathroom vanity with two doors and an inset shelf. Softclose hinges.

> Generate a cutlist for the workshop cabinet I just designed.

That's it. Claude drives the parametric engine through an MCP server — you never need to touch Python directly.

For Claude Desktop, Gemini CLI, or HTTP/SSE mode, see [docs/mcp.md](docs/mcp.md).

## Install options

| Command | What you get |
|---|---|
| `uv pip install -e ".[full]"` | **Recommended.** CadQuery (3D + HTML viewer) + rectpack (sheet optimizer) |
| `uv pip install -e ".[cad]"` | CadQuery only — 3D geometry, interference checks, HTML viewer |
| `uv pip install -e .` | **Lite.** Pure-Python only — parametric design, evaluation, cutlist BOM, MCP server |

With `uv run`, the full install is the default (configured via `default-groups = ["full", "dev"]` in `pyproject.toml`). To run in lite mode: `uv run --no-group full cabinet-mcp`.

## Using it from Python

```python
from cadquery_furniture.presets import get_preset
from cadquery_furniture.evaluation import evaluate_cabinet, print_report

cfg = get_preset("kitchen_base_3_drawer").config
print_report(evaluate_cabinet(cfg))
```

The parametric core, evaluation engine, and cutlist BOM all work in lite mode (no CadQuery). 3D geometry, interference checks, and the HTML viewer require the `cad` or `full` extra.

## What it knows

- **Hardware** — seven drawer slides, seven Blum Clip Top hinges, four furniture legs — [docs/hardware.md](docs/hardware.md)
- **Pulls and knobs** — 45 catalog entries (Top Knobs, Rockler, Richelieu, Hafele, IKEA) with placement policy, fit checks, and pack-quantity BOM math — [docs/pulls.md](docs/pulls.md)
- **Joinery** — four drawer corner joints and five carcass methods, all parametric — [docs/joinery.md](docs/joinery.md)
- **Proportions** — graduated drawers and asymmetric column widths via named ratios — [docs/proportions.md](docs/proportions.md)
- **Presets** — fourteen pre-validated starting points for kitchen, workshop, bedroom, bathroom, and living-room furniture — [docs/presets.md](docs/presets.md)
- **Evaluation** — clearances, deflection, geometry, joinery adequacy, pull fit/style; typed `Issue` objects with severity and measured values
- **Cutlist** — consolidated BOM with guillotine sheet optimisation (sheets used, waste %, physically executable layouts), JSON and CSV export; hardware BOM with pack-quantity / leftover math
- **Auto-repair** — single-pass fixer for common stack/rabbet errors
- **MCP server** — seventeen tools over stdio or HTTP/SSE — [docs/mcp.md](docs/mcp.md)
- **Eval harness** — 77 scenarios / 332 assertions, runs in under a second — [docs/evals.md](docs/evals.md)

For the module layout and data flow, see [docs/architecture.md](docs/architecture.md).

## Running tests

```bash
uv run pytest tests/ -v        # unit + integration
uv run python -m evals         # full scenario suite (< 1 second)
```

Neither requires CadQuery (CadQuery-dependent tests are skipped automatically in lite mode).

## Attributions

Hardware dimensions, placement rules, part numbers, and joinery references come from manufacturer datasheets and woodworking literature. See [ATTRIBUTIONS.md](ATTRIBUTIONS.md) for full citations.
