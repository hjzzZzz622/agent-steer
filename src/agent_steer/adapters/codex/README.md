# Codex App Server adapter — v0.3.0

Creates an agent-steer-owned thread/turn over stdio, then polls the shared inbox
and calls `turn/steer` with `expectedTurnId`. It does not attach to existing desktop
or CLI sessions. Requires macOS/Linux, Python 3.9+, installed Codex and normal login.

## 安装与启动（终端 A）

From an updated checkout, install and check your CLI:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
codex --version
```

Run `codex login` if not already authenticated. Choose an available model and a
private absolute DB path. Start a task:

```bash
agent-steer --db /absolute/private/inbox.sqlite3 codex-run \
  --cwd /absolute/path/to/project --model YOUR_MODEL_ID --timeout 300 \
  '查询日报数据；根据后续纠偏调整查询，保留已有进度。'
```

Default sandbox is read-only. Add `--sandbox workspace-write` for tasks that need
project file changes. Approval policy is `never`: operations requiring elevation
fail rather than bypassing the sandbox. Unsupported interactive server requests
are rejected. Existing Codex configuration and managed policy still apply.
Diagnostics go to stderr; stdout is a JSON-lines event stream.

## 运行中提交（终端 B）

Use the same installed environment and DB path:

```bash
agent-steer --db /absolute/private/inbox.sqlite3 sessions
agent-steer --db /absolute/private/inbox.sqlite3 submit \
  --session 'codex:THREAD_ID:TURN_ID' '0907 数据尚未落库，请改查 0906。'
agent-steer --db /absolute/private/inbox.sqlite3 messages \
  --session 'codex:THREAD_ID:TURN_ID'
```

Copy the full run ID from `steering/session` or `sessions`. It contains both IDs
so stale guidance cannot silently enter another turn. One invocation owns one
turn. Once completed, new messages stay pending; they do not resume the turn.
Start another run and explicitly resubmit if needed. Sessions are historical
records, not liveness guarantees.

`steering/accepted` and `emitted=true` mean the server accepted input for this turn,
not that the model followed it. `status` remains pending until manual confirmation:

```bash
agent-steer --db /absolute/private/inbox.sqlite3 ack --session RUN_ID MESSAGE_ID
```

`retry --session RUN_ID MESSAGE_ID` resets emission for a still-active turn.
Timeout/disconnect can make acceptance uncertain; retry can duplicate guidance.
Rejected messages remain pending. No replacement turn starts automatically.
Timeout/interruption requests `turn/interrupt` before closing the owned server;
cancellation is best effort. This MVP has no resume or interactive approval UI.

## 测试与量化

Offline tests use real subprocess I/O with a deterministic fake App Server:

```bash
PYTHONPATH=src:. python -m unittest discover -s tests -v
```

Real Codex benchmark (six model trials per repeat):

```bash
PYTHONPATH=src:. python -m benchmarks.codex_run --live \
  --model YOUR_MODEL_ID --repeats 1 --timeout 120 \
  --output work/codex-benchmark-1
```

Start with one repeat; ten means 60 trials. Uses your model quota; there is no
enforced dollar/token cap. Timeout is a time limit, not a spending guarantee.
Date, region and source scenarios each have baseline/steered conditions. Output
includes JSONL trials, JSON/Markdown summaries, events, query traces, and token usage
when reported. Cost remains unknown. Benchmark enables workspace-write for its new
trial directory; fixtures are trusted instrumentation, not adversarial protection.

Codex guidance contains a fresh `--receipt` token that must appear in the corrected
fixture call. This proves the query used information from steering without relying
on response timing. This stricter condition differs from Claude's timestamp/marker
scoring; note it when comparing. Baseline never receives the revised target, so
revised-target rates are not an equal-information model comparison.
`receipt_wrong_selection_calls` and `receipt_calls_until_target` count only
receipt-bearing calls in the steered condition; they do not count untagged calls
as chronologically before or after acceptance. Baseline counts start after its
initial query. Raw traces retain every fixture call for separate analysis.

## 验证范围

Tests cover response correlation, RPC rejection, expected turn IDs, completion
races, timeout cancellation, durable emission and all six benchmark conditions.
These are protocol/harness tests, not real model performance results.

Local Codex 0.144.1 generated protocol schemas successfully; required steering
fields match this client. Actual server initialization was attempted but blocked
by the development sandbox's inability to write the user's Codex state directory.
No live Codex adoption rate is claimed.

Official reference: [Codex App Server](https://developers.openai.com/codex/app-server).
