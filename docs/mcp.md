# MCP server

`server.py` exposes the full pipeline as **thirty MCP tools**. The server runs over stdio by default; pass `--http` to run a persistent HTTP/SSE process instead.

(MCP — Model Context Protocol — is the plug-in standard that lets AI clients like Claude Code, Claude Desktop, and Gemini CLI call local tools. You register the server once; after that, everything happens in plain-English conversation.)

## Tools

### Discover

| Tool | What it does |
|---|---|
| `list_presets` | Browse the named preset catalogue; filter by category or tag |
| `apply_preset` | Load a preset config; optionally override individual fields |
| `list_hardware` | Catalogue of slides, hinges, legs, and pulls (keys, specs, clearances); `brand=` / `mount_style=` filters on pulls |
| `list_joinery_options` | Drawer and carcass joinery styles; Domino tenon sizes |
| `list_pull_presets` | Named pull bundles (drawer pull + door pull + orientation) |
| `identify_furniture_type` | Map a natural-language furniture name ("chiffoniere?") to the closest preset / opening layout |
| `suggest_proportions` | Compare all four proportion presets (equal / subtle / classic / golden) for a cabinet — [proportions.md](proportions.md) |

### Design

| Tool | What it does |
|---|---|
| `design_cabinet` | Parametric layout — panel sizes, opening stack, joinery; `num_drawers` + `drawer_proportion` for auto-graduated heights |
| `design_multi_column_cabinet` | Multi-column carcass; `num_columns` + `column_proportion` + `wide_index` for fully proportional auto-layout |
| `design_drawer` | Drawer box dimensions, joinery cut specs, standard-height snapping; optional pull block with placements and BOM |
| `design_door` | Door dimensions, hinge count, positions; optional pull block with per-leaf placements and BOM |
| `design_legs` | Leg placement coordinates, load-per-leg check, hardware BOM |
| `design_pulls` | Whole-cabinet pull pass — per-slot placements, style check, consolidated BOM with pack quantities — [pulls.md](pulls.md) |
| `compare_joinery` | Side-by-side drawer joinery cut dimensions for a stock thickness |

### Check and describe

| Tool | What it does |
|---|---|
| `evaluate_cabinet` | Full structural/fit evaluation; returns issues by severity with measured values |
| `auto_fix_cabinet` | One-pass deterministic repair of common errors (stack height, rabbet alignment) |
| `describe_design` | Prose summary (metric + imperial) for design review before visualization |

### Visualize

| Tool | What it does |
|---|---|
| `visualize_cabinet` | 3D assembly → self-contained HTML viewer; wood finishes, grain direction, open/x-ray/clip/diagnostic shortcuts — [viewer.md](viewer.md) |
| `visualize_project` | All cabinets of a project in one 3D scene at their run offsets, worktop included |

### Projects — [projects.md](projects.md)

| Tool | What it does |
|---|---|
| `design_project` | Multi-cabinet project with a shared design-token block; persists to `~/.cabineteer/projects/<name>.json`; refuses to overwrite unless asked |
| `list_projects` | Saved-project catalogue — names, cabinet counts, run widths, notes, modified times; `query=` filter, newest-first, dev-artifact hiding |
| `load_project` | Load a saved project back for continued editing or reuse |
| `update_project` | **Delta edits** — patch fields, rename/add/remove cabinets, adjust the worktop, all without re-describing the design |
| `rename_project` | Rename a snapshot (file + embedded name); refuses to overwrite |
| `duplicate_project` | Fork a design; the copy carries `forked_from` lineage forever |
| `delete_project` | Permanently delete a saved snapshot (confirm with the user first) |
| `evaluate_project` | Per-cabinet evaluation plus cross-cabinet consistency checks |

### Build documents

| Tool | What it does |
|---|---|
| `generate_cutlist` | Panel BOM with part IDs, sheet layouts (4 algorithms incl. shop-sequence `rips_first`), priced hardware BOM, HTML/PDF/CSV/JSON — [cutlists.md](cutlists.md) |
| `generate_project_cutlist` | Same for a whole project — or several projects batched into one purchase with per-project colors and labels |
| `generate_assembly_instructions` | Printable carcass assembly docs — joint census, mortise maps, machine setup, dry-fit-first steps — [assembly.md](assembly.md) |

## Recommended workflow

```
list_presets → apply_preset → evaluate_cabinet
            ↓ (if errors)
        auto_fix_cabinet → evaluate_cabinet
            ↓
        describe_design → user review → visualize_cabinet
            ↓
        design_project (save) → generate_project_cutlist → generate_assembly_instructions
```

Tool descriptions encode this sequence — the LLM is instructed never to skip evaluation or visualize before the user has approved the described design.

## Configure with Claude Code

One-liner — registers at user scope so it's available in every session:

```bash
claude mcp add cabineteer -- uv --directory /absolute/path/to/cabineteer run cabineteer
claude mcp list          # verify "cabineteer" connected
claude mcp remove cabineteer
```

Inside a Claude Code session, `/mcp` lists connected servers and their tools.

## Configure with Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "cabineteer": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/cabineteer", "run", "cabineteer"]
    }
  }
}
```

## Configure with Gemini CLI

`~/.gemini/settings.json`, stdio:

```json
{
  "mcp": {
    "servers": {
      "cabineteer": {
        "command": "uv",
        "args": ["--directory", "/absolute/path/to/cabineteer", "run", "cabineteer"]
      }
    }
  }
}
```

Or HTTP/SSE pointing at a running server:

```json
{
  "mcp": {
    "servers": {
      "cabineteer": { "url": "http://127.0.0.1:3749/sse" }
    }
  }
}
```

## HTTP/SSE mode

The default starting port is **3749**; it auto-increments if occupied, so running multiple servers never collides.

```bash
cabineteer --http                               # port 3749 (or next free)
cabineteer --http --port 4200
cabineteer --http --port 4200 --max-port-attempts 40
cabineteer --http --host 0.0.0.0                # bind all interfaces
```

The chosen port is printed to stderr and written to `/tmp/cabineteer.port`:

```bash
PORT=$(cat /tmp/cabineteer.port)
curl "http://127.0.0.1:${PORT}/sse"
```
