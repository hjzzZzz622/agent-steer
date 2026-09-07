"""Cooperative boundary helper; the host owns authorization and execution."""
from typing import Callable
from ..core import Guidance, SteeringQueue


def apply_pending(queue: SteeringQueue, run_id: str,
                  apply: Callable[[Guidance], None]) -> int:
    """Apply a snapshot in FIFO order and ack only successful callbacks.

    Exceptions propagate, leaving the failed and subsequent messages pending.
    Serialize calls per run. Callbacks must deduplicate by message ID if their
    side effects can succeed before an exception or failed acknowledgement.
    Messages submitted during this call are read at the next boundary.
    """
    count = 0
    for message in queue.get_pending(run_id):
        apply(message)
        queue.ack(run_id, message.id)
        count += 1
    return count
