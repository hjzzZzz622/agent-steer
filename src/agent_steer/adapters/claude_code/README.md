# Claude Code: MCP + Hooks

Status: design skeleton, not an installed or live integration.

Expose the queue contract through an MCP service; poll it from a PostToolUse hook and provide guidance as additional context. A hook runs in another process, so it must connect to a shared service or durable backend. Never instantiate this in-memory queue separately in each hook. Acknowledge host acceptance explicitly; emitting hook output alone does not prove the model followed it.

Use `agent_steer.adapters.base.apply_pending` at a host-owned safe boundary.
Host code is responsible for authentication, run ownership, permissions, and acknowledgements.

Official reference: [Claude Code: MCP + Hooks](https://code.claude.com/docs/en/hooks). Verify the host version before implementing.
