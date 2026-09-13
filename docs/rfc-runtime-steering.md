# RFC: Runtime human↔agent steering primitives

**Status:** Draft  
**Applies to:** agent-steer core protocol (framework-agnostic)

## 1. Problem

Long-running agents often discover wrong assumptions mid-task (wrong date partition, wrong region, missing credential). Restarting the run discards useful progress. Hosts need a **small, shared contract** to inject human guidance at the next safe boundary while keeping the same run identity.

This is an **interaction-layer** problem, not another agent framework.

## 2. Goals

- Define minimal primitives for submitting, reading, and acknowledging guidance.
- Keep the core free of any agent SDK.
- Make delivery semantics explicit enough for adapters (Claude Code hooks, Codex App Server, LangGraph middleware, MCP, …) to interoperate.

## 3. Non-goals

- Not an agent runtime, planner, or tool executor.
- Guidance text is **input**, not executable code and not permission to bypass host policy.
- A `run_id` alone is **not** authorization for remote multi-user deployments.
- Exactly-once delivery across processes is not required in v1.
- Guaranteeing that a model *obeys* guidance is out of scope; hosts measure adoption separately.

## 4. Primitives

Immutable envelope `Guidance` (versioned wire fields): `version`, `id`, `run_id`, `text`, `created_at`.

Store protocol:

| Method | Behavior |
|--------|----------|
| `submit(run_id, text) -> Guidance` | Append; new id each call; no dedup |
| `get_pending(run_id) -> tuple` | Non-destructive FIFO snapshot |
| `ack(run_id, message_id)` | Idempotent; scoped to run |
| `status(run_id, message_id)` | `pending` \| `acknowledged` |

Optional host helper: apply a pending snapshot, then ack only after the host callback succeeds.

## 5. Delivery semantics

- **At least once** while the store is available: a successful apply may race a failed ack; consumers should dedupe effects by message `id`.
- One logical consumer per `run_id`.
- Reads do not claim messages; ack means **host application succeeded**, not that the model complied or the task finished.
- Conflicting guidance is a **host policy** decision.

## 6. Host boundary

Only the host decides when to consume pending guidance (tool boundary, graph node, turn poll, …). Adapters must not invent a second agent loop inside the core.

## 7. Security notes (remote)

Future networked services must authenticate submitters and enforce run ownership. Local single-user SQLite inboxes are trusted-operator only.

## 8. Open questions

- Should `ack` be split into `emitted` vs `applied` vs `obeyed` for metrics?
- Standard conflict policy (last-write-wins vs explicit supersede)?
- Cancellation / TTL for stale pending messages?

## 9. References

- Implementation: `src/agent_steer/core/`
- Codex live acceptance: `docs/codex-acceptance.md`
