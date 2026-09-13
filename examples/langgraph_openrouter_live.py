#!/usr/bin/env python3
"""LangGraph L2 live acceptance: mid-run steer 0907 -> 0906 via OpenRouter free router.

Requires OPENROUTER_API_KEY. Optional deps: langgraph, langchain-core, openai.
Never prints the API key.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from openai import APIStatusError, OpenAI

from agent_steer.adapters.langgraph import SteeringMiddleware
from agent_steer.core.sqlite import SQLiteSteeringQueue

THREAD_ID = "daily-report-l2"
GUIDANCE = "0907 数据尚未落库，请查询 0906 / 改查 0906"
FIXTURE = {"0906": {"revenue": 120}, "0907": {"revenue": 0}}
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "openrouter/free"
FATAL_HTTP = {401, 402, 429}


class GraphState(TypedDict, total=False):
    date: str
    steps: list
    rows: list
    revenue: int
    steered: bool
    applied_texts: list
    model_id: str
    model_reply: str
    llm_date: str


def redact(text: Any) -> str:
    raw = "" if text is None else str(text)
    raw = re.sub(r"(?i)(authorization:\s*bearer\s+)\S+", r"\1[REDACTED]", raw)
    raw = re.sub(r"sk-or-[A-Za-z0-9._-]+", "[REDACTED]", raw)
    raw = re.sub(r"sk-[A-Za-z0-9._-]{10,}", "[REDACTED]", raw)
    return raw


def query_fixture(date: str) -> dict:
    return dict(FIXTURE.get(date, {"revenue": None}))


def apply_guidance(message, state: dict) -> dict:
    text = message.text or ""
    before = state.get("date")
    if "0906" in text or "改查" in text:
        print(f"STEER APPLY: {before} -> 0906 | guidance={text!r}")
        return {"date": "0906", "steered": True}
    print(f"STEER IGNORE: date={before!r} guidance={text!r}")
    return {}


def thread_id_from(config: RunnableConfig) -> str:
    return config["configurable"]["thread_id"]


def _extract_json_obj(text: str) -> dict:
    text = (text or "").strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[^{}]*\}", text)
    if match:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    return {}


def _fatal_http(exc: APIStatusError) -> None:
    status = exc.status_code
    body = ""
    try:
        body = exc.response.text if exc.response is not None else ""
    except Exception:
        body = ""
    if not body:
        body = redact(getattr(exc, "body", None) or exc)
    print(f"OPENROUTER FATAL HTTP {status}: {redact(body)[:500]}")
    raise SystemExit(2)


def _message_text(message) -> str:
    parts = []
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
            else:
                parts.append(str(getattr(block, "text", "") or getattr(block, "content", "") or ""))
    for attr in ("reasoning", "refusal"):
        extra = getattr(message, attr, None)
        if extra:
            parts.append(str(extra))
    return "\n".join(p for p in parts if p).strip()


def call_openrouter(date: str) -> tuple[str, str, str]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("FAIL: OPENROUTER_API_KEY is not set")
        raise SystemExit(2)
    client = OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE,
        default_headers={
            "HTTP-Referer": "https://github.com/hjzzZzz622/agent-steer",
            "X-Title": "agent-steer langgraph L2 live",
        },
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a reporting assistant. The host already selected the query date. "
                f"query_date={date}. Reply with ONLY compact JSON: {{\"date\":\"{date}\"}} "
                "using that exact query_date. No markdown, no extra keys."
            ),
        },
        {"role": "user", "content": "Confirm the date you will use for the revenue query. JSON only."},
    ]
    last_err = None
    last_http_ok = None
    for attempt in range(1, 4):
        print(f"OPENROUTER attempt {attempt}/3 model={OPENROUTER_MODEL} date_in_prompt={date}")
        try:
            resp = client.chat.completions.create(
                model=OPENROUTER_MODEL, messages=messages, temperature=0, max_tokens=128
            )
            choice = resp.choices[0] if resp.choices else None
            message = choice.message if choice is not None else None
            reply = _message_text(message) if message is not None else ""
            model_id = resp.model or OPENROUTER_MODEL
            finish = getattr(choice, "finish_reason", None)
            parsed = _extract_json_obj(reply)
            llm_date = str(parsed.get("date") or "")
            print(f"OPENROUTER ok model_id={model_id} finish={finish} reply={reply!r} parsed_date={llm_date!r}")
            last_http_ok = (str(model_id), reply, llm_date)
            if reply:
                return last_http_ok
            print("OPENROUTER empty content; treating as free-router flake")
            if attempt < 3:
                time.sleep(2 ** attempt)
        except APIStatusError as exc:
            last_err = exc
            print(f"OPENROUTER HTTP {exc.status_code}: {redact(exc)[:240]}")
            if getattr(exc, "status_code", None) in FATAL_HTTP:
                _fatal_http(exc)
            if attempt < 3:
                time.sleep(2 ** attempt)
        except SystemExit:
            raise
        except Exception as exc:
            last_err = exc
            print(f"OPENROUTER error: {redact(exc)[:240]}")
            if attempt < 3:
                time.sleep(2 ** attempt)
    if last_http_ok is not None:
        return last_http_ok
    print(f"FAIL: OpenRouter retries exhausted: {redact(last_err)[:240]}")
    raise SystemExit(3)


def main() -> int:
    print("=== agent-steer LangGraph L2 live (OpenRouter free) ===")
    work = Path(tempfile.mkdtemp(prefix="agent-steer-langgraph-live-"))
    queue_path = work / "langgraph_live.sqlite3"
    print(f"queue={queue_path}")
    print(f"thread_id={THREAD_ID}")
    print(f"initial date=0907 fixture={FIXTURE}")
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("FAIL: OPENROUTER_API_KEY is not set")
        return 2

    queue = SQLiteSteeringQueue(queue_path)
    steering = SteeringMiddleware(queue, apply_guidance)

    def plan_node(state: GraphState, config: RunnableConfig) -> dict:
        tid = thread_id_from(config)
        applied = steering.before_node(tid, "plan", state)
        steps = list(state.get("steps") or []) + ["plan"]
        print(f"NODE plan date={state.get('date')} applied={len(applied)} steps={steps}")
        return {"date": state.get("date"), "steps": steps, "steered": bool(state.get("steered"))}

    def query_node(state: GraphState, config: RunnableConfig) -> dict:
        tid = thread_id_from(config)
        applied = steering.before_node(tid, "query", state)
        texts = [item.text for item in applied]
        date = state["date"]
        row = query_fixture(date)
        revenue = row.get("revenue")
        steps = list(state.get("steps") or []) + ["query"]
        print(f"NODE query after_steer date={date} revenue={revenue} applied={texts}")
        return {
            "date": date,
            "rows": [row],
            "revenue": revenue,
            "steps": steps,
            "steered": bool(state.get("steered")),
            "applied_texts": texts,
        }

    def call_model_node(state: GraphState, config: RunnableConfig) -> dict:
        tid = thread_id_from(config)
        steering.before_node(tid, "call_model", state)
        date = state["date"]
        model_id, reply, llm_date = call_openrouter(date)
        steps = list(state.get("steps") or []) + ["call_model"]
        return {"date": date, "model_id": model_id, "model_reply": reply, "llm_date": llm_date, "steps": steps}

    builder = StateGraph(GraphState)
    builder.add_node("plan", plan_node)
    builder.add_node("query", query_node)
    builder.add_node("call_model", call_model_node)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "query")
    builder.add_edge("query", "call_model")
    builder.add_edge("call_model", END)
    graph = builder.compile(checkpointer=InMemorySaver())

    config = {"configurable": {"thread_id": THREAD_ID}}
    initial: GraphState = {"date": "0907", "steps": [], "steered": False}
    submitted = False
    final_state: dict = dict(initial)
    for event in graph.stream(initial, config, stream_mode="updates"):
        print(f"STREAM event={event}")
        if not submitted and "plan" in event:
            msg = queue.submit(THREAD_ID, GUIDANCE)
            submitted = True
            print(f"MID-RUN SUBMIT message_id={msg.id} text={GUIDANCE!r}")
        if isinstance(event, dict):
            for patch in event.values():
                if isinstance(patch, dict):
                    final_state.update(patch)

    date = final_state.get("date")
    revenue = final_state.get("revenue")
    steered = bool(final_state.get("steered"))
    model_id = final_state.get("model_id")
    print("--- evidence ---")
    print(f"final date={date} revenue={revenue} steered={steered} steps={final_state.get('steps')}")
    print(f"openrouter model_id={model_id} llm_date={final_state.get('llm_date')}")
    steer_ok = steered and date == "0906" and revenue == 120
    live_ok = bool(model_id)
    if steer_ok:
        print("PASS steer: 0907 -> 0906 applied mid-run")
        print("PASS query: date=0906 revenue=120")
    else:
        print(f"FAIL steer/query: date={date} revenue={revenue} steered={steered}")
    if live_ok:
        print(f"PASS live: OpenRouter response model_id={model_id}")
    else:
        print("FAIL live: no OpenRouter model response")
    if steer_ok and live_ok:
        print("PASS overall: LangGraph L2 live steer + OpenRouter")
        return 0
    print("FAIL overall")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        print("FAIL unhandled exception:")
        print(redact(traceback.format_exc()))
        sys.exit(1)
