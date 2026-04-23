# Local setup and debugging

This guide covers installing cabinet-mcp on macOS, registering it with your AI client, and diagnosing the most common connection problems.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| macOS 12 Monterey or later | Intel and Apple Silicon both work |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | The only hard dependency you need to install manually |
| ~2 GB free disk | For the full install with CadQuery; lite mode needs < 100 MB |

Install uv if you don't have it:

```bash
brew install uv
# or without Homebrew:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

uv manages Python automatically — you do not need a separate Python install.

---

## Install

Clone the repo and install in one step:

```bash
git clone https://github.com/your-org/cabinet-mcp.git
cd cabinet-mcp
uv sync          # full install: CadQuery + rectpack + dev tools
```

Smoke-test the install:

```bash
uv run cabinet-mcp --help
```

You should see the argparse help block listing `--http`, `--port`, `--host`, and `--max-port-attempts`. If that works, the server binary and all dependencies are present.

> **Lite mode** — if you hit CadQuery build errors (see [CadQuery won't install](#cadquery-wont-install) below), you can run without it. Parametric design, evaluation, cutlist BOM, and the full MCP server all work; 3D geometry and the HTML viewer are disabled.
>
> ```bash
> uv run --no-group full cabinet-mcp --help
> ```

---

## Launch modes

### stdio — Claude Code or Claude Desktop (recommended)

stdio is the default transport. The AI client launches `cabinet-mcp` as a child process and communicates over stdin/stdout. No port is involved, so there are no port conflicts and no firewall rules to worry about.

**Claude Code** — register once at user scope so it's available in every project:

```bash
claude mcp add cabinet -- uv --directory /absolute/path/to/cabinet-mcp run cabinet-mcp
```

Verify it registered:

```bash
claude mcp list
# cabinet: uv --directory /…/cabinet-mcp run cabinet-mcp
```

Inside any Claude Code session, `/mcp` lists connected servers and confirms the seventeen cabinet tools are visible.

**Claude Desktop** — edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Replace `/absolute/path/to/cabinet-mcp` with the real path (no `~` shorthand — Claude Desktop does not expand tildes). Restart Claude Desktop after saving. The hammer icon in the toolbar should show the cabinet tools.

### HTTP/SSE — persistent server or multi-client

Run a long-lived server when you want to keep the process running and connect to it from Gemini CLI, a browser client, or multiple sessions at once.

```bash
# Default port 3749, auto-increments if occupied
uv run cabinet-mcp --http

# Specific port
uv run cabinet-mcp --http --port 4200

# Bind all interfaces (e.g. for access from another machine on your LAN)
uv run cabinet-mcp --http --host 0.0.0.0 --port 4200
```

The resolved port is printed to stderr and written to `/tmp/cabinet-mcp.port`:

```bash
# Read the port without parsing log output
PORT=$(cat /tmp/cabinet-mcp.port)
echo "Server is on port $PORT"
```

Confirm the SSE endpoint is reachable:

```bash
curl -N "http://127.0.0.1:${PORT}/sse"
# You should see the SSE stream open (event: endpoint …)
# Press Ctrl-C to close
```

Configure Gemini CLI (`~/.gemini/settings.json`):

```json
{
  "mcp": {
    "servers": {
      "cabinet-mcp": { "url": "http://127.0.0.1:3749/sse" }
    }
  }
}
```

---

## Debugging connection problems

### "command not found: cabinet-mcp"

The `cabinet-mcp` script only exists inside the uv environment. Always launch via `uv run`:

```bash
# Wrong — only works after a global pip install, which is not recommended
cabinet-mcp --http

# Right
uv run cabinet-mcp --http

