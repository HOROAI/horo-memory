# HORO Memory

HORO Memory is a self-hosted operational memory and observable learning layer for AI agents. It records what an agent attempted, the evidence it produced, the result it obtained, and the improvements a human approved. The agent runtime remains replaceable: Hermes, Codex, Claude Code, OpenClaw, or another client can use the same memory through HTTP or MCP.

```text
agent -> run -> immutable events -> outcomes
                    |               |
                    v               v
             Markdown vault -> improvement proposal -> human decision
                    |
                    v
              Graphify index
```

The event ledger and approved decisions are the operational source of truth. The Markdown vault is the portable, human-readable surface that can be opened with Obsidian. Graphify is an optional rebuildable knowledge index. HORO Graph Studio combines all three in one visual brain.

## What works in the MVP

- Isolated workspaces, agents, runs, events, notes, and improvement proposals.
- Append-only events with hashes, provenance, evidence, metrics, and database guards.
- Obsidian-compatible Markdown vaults per workspace.
- Optional Graphify extraction and graph import.
- HTTP API and an MCP server for agent runtimes.
- Visual execution, knowledge, and evolution views.
- Human approval or rejection before any proposed improvement is promoted.
- Docker deployment that listens on localhost by default.

## Quick start with Docker

Requirements: Docker Engine with Compose v2.

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Put the generated value in HORO_API_TOKEN inside .env.
docker compose up -d --build
docker compose exec horo-memory horo-memory demo
```

Open `http://127.0.0.1:8088`, enter the API token, and choose the `HORO Demo` workspace. The browser keeps the token in session storage and removes it when the browser session ends.

The default port binding is local-only. On a VPS, reach it through Tailscale or place a TLS reverse proxy in front of it. Do not publish the raw HTTP port to the internet.

### VPS without Docker

The repository includes a hardened systemd installer for a private Linux VPS:

```bash
git clone https://github.com/HOROAI/horo-memory.git
cd horo-memory
chmod +x deploy/install-vps.sh
./deploy/install-vps.sh
```

It generates the token in `/etc/horo-memory.env`, stores data in `/var/lib/horo-memory`, runs under the current non-root user, and binds only to `127.0.0.1:8088`. Connect from another computer with an SSH tunnel:

```bash
ssh -L 8088:127.0.0.1:8088 user@your-vps
```

## Local development

```bash
uv sync --extra dev --extra graphify
$env:HORO_API_TOKEN="replace-with-a-long-random-token"
$env:HORO_DATA_DIR="./data-dev"
uv run horo-memory demo
uv run horo-memory serve
```

Useful checks:

```bash
uv run ruff check .
uv run pytest -q
docker compose config
```

## Agent connection through MCP

Configure the process in an MCP-compatible client. Each process is pinned to one workspace, which prevents an agent from accidentally reading another company's context.

```json
{
  "mcpServers": {
    "horo-memory": {
      "command": "horo-memory-mcp",
      "env": {
        "HORO_DATA_DIR": "/srv/horo-memory/data",
        "HORO_MCP_WORKSPACE": "client-acme"
      }
    }
  }
}
```

Available tools:

- `horo_context_search`
- `horo_note_write`
- `horo_run_start`
- `horo_action_record`
- `horo_outcome_record`
- `horo_run_complete`
- `horo_improvement_propose`
- `horo_graph_snapshot`

The local MCP process accesses the same data directory directly. The HTTP API uses bearer authentication for browsers and remote adapters.

## Graphify and Obsidian

Each workspace creates a vault under `data/vault/<workspace-id>`. Open that directory as an Obsidian vault or synchronize it using the operator's preferred method.

When Graphify is enabled, **Reindex knowledge** runs the equivalent of:

```bash
graphify extract data/vault/<workspace-id> --out data/graphify-out/<workspace-id>
```

Semantic extraction may require a Graphify-supported model provider. Graphify output is stored separately and can always be rebuilt from the vault; deleting its index does not delete HORO's event history.

## API example

```bash
curl -H "Authorization: Bearer $HORO_API_TOKEN" \
  http://127.0.0.1:8088/api/v1/workspaces
```

Interactive API documentation is available at `/docs` after startup.

## Data and backups

All persistent state lives below `HORO_DATA_DIR`:

```text
data/
  horo-memory.sqlite3   # event ledger and operational state
  vault/                # portable Markdown, one directory per workspace
  graphify-out/         # rebuildable derived indexes
```

Back up the whole directory. For a consistent SQLite snapshot, stop the container briefly or use SQLite's online backup command before copying it.

## Security boundary

This first release is designed for one trusted operator and multiple isolated workspaces on a private VPS. It includes bearer authentication, strict identifiers and paths, request size limits, security headers, immutable event triggers, no shell execution for Graphify, and a least-privilege container.

It does not yet provide enterprise identity, per-user roles, encrypted application data, audit signing, rate limiting, or a multi-node database. See [SECURITY.md](SECURITY.md) before exposing it outside a private network.

## Project boundaries

HORO Memory stores and explains operational learning. Agent runtimes execute tasks. Skills describe capabilities. Obsidian displays and edits portable knowledge. Graphify derives relationships from that knowledge. This separation prevents the product from depending on one agent or one graph engine.

The next product milestone is evaluation: compare workflow and skill versions under equivalent criteria, then promote or roll back an approved version without rewriting history.

## License

Apache License 2.0. See [LICENSE](LICENSE).
