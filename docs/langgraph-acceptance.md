# LangGraph 验收指南 / LangGraph Acceptance

本页记录一次可复现的 **LangGraph L2 + 真模型** 验收：图执行中途注入纠偏，同一
`thread_id` 内改查日期并调用 OpenRouter 免费路由。

This page documents a reproducible live acceptance: mid-run steering in a LangGraph
run with a real OpenRouter model, without restarting the graph.

## 前提 / Prerequisites

- macOS/Linux，Python 3.9+
- 本仓库可编辑安装：`python -m pip install -e .`
- **可选**依赖（仅 live 示例需要，不在 `pyproject.toml` 中）：

  ```bash
  python -m pip install langgraph langchain-core openai
  ```

- 环境变量 `OPENROUTER_API_KEY`（[OpenRouter](https://openrouter.ai/) 密钥；示例不会打印密钥）
- 示例使用临时目录存放 SQLite 队列，无需手动准备夹具

## 运行 live 示例 / Run the live example

```bash
source .venv/bin/activate   # 或你的安装环境
export OPENROUTER_API_KEY='sk-or-...'   # 勿提交到 git

PYTHONPATH=src:. python examples/langgraph_openrouter_live.py \
  2>&1 | tee work/langgraph_openrouter_live.log
```

图结构：`plan → query → call_model`。在 `plan` 节点完成后、后续节点执行前，示例向
共享 SQLite 队列提交纠偏；`query` 边界应用后改查 0906；`call_model` 通过 OpenRouter
`openrouter/free` 路由确认查询日期。

可选：将 stdout 重定向到 `work/langgraph_openrouter_live.log`（已在 `.gitignore`）。

## 过关标准 / Pass criteria

必须全部满足：

1. 中途提交纠偏后 `steered=true`，最终 `date=0906`
2. 夹具查询 `0906` 返回 `revenue=120`（0907 为 0）
3. OpenRouter 返回非空 `model_id`（免费路由可能 flake；示例最多重试 3 次）
4. 仍在**同一** `thread_id` / 图流内完成（未重新编译或新开图）

stdout 应出现：

```text
PASS steer: 0907 -> 0906 applied mid-run
PASS query: date=0906 revenue=120
PASS live: OpenRouter response model_id=...
PASS overall: LangGraph L2 live steer + OpenRouter
```

## 不算成功 / Not success

- 仅口头/日志说会改查，但 `date` 仍为 0907 或 `revenue` 不是 120
- 纠偏已 ack 但查询仍用 0907 夹具
- 新开一轮图 / 新 `thread_id` 才改查
- OpenRouter 401/402/429 等致命 HTTP（示例以 exit 2 结束）
- 日志或 stdout 泄露 `OPENROUTER_API_KEY`、`Authorization: Bearer` 或 `sk-or-` 前缀

## 已验证记录 / Verified once

- 日期：2026-09-13
- OpenRouter 路由模型：`openrouter/free`
- 实际路由到的模型：`inclusionai/ling-3.0-flash-sante:free`
- 场景：初始 `date=0907`；`plan` 后中途提交「0907 数据尚未落库，请查询 0906 / 改查 0906」；
  `query` 改查 0906 得 `revenue=120`；LLM 返回解析日期 `0906`
- 备注：免费路由偶发空 content；示例对空回复退避重试最多 3 次

## 离线测试 / Offline tests

无需 OpenRouter 或 LangGraph 安装：

```bash
PYTHONPATH=src:. python -m unittest discover -s tests -p 'test_*.py' -v
```

LangGraph 适配器契约见 `tests/test_langgraph.py`（不调用真模型）。

## 相关

- 适配器说明：`src/agent_steer/adapters/langgraph/README.md`
- 控制面契约草案：`docs/rfc-runtime-steering.md`
- 离线日期纠偏示例：`examples/date_correction.py`
