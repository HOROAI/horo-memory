# Security policy

## Supported version

Security fixes currently target the latest commit on `main`.

## Deployment requirements

- Generate a unique, high-entropy `HORO_API_TOKEN` for each installation.
- Keep the HTTP listener on loopback and use Tailscale or a TLS reverse proxy.
- Restrict filesystem access to the service account and protect backups.
- Pin one `HORO_MCP_WORKSPACE` per agent process.
- Keep model-provider credentials outside the vault and event payloads.
- Review improvement proposals before approval; approval records a decision but does not silently edit production skills.

## Current trust model

HORO Memory 0.1 assumes one trusted administrator per installation. Workspaces isolate normal API and MCP access, but the administrator of the host can access every workspace and the underlying SQLite database. Use separate installations when host-level isolation between customers is required.

## Secrets

Do not put tokens, passwords, private keys, full cookies, or authentication headers into notes, event evidence, metrics, or payloads. The product does not currently perform automatic secret redaction at rest.

## Reporting a vulnerability

Do not open a public issue containing exploit details or customer data. Contact the maintainers privately with the affected version, reproduction steps, impact, and any proposed mitigation. A public security contact will be added before the first public release.
