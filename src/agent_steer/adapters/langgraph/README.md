# LangGraph adapter — v0.4.0

This adapter implements the runtime-steering boundary without making LangGraph a
hard dependency. Call the middleware at the start of a node/task and use the
LangGraph checkpoint `thread_id` as `run_id`. The SQLite queue survives an
`interrupt()` and resume in another process.

## Installation

```bash
python -m pip install agent-steer
python -m pip install langgraph
```

## Minimal integration

```python
from agent_steer import InMemorySteeringQueue
from agent_steer.adapters.langgraph import SteeringMiddleware

queue = InMemorySteeringQueue()  # use SQLiteSteeringQueue across processes

def apply_guidance(message, state):
    if '0906' in message.text:
        return {'date': '0906'}
    if 'ip_gpu_count' in message.text:
        return {'numerator': 'ip_gpu_count'}
    return {}

steering = SteeringMiddleware(queue, apply_guidance)

def query_node(state, config):
    thread_id = config['configurable']['thread_id']
    steering.before_node(thread_id, 'query', state)
    return {'rows': query(state['date'])}
```

`before_node` reads a FIFO snapshot, calls your state update callback, and only then
acknowledges the message. If the callback or checkpoint write fails, it remains
pending for the next boundary. A dict returned by the callback updates the supplied
state. `wrap_node` runs the boundary and node together and returns applied message
IDs for audit metadata.

The adapter does not call `interrupt()` itself. LangGraph interruption is an
explicit approval point; steering is cooperative input before the next node. Keep
side effects before an interrupt idempotent because resumed nodes may restart from
their beginning.

## Screenshot-style correction

```python
queue.submit(
    'inventory-report-0907',
    '上期低负载卡数使用 0814 快照；mTKE 分子使用 ip_gpu_count。保留已完成的 CSV 读取，只重算受影响指标。',
)
```

The next `calculate` boundary can update `snapshot` and `numerator` while preserving
`loaded_rows` and `completed_steps`. Verify the next query uses those values.

## Live acceptance

Mid-run steer with a real OpenRouter model (optional deps, requires
`OPENROUTER_API_KEY`):

- Guide: [LangGraph live acceptance](../../../docs/langgraph-acceptance.md)
- Runnable example:

  ```bash
  export OPENROUTER_API_KEY='sk-or-...'
  python -m pip install langgraph langchain-core openai
  PYTHONPATH=src:. python examples/langgraph_openrouter_live.py
  ```

The example uses a temp SQLite queue, submits guidance after `plan`, queries fixture
0906, and calls OpenRouter `openrouter/free`. See the acceptance doc for pass
criteria and a verified-once record.

## Testing

```bash
PYTHONPATH=src:. python -m unittest discover -s tests -p 'test_langgraph.py' -v
```

Tests cover state updates, failure/retry, SQLite persistence across an interrupt/
resume boundary, FIFO behavior and thread isolation. They do not claim model
behavior because LangGraph is intentionally not imported. Add an application test
with a checkpointer that asserts state and tool arguments after resume.

This adapter cannot interrupt a long-running node or force an LLM to follow text.
Add boundaries around expensive nodes and validate critical state transitions in
deterministic application code.

Official references: [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
and [persistence](https://docs.langchain.com/oss/python/langgraph/persistence).
