"""LangGraph-friendly steering boundary without a hard LangGraph dependency.

Call ``before_node`` at the start of each node (or task) and pass the same
checkpoint thread id as ``run_id``. The callback owns state updates; messages are
acknowledged only after it returns. This works with LangGraph ``interrupt``
resume because the queue is external and durable while graph state is checkpointed.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from ...core import Guidance, SteeringQueue


@dataclass(frozen=True)
class AppliedGuidance:
    message_id: str
    text: str
    node: str


class SteeringMiddleware:
    """Apply pending guidance once at an explicit graph/node boundary.

    ``apply`` must update the graph state (or return a patch) and may raise. A
    raised exception leaves the message pending for retry. The middleware does not
    call LangGraph APIs, so applications can use it with Python or JS wrappers and
    choose their own checkpoint/interrupt implementation.
    """
    def __init__(self, queue: SteeringQueue, apply: Callable[[Guidance, Dict[str, Any]], Any]):
        self.queue = queue
        self.apply = apply

    def before_node(self, run_id: str, node: str, state: Dict[str, Any]) -> tuple:
        applied = []
        for message in self.queue.get_pending(run_id):
            result = self.apply(message, state)
            if isinstance(result, dict):
                state.update(result)
            self.queue.ack(run_id, message.id)
            applied.append(AppliedGuidance(message.id, message.text, node))
        return tuple(applied)

    def wrap_node(self, run_id: str, node: str, state: Dict[str, Any], fn: Callable):
        """Run the boundary then the node; return ``(state, applied)``."""
        applied = self.before_node(run_id, node, state)
        result = fn(state)
        if isinstance(result, dict):
            state.update(result)
        return state, applied


def interrupt_payload(applied):
    """Return a JSON-serializable audit payload for a LangGraph interrupt/UI."""
    return {'type': 'agent_steer', 'messages': [
        {'id': item.message_id, 'text': item.text, 'node': item.node} for item in applied]}
