# Claude Code MVP — 实际接入指南

v0.2.0 implements a local CLI + SQLite inbox + synchronous command hooks.
Supported target: macOS/Linux, Python 3.9+, Claude Code with `--settings`,
SessionStart, PostToolUse and PostToolUseFailure command hooks. No MCP server or
model API key is required by agent-steer; Claude Code uses your own login.

## 1. 安装（终端 A）

```bash
git clone https://github.com/hjzzZzz622/agent-steer.git
cd agent-steer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
agent-steer --help
```

Already cloned? Update your checkout before installing. Keep the virtual environment
at its installed path: the generated hook command embeds its absolute interpreter
path. Regenerate the settings file if you move or recreate that environment.

Choose a private, local directory outside the target repository for runtime files.
The following uses a fresh temporary directory; both terminals must use the SAME
absolute DB path printed here. Retain the directory to resume later; removing it
removes inbox history. Do not place the database in a shared/cloud-synced folder.

```bash
STEER_DIR=$(mktemp -d /tmp/agent-steer.XXXXXX)
agent-steer --db "$STEER_DIR/inbox.sqlite3" claude-settings --output "$STEER_DIR/hooks.json"
printf 'DB=%s\nSETTINGS=%s\n' "$STEER_DIR/inbox.sqlite3" "$STEER_DIR/hooks.json"
```

Now enter the project you want Claude to work on and start a NEW session:

```bash
cd /absolute/path/to/your/project
claude --settings "$STEER_DIR/hooks.json"
```

Accept ordinary project trust prompts as appropriate. Check `/hooks` to confirm
three hooks are loaded. The file is passed explicitly for this launch; agent-steer
does not edit `.claude/settings.json`, global configuration, or existing hooks.
A running session launched without these settings must be restarted once to load
this integration. Subsequent steering does not restart the task.

## 2. 选择会话并提交（终端 B）

Activate the SAME agent-steer virtual environment, then use the DB path from A:

```bash
source /absolute/path/to/agent-steer/.venv/bin/activate
STEER_DB=/tmp/agent-steer.REPLACE_WITH_ACTUAL/inbox.sqlite3
agent-steer --db "$STEER_DB" sessions
```

Output contains `session_id`, `cwd` and `last_seen`. Match the project directory and
copy the exact ID; multiple sessions are never guessed or broadcast to. Historical
sessions remain listed, so `last_seen` does not prove the session is still running.

While Claude is performing a tool call, submit the correction:

```bash
STEER_SESSION=REPLACE_WITH_SESSION_ID
agent-steer --db "$STEER_DB" submit --session "$STEER_SESSION" '0907 数据尚未落库，请查询 0906，保留已有任务进度。'
agent-steer --db "$STEER_DB" messages --session "$STEER_SESSION"
```

The next eligible tool boundary emits guidance into Claude's context. The CLI
returns a message ID. Unknown session IDs and empty or over-8000-character text
are rejected. At most eight messages are emitted per boundary, in FIFO order.

## 3. 验收场景：0907 → 0906

In a disposable test project, copy the repository's `examples/claude_query.py`.
Ask Claude:

> 请先运行 `python3 claude_query.py 0907 --delay 30`，查询日报数据；
> 结果返回后再决定下一步。若收到运行中纠偏，请保留已完成步骤，说明采用了
> 哪条纠偏，并查询新的日期。不要启动子 agent，也不要自行读取 inbox 数据库。

During the 30-second delay, send the correction from terminal B. The script is a
local fake database: 0907 returns an empty list, 0906 returns revenue 120. It does
not call a real database. Approve normal shell tool execution if Claude asks.

Pass criteria:

1. `messages` changes that message's `emitted` from false to true after the tool.
2. Claude mentions the date correction and runs the query for 0906.
3. Output contains revenue 120 and the same session continues without resetting.

Record `claude --version`, the message ID, `messages` output and relevant task
transcript when reporting a failure. Remove business data from shared diagnostics.

## 状态、重发与确认

`status=pending, emitted=false`: waiting for a tool boundary.
`status=pending, emitted=true`: hook stdout was flushed and recorded, **not proof
that Claude received, obeyed or completed the instruction**. After observing the
actual correction, optionally confirm it:

```bash
agent-steer --db "$STEER_DB" ack --session "$STEER_SESSION" MESSAGE_ID
```

If emission was recorded but no correction was observed, requeue explicitly:

```bash
agent-steer --db "$STEER_DB" retry --session "$STEER_SESSION" MESSAGE_ID
```

Retry can duplicate previously seen guidance; the context includes message IDs.
Acknowledged messages cannot be retried; submit a new message instead. `ack` is a
manual receipt and never automatically called on the model's behalf.

## 排障与边界

- No sessions: check `/hooks`, interpreter path and settings path. Run a tool to
  register the session if SessionStart was missed. Check Claude's hook errors.
- Still not emitted: verify the DB and session ID. Idle/model-only phases do not
  poll. A long-running tool must finish first; this is cooperative, not preemptive.
- Hook error: stderr describes invalid JSON, database lock or filesystem failures.
  Errors do not block the task intentionally; pending messages can be retried.
- A process dying between stdout and the transaction commit can duplicate output.
  A host failing after commit can miss output and requires manual retry.
- Hooks carrying `agent_id` are ignored to avoid consuming parent guidance in a
  subagent. MVP acceptance targets the main agent only; versions that omit that
  identity may not isolate delegated work, so avoid subagents for initial testing.
- This is a trusted single-user local inbox. It has no network listener, cross-user
  authorization, retention cleanup, cancellation, or guaranteed model compliance.
- To disable, close the session and launch Claude without this settings file.

## Verification status

Automated tests run real CLI subprocesses against the same SQLite file and execute
the generated shell command. They cover output schemas, retry, persistence,
isolation, concurrent hooks, write failure, and configuration preservation.
No live Claude model was run in the development environment (CLI unavailable).

Official contracts checked 2026-09-07:
[hooks](https://code.claude.com/docs/en/hooks),
[CLI --settings](https://code.claude.com/docs/en/cli-reference).
