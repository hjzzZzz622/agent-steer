# Codex 验收指南 / Codex Acceptance

本页记录一次可复现的 **真人/真模型** 验收：在同一 Codex turn 内注入纠偏，任务不重开。

This page documents a reproducible live acceptance: inject mid-run guidance into the same Codex turn without restarting.

## 前提 / Prerequisites

- macOS/Linux，Python 3.9+
- 已安装并登录 Codex CLI（`codex login` / ChatGPT）
- 本仓库可编辑安装：`python -m pip install -e .`
- 推荐模型：`gpt-5.5`（若本地 `models_cache` 对某模型缺字段，可能告警或表现不稳）

## 准备夹具 / Fixture

```bash
mkdir -p ~/agent-steer-codex-demo ~/agent-steer-codex-inbox
cp examples/claude_query.py ~/agent-steer-codex-demo/
# 假库：0907 空；0906 返回 revenue 120
```

## 终端 A：启动 owned turn

```bash
source .venv/bin/activate   # 或你的安装环境
export PATH="$HOME/.local/bin:$PATH"

agent-steer --db ~/agent-steer-codex-inbox/inbox.sqlite3 codex-run \
  --cwd ~/agent-steer-codex-demo \
  --model gpt-5.5 \
  --timeout 300 \
  --sandbox workspace-write \
  '请先运行 python3 claude_query.py 0907 --delay 50，查询日报数据；结果返回后再决定下一步。若收到运行中纠偏，请保留已完成步骤，说明采用了哪条纠偏，并查询新的日期。不要自行读取 inbox 数据库。'
```

stdout 会出现 JSONL；其中 `steering/session` 给出完整 `run_id`（形如 `codex:THREAD:TURN`）。

## 终端 B：中途提交纠偏

使用**同一** db 路径与 venv：

```bash
agent-steer --db ~/agent-steer-codex-inbox/inbox.sqlite3 sessions
agent-steer --db ~/agent-steer-codex-inbox/inbox.sqlite3 submit \
  --session 'codex:THREAD_ID:TURN_ID' \
  '0907 数据尚未落库，请改查 0906，保留已有任务进度。'
agent-steer --db ~/agent-steer-codex-inbox/inbox.sqlite3 messages \
  --session 'codex:THREAD_ID:TURN_ID'
```

## 过关标准 / Pass criteria

必须全部满足：

1. 出现 `steering/accepted`，且该消息 `emitted=true`
2. Codex **实际执行** `python3 claude_query.py 0906`（或等价），输出含 `revenue` / `120`
3. 仍在**同一** `run_id` / turn 内完成（未重新 `codex-run`）

通过后可人工确认并打收据：

```bash
agent-steer --db ~/agent-steer-codex-inbox/inbox.sqlite3 ack \
  --session RUN_ID MESSAGE_ID
```

## 不算成功 / Not success

- 仅口头说「收到了 / 会改查」
- 只有 `emitted=true` 而无 0906 工具结果
- 新开一轮 turn / 新会话才改查
- 自行读取 inbox SQLite 绕过纠偏通道

## 已验证记录 / Verified once

- 日期：2026-09-13
- Codex CLI：0.147.0
- 模型：`gpt-5.5`
- 结果：中断延迟中的 0907 查询后改查 0906，得到 `{"date":"0906","rows":[{"revenue":120}]}`，同 turn 结束

## 相关

- 适配器说明：`src/agent_steer/adapters/codex/README.md`
- 控制面契约草案：`docs/rfc-runtime-steering.md`
