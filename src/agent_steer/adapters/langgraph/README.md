# LangGraph: middleware / checkpoint

Status: design skeleton, not an installed or live integration.

A future wrapper can call apply_pending between nodes and persist accepted guidance IDs alongside graph state. Interrupt/resume requires a checkpointer and stable thread_id; resumed nodes may execute again, so effects must be idempotent. The in-memory queue is not a LangGraph checkpointer. Middleware here describes an integration boundary, not a claimed native API.

Use `agent_steer.adapters.base.apply_pending` at a host-owned safe boundary.
Host code is responsible for authentication, run ownership, permissions, and acknowledgements.

Official reference: [LangGraph: middleware / checkpoint](https://docs.langchain.com/oss/python/langgraph/interrupts). Verify the host version before implementing.
