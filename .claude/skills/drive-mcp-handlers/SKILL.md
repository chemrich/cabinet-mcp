---
name: drive-mcp-handlers
description: Call cabinet-mcp tool handlers directly from Python without the MCP transport or a live server. Use to exercise or debug a tool (design_cabinet, evaluate_cabinet, generate_cutlist, visualize_cabinet, auto_fix_cabinet, etc.), reproduce an eval scenario, or check behavior when the session's `cabinet` MCP server is stale (predates recent merges until a `/mcp` reconnect). This is the same path the eval harness uses.
---

# Driving tool handlers directly

Every MCP tool is a plain async handler named `_tool_<name>` in `src/cadquery_furniture/server.py` that takes an `args` dict and returns `list[types.TextContent]` whose `[0].text` is a JSON string. You can call these without any MCP client — this bypasses the transport entirely and always runs the **current on-disk code**, even when the session's registered `cabinet` server process is stale.

## Pattern

```python
import asyncio, json
from cadquery_furniture import server as srv

res = asyncio.run(srv._tool_evaluate_cabinet({"width": 600, "height": 720, "depth": 550}))
print(json.loads(res[0].text)["summary"])   # {'errors': 0, 'warnings': 0, 'info': 0, 'pass': True}
```

Run it with `uv run python - <<'EOF' ... EOF` (or `uv run python -c "..."`).

## Handler names

The tool name usually maps to `_tool_<name>` — e.g. `design_cabinet` → `_tool_design_cabinet`, `generate_cutlist` → `_tool_generate_cutlist`, `visualize_project` → `_tool_visualize_project`. **There are exceptions** (e.g. `list_joinery_options` → `_tool_list_joinery`), so the eval harness's `TOOL_DISPATCH` (in `evals/harness.py`) is the **canonical** name→handler map — check it rather than assuming the pattern.

## Args

The `args` dict mirrors the tool's `inputSchema` in `server.py`. Cabinet geometry uses `drawer_config` as a list of `[height_mm, opening_type]` pairs (e.g. `[[300, "drawer"], [192, "drawer"]]`); `opening_type` is one of `drawer | door | door_pair | shelf | open`. All units are millimetres.

## Why this matters here

- **Stale server:** the session's `cabinet` server only picks up merged code after a `/mcp` reconnect. Direct-drive sidesteps that — use it to verify a fix landed before reconnecting.
- **Reproducing evals:** copy a scenario's `args` from `evals/scenarios.py` and drive the handler to see the full JSON result an assertion walked (evals only surface the failing path).
- **File-writing tools** write under `~/.cabinet-mcp/`. The `visualize_*` tools accept an explicit `output_dir` — point it at a scratch path when probing. `generate_cutlist`/`generate_project_cutlist` have **no `output_dir`** (they always write to `~/.cabinet-mcp/cutlists/`, and passing `output_dir` raises `ValueError: Unknown cabinet parameter(s)`); use a throwaway `name` if you want to avoid clobbering. Output `name` is validated as a filename stem (no `..`/separators) — a traversal name raises.
