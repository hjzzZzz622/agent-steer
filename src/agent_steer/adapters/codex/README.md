# Codex: MCP / App Server

Status: design skeleton, not an installed or live integration.

The MCP route is cooperative: instructions ask the agent to poll at safe boundaries. A future App Server client should map host thread/turn IDs to run IDs and use the documented steering interface while handling turn races and rejected requests. Lifecycle notifications alone do not inject guidance. No App Server client or automatic hook installation ships here.

Use `agent_steer.adapters.base.apply_pending` at a host-owned safe boundary.
Host code is responsible for authentication, run ownership, permissions, and acknowledgements.

Official reference: [Codex: MCP / App Server](https://developers.openai.com/codex/app-server). Verify the host version before implementing.
