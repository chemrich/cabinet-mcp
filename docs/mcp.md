# MCP server

`server.py` exposes the full pipeline as fifteen MCP tools. The server runs over stdio by default; pass `--http` to run a persistent HTTP/SSE process instead.

## Tools

| Tool | What it does |
|---|---|
| `list_presets` | Browse the named preset catalogue; filter by category or tag |
| `apply_preset` | Load a preset config dict; optionally override individual fields |
| `list_hardware` | Catalogue of slides, hinges, and legs (keys, specs, clearances) |
| `list_joinery_options` | Drawer and carcass joinery styles; Domino tenon sizes |
| `design_cabinet` | Parametric layout — panel sizes, opening stack, joinery; accepts `num_drawers` + `drawer_proportion` for auto-graduated heights |
| `design_multi_column_cabinet` | Multi-column carcass; accepts `num_columns` + `column_proportion` + `wide_index` plus `num_drawers` + `drawer_proportion` for fully proportional auto-layout |
| `evaluate_cabinet` | Full structural/fit evaluation; returns issues by severity |
| `auto_fix_cabinet` | One-pass deterministic repair of common errors (stack height, rabbet alignment) |
| `describe_design` | Prose summary for design review before visualization |
| `design_door` | Door dimensions, hinge count, Z-positions for an opening |
| `design_drawer` | Drawer box dimensions, joinery cut specs, standard-height snapping |
| `design_legs` | Leg placement coordinates, load-per-leg check, hardware BOM |
| `generate_cutlist` | BOM as JSON (cut-optimizer-2d compatible) and CSV |
| `compare_joinery` | Side-by-side drawer joinery cut dimensions for a stock thickness |
| `visualize_cabinet` | 3D assembly → GLB + HTML viewer with x-ray (X) and open-drawer (O) toggles |

## Recommended workflow

```
list_presets → apply_preset → evaluate_cabinet
            ↓ (if errors)
        auto_fix_cabinet → evaluate_cabinet
            ↓
        describe_design → user review → visualize_cabinet
```

Tool descriptions encode this sequence — the LLM is instructed never to skip evaluation or visualize before the user has approved the described design.

## Configure with Claude Code

One-liner — registers at user scope so it's available in every session:

```bash
claude mcp add cabinet -- uv --directory /absolute/path/to/cabinet-mcp run cabinet-mcp
claude mcp list          # verify "cabinet" connected
claude mcp remove cabinet
```

Inside a Claude Code session, `/mcp` lists connected servers and their tools.

## Configure with Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "cabinet-mcp": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/cabinet-mcp", "run", "cabinet-mcp"]
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
      "cabinet-mcp": {
        "command": "uv",
        "args": ["--directory", "/absolute/path/to/cabinet-mcp", "run", "cabinet-mcp"]
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
      "cabinet-mcp": { "url": "http://127.0.0.1:3749/sse" }
    }
  }
}
```

## HTTP/SSE mode

The default starting port is **3749**; it auto-increments if occupied, so running multiple servers never collides.

```bash
cabinet-mcp --http                               # port 3749 (or next free)
cabinet-mcp --http --port 4200
cabinet-mcp --http --port 4200 --max-port-attempts 40
cabinet-mcp --http --host 0.0.0.0                # bind all interfaces
```

The chosen port is printed to stderr and written to `/tmp/cabinet-mcp.port`:

```bash
PORT=$(cat /tmp/cabinet-mcp.port)
curl "http://127.0.0.1:${PORT}/sse"
```
