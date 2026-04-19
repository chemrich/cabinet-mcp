# Presets

`presets.py` ships fourteen named, pre-validated `CabinetConfig` instances. Each one has its opening-stack heights pre-calculated to fill `interior_height` exactly, so it passes `evaluate_cabinet` with zero issues. They're exposed via the `list_presets` and `apply_preset` MCP tools, and directly via `get_preset(name)` in Python.

| Name | Category | Dimensions (W×H×D) | Notes |
|------|----------|--------------------|-------|
| `kitchen_base_3_drawer` | kitchen | 600 × 720 × 550 | 300/192/192 mm stack, Blum Tandem 550H |
| `kitchen_base_door_2_drawer` | kitchen | 600 × 720 × 550 | Deep door at bottom, two drawers above |
| `kitchen_base_door_pair_wide` | kitchen | 900 × 720 × 550 | Door pair + 2 drawers, half-overlay hinges |
| `kitchen_tall_pantry` | kitchen | 600 × 2100 × 550 | Two door pairs + shelf section, BLUMOTION |
| `workshop_tool_chest` | workshop | 600 × 900 × 550 | 6 × 144 mm drawers, Movento 769 (77 kg), pocket-screw |
| `workshop_wall_cabinet` | workshop | 600 × 720 × 300 | Door pair + adjustable shelves, shallow depth |
| `bedroom_dresser` | bedroom | 900 × 1100 × 550 | 6-drawer, Tandem+ full-extension |
| `bathroom_vanity` | bathroom | 600 × 850 × 480 | Door + 2 drawers, BLUMOTION soft-close |
| `storage_wall_cabinet` | storage | 600 × 720 × 300 | Door pair + adjustable shelves |
| `foyer_console_2_drawer` | living_room | 1200 × 800 × 350 | Open shelf + 2 drawers, shallow |
| `foyer_console_narrow` | living_room | 900 × 850 × 300 | Single drawer + open shelf |
| `living_room_credenza` | living_room | 1600 × 800 × 450 | Door pair + 2 frieze drawers, Tandem+ / BLUMOTION |
| `living_room_sideboard` | living_room | 1800 × 900 × 500 | Door pair + 2 drawers, wider/taller than credenza |
| `media_console` | living_room | 1800 × 600 × 450 | Low-profile: door pair + open display shelf |

## Usage

```python
from dataclasses import replace
from cadquery_furniture.presets import get_preset
from cadquery_furniture.evaluation import evaluate_cabinet, print_report

cfg = get_preset("kitchen_base_3_drawer").config

# Presets are frozen — tweak via dataclasses.replace
cfg = replace(cfg, width=750, drawer_slide="blum_movento_760h")

print_report(evaluate_cabinet(cfg))
```

## Via MCP

```
list_presets(category="kitchen")
apply_preset(name="kitchen_base_3_drawer", overrides={"width": 750})
```
