# agent-steer

A lightweight runtime steering layer for AI agents — inject guidance into running agents without restarting the task.

**Status: v0.1.0 alpha skeleton.** The dependency-free Python core and simulated
example work. Claude Code, Codex, and LangGraph directories reserve integration
boundaries; they are not installed plugins, MCP servers, or live SDK adapters yet.

## Why / 核心动机

Agents often discover incomplete data halfway through a task. A user may already
know the correction: “0907 数据尚未落库，请查询 0906”. Restarting loses useful
progress. agent-steer provides a small contract for receiving guidance and applying
it at the next host-controlled boundary while keeping the same run and state.

## Architecture

```text
User / future UI
       | submit(run_id, text)
       v
SteeringQueue Protocol <-- InMemorySteeringQueue (reference backend)
       | get_pending(run_id)
       v
Host-owned adapter / safe boundary
       | apply guidance to existing task state
       | ack(run_id, message_id) only after success
       v
Continue the same run
```

The core imports no agent framework. Hosts decide when to consume guidance and how
to interpret it. Guidance is input, not executable code or permission to bypass
host rules. A future remote service must authenticate submitters and enforce run
ownership; a run ID alone is not authorization.

## Quick start

Python 3.9+; no runtime dependencies or model keys.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python examples/date_correction.py
python -m unittest discover -s tests -v
```

Without installing, run from this checkout:

```bash
PYTHONPATH=src python examples/date_correction.py
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Minimal API

```python
from agent_steer import InMemorySteeringQueue

queue = InMemorySteeringQueue()
message = queue.submit('daily-report', '0907 数据尚未落库，请查询 0906')

# In the existing agent loop, after a tool result / before the next step:
for guidance in queue.get_pending('daily-report'):
    print(guidance.text)  # Replace with host logic that applies the correction.
    # Ack only once that host logic succeeds.
    queue.ack('daily-report', guidance.id)

assert queue.status('daily-report', message.id) == 'acknowledged'
```

For callbacks, `apply_pending(queue, run_id, apply)` from
`agent_steer.adapters.base` applies a snapshot in FIFO order and acknowledges each
successful callback. Exceptions propagate and leave failed/unvisited messages
pending. Its return value is the number acknowledged.

## Example: 0907 -> 0906

[Run the complete demo](examples/date_correction.py). It first queries an empty
0907 partition, receives user guidance, then queries 0906 without resetting its
`daily-report` run or previously completed planning step:

```text
run=daily-report: query 0907 -> []
steer: 0907 数据尚未落库，请查询 0906
run=daily-report: query 0906 -> [{'revenue': 120}]
preserved progress: ['plan', 'query']
```

This is a deterministic simulated tool loop. The date mapping is an explicit demo
policy; the core does not parse arbitrary language or contact a database/model.

## Protocol and delivery semantics

`Guidance` is immutable and serializable through `to_dict()` / `from_dict()`:

```json
{"version":"1","id":"message-id","run_id":"daily-report","text":"请查询 0906","created_at":"2026-09-07T00:00:00+00:00"}
```

- `submit(run_id, text) -> Guidance`: new ID on each call; no submission deduplication.
- `get_pending(run_id) -> tuple[Guidance, ...]`: non-destructive FIFO snapshot.
- `ack(run_id, message_id) -> None`: idempotent, scoped to a run.
- `status(run_id, message_id) -> 'pending' | 'acknowledged'`.
- Unknown message/run pairs raise `KeyError` for ack/status. Empty reads return `()`.
- Invalid envelopes raise `ValueError`; version 1 requires exactly the five fields.

Thread-safe producers; **one logical consumer per run**. Reading does not claim
messages. Delivery is at least once while this process lives, not exactly once:
a callback may succeed before ack fails. Consumers should deduplicate effects by
message ID. Acknowledgement means the host callback succeeded, not that an LLM
obeyed the guidance or completed the task. New guidance during application waits
until the next boundary; conflicting guidance is a host policy decision.

The reference backend is process-local, loses data on exit, and retains all
messages in memory. It is unsuitable for long-running or multi-process production
use. Durable retention, consumer leases, authentication, network transport,
cancellation, and priority are future scope.

## Adapter roadmap

| Adapter | Reserved integration | Current implementation |
| --- | --- | --- |
| [Claude Code](src/agent_steer/adapters/claude_code/README.md) | MCP + Hooks | Design namespace only |
| [Codex](src/agent_steer/adapters/codex/README.md) | MCP / App Server | Design namespace only |
| [LangGraph](src/agent_steer/adapters/langgraph/README.md) | Node middleware / checkpoint | Design namespace only |

Shared callback boundary helper is implemented and tested. Real integrations must
share a backend across processes and map host identities to run IDs explicitly.

## Repository layout

```text
src/agent_steer/
  core/             # versioned envelope, store protocol, reference queue
  adapters/
    base.py         # tested cooperative boundary helper
    claude_code/    # MCP + Hooks extension point
    codex/          # MCP / App Server extension point
    langgraph/      # middleware / checkpoint extension point
examples/           # runnable date-correction scenario
tests/              # unittest contract tests
docs/               # initial design and implementation checklist
pyproject.toml
LICENSE
```

## Development

Tests cover run isolation, FIFO/non-destructive reads, acknowledgement scope and
idempotence, wire validation, concurrent producers, failed application/retry, and
preserving task progress during correction. Changes to queue backends should
preserve this contract. Vendor integration tests will be added with each adapter.

Licensed under the [MIT License](LICENSE).
