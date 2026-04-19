# cadquery-furniture

Design kitchen and furniture cabinets conversationally. An MCP server drives a parametric core that emits validated configurations, 3D geometry, and optimised cutlists — with real Blum/Accuride/Salice hardware, five carcass joinery methods, and a proportion system rooted in traditional cabinet-making.

## Quick start — via Claude Code

```bash
pip install -e .
claude mcp add cabinet -- uv --directory $(pwd) run cabinet-mcp
```

Then ask Claude:

> Design a 900 mm 3-drawer kitchen base with BLUMOTION slides and a classic drawer graduation.

For Claude Desktop, Gemini CLI, or HTTP/SSE mode, see [docs/mcp.md](docs/mcp.md).

## Quick start — from Python

The parametric core doesn't require CadQuery:

```python
from cadquery_furniture.presets import get_preset
from cadquery_furniture.evaluation import evaluate_cabinet, print_report

cfg = get_preset("kitchen_base_3_drawer").config
print_report(evaluate_cabinet(cfg))
```

Install `cadquery` on top if you want 3D geometry and interference checks:

```bash
pip install cadquery && pip install -e .
```

## What it knows

- **Hardware** — seven drawer slides, seven Blum Clip Top hinges, four furniture legs — [docs/hardware.md](docs/hardware.md)
- **Joinery** — four drawer corner joints and five carcass methods, all parametric — [docs/joinery.md](docs/joinery.md)
- **Proportions** — graduated drawers and asymmetric column widths via named ratios — [docs/proportions.md](docs/proportions.md)
- **Starting points** — fourteen pre-validated presets for kitchen, workshop, bedroom, bathroom, and living-room furniture — [docs/presets.md](docs/presets.md)
- **Evaluation** — clearances, deflection, geometry, joinery adequacy; typed `Issue` objects with severity and measured values
- **Cutlist** — consolidated BOM in cut-optimizer-2d JSON and CSV; grain direction tracked
- **Auto-repair** — single-pass fixer for common stack/rabbet errors
- **MCP server** — fifteen tools over stdio or HTTP/SSE — [docs/mcp.md](docs/mcp.md)
- **Eval harness** — 62 scenarios / 250 assertions, runs in under a second — [docs/evals.md](docs/evals.md)

For the module layout and data flow, see [docs/architecture.md](docs/architecture.md).

## Testing

```bash
pytest tests/ -v        # unit + integration
python -m evals         # full scenario suite
```

Neither requires CadQuery.

## Attributions

Hardware dimensions, placement rules, part numbers, and joinery references come from manufacturer datasheets and woodworking literature. See [ATTRIBUTIONS.md](ATTRIBUTIONS.md) for full citations.
