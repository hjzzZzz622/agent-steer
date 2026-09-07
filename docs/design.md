# Initial design

The framework-independent core owns immutable versioned guidance envelopes and a
thread-safe in-memory queue. Each run has one logical consumer. Reading is
non-destructive; acknowledgement happens only after successful application.
Delivery is at least once, so consumers must apply messages idempotently by ID.
The core never executes guidance or overrides host permissions.

A Python Protocol defines submit/get_pending/ack/status, allowing durable stores
and transports later without coupling the core to an agent SDK. Adapter modules
reserve Claude Code MCP + Hooks, Codex MCP/App Server, and LangGraph node-boundary
middleware/checkpoint integrations. This release ships a callback boundary helper,
not working vendor transports. No cross-process guarantees are claimed.

Alternative: building three SDK integrations immediately would obscure the core
contract. A standalone HTTP server would add authentication and persistence scope.
Both are deferred in favor of an executable, dependency-free core skeleton.