# Or activate the environment first
source .venv/bin/activate
cabinet-mcp --http
```

When registering with Claude Code, the `uv --directory … run cabinet-mcp` form handles this automatically.

### Claude Desktop: tools not appearing

Claude Desktop launches MCP servers using the PATH it inherits from launchd, which is **not** the same as your interactive terminal PATH. `uv` installed via Homebrew at `/opt/homebrew/bin/uv` may be invisible to GUI apps.

Fix: use the full absolute path to the `uv` binary in your config:

```bash
which uv   # e.g. /opt/homebrew/bin/uv
```

```json
{
  "mcpServers": {
    "cabinet-mcp": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["--directory", "/Users/yourname/cabinet-mcp", "run", "cabinet-mcp"]
    }
  }
}
```

Also double-check:
- The path in `args` is absolute and the directory exists.
- You fully quit and relaunched Claude Desktop after editing the config (Cmd-Q, not just closing the window).
- There are no JSON syntax errors in the config file — a trailing comma or missing brace silently breaks the whole file.

Validate your JSON before saving:

```bash
python3 -m json.tool ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

### Claude Desktop: reading the MCP logs

Claude Desktop writes MCP server output to log files:

```
~/Library/Logs/Claude/mcp-server-cabinet-mcp.log   # server stdout/stderr
~/Library/Logs/Claude/mcp.log                       # MCP host-side messages
```

Tail them while restarting Claude Desktop to see exactly what's failing:

```bash
tail -f ~/Library/Logs/Claude/mcp-server-cabinet-mcp.log
tail -f ~/Library/Logs/Claude/mcp.log
```

### Port conflict in HTTP mode

If port 3749 is already in use, the server auto-increments through up to 20 ports by default. If all are occupied it exits. Widen the search or pick a different starting port:

```bash
uv run cabinet-mcp --http --port 5000 --max-port-attempts 40
```

Find what's holding a port:

```bash
lsof -i :3749
```

Check whether a previous server is still running:

```bash
cat /tmp/cabinet-mcp.port    # shows the port of the last server that wrote this file
```

### "No module named 'cadquery_furniture'" after a fresh sync

If the package itself isn't importable even after `uv sync`, the venv's editable install is in a bad state (this can happen when uv or pip leaves behind stale dist-info). The reliable fix is a clean rebuild:

```bash
rm -rf .venv
uv sync
uv run cabinet-mcp --help
```

If the error persists after a clean venv, confirm that `src/cadquery_furniture/` exists and that `uv sync` completed without errors before trying anything else.

### CadQuery won't install

CadQuery has a large native dependency tree (OCCT). If the build fails or takes too long, switch to lite mode — everything except 3D geometry works:

```bash
# Install without CadQuery
uv sync --no-group full

# Launch in lite mode
uv run --no-group full cabinet-mcp
```

The server will start and all seventeen tools are available; `visualize_cabinet` returns a "CadQuery not installed" error instead of geometry, and `evaluate_cabinet` skips interference checks.

### Smoke-testing the stdio protocol manually

You can drive the server directly without a client to confirm basic health:

```bash
# Send an MCP initialize request and read the response
echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0"}},"id":1}' \
  | uv run cabinet-mcp
```

A healthy server returns a JSON object with `serverInfo` and a `capabilities` block. Any Python traceback here means a dependency or import problem — check the output for the specific error.

### Stale port file

If the server crashed without cleaning up, `/tmp/cabinet-mcp.port` may contain a stale port number that confuses scripts reading it:

```bash
rm -f /tmp/cabinet-mcp.port
```

### Apple Silicon / Rosetta

CadQuery's OCCT binaries are native ARM64 on Apple Silicon — do not run `uv` under Rosetta (x86_64 emulation). Check which architecture your terminal is using:

```bash
arch   # should print "arm64" on Apple Silicon, not "i386"
```

If it prints `i386`, open a new terminal that is not running under Rosetta, or run `arch -arm64 zsh` to get a native shell.

---

## Quick-reference

```bash
# Install
uv sync

# Smoke test
uv run cabinet-mcp --help

# Register with Claude Code
claude mcp add cabinet -- uv --directory $(pwd) run cabinet-mcp
claude mcp list

# HTTP server
uv run cabinet-mcp --http
PORT=$(cat /tmp/cabinet-mcp.port) && curl -N "http://127.0.0.1:${PORT}/sse"

# Lite mode (no CadQuery)
uv run --no-group full cabinet-mcp

# Manual stdio test
echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0"}},"id":1}' \
  | uv run cabinet-mcp

# Claude Desktop logs
tail -f ~/Library/Logs/Claude/mcp-server-cabinet-mcp.log
tail -f ~/Library/Logs/Claude/mcp.log
```
