"""Store contract and an in-process reference implementation."""
from threading import RLock
from typing import Literal, Protocol, Tuple
from .models import Guidance

Status = Literal['pending', 'acknowledged']


class SteeringQueue(Protocol):
    def submit(self, run_id: str, text: str) -> Guidance: ...
    def get_pending(self, run_id: str) -> Tuple[Guidance, ...]: ...
    def ack(self, run_id: str, message_id: str) -> None: ...
    def status(self, run_id: str, message_id: str) -> Status: ...


class InMemorySteeringQueue:
    """Thread-safe, FIFO, single logical consumer per run; no persistence.

    Reads do not claim messages. Consumers must serialize applications per run.
    Acknowledged messages remain available for status inspection until exit.
    """
    def __init__(self):
        self._messages = {}
        self._acknowledged = set()
        self._lock = RLock()

    def submit(self, run_id: str, text: str) -> Guidance:
        message = Guidance(run_id=run_id, text=text)
        with self._lock:
            self._messages[(run_id, message.id)] = message
        return message

    def get_pending(self, run_id: str) -> Tuple[Guidance, ...]:
        with self._lock:
            return tuple(message for key, message in self._messages.items()
                         if key[0] == run_id and key not in self._acknowledged)

    def ack(self, run_id: str, message_id: str) -> None:
        key = (run_id, message_id)
        with self._lock:
            if key not in self._messages:
                raise KeyError(key)
            self._acknowledged.add(key)

    def status(self, run_id: str, message_id: str) -> Status:
        key = (run_id, message_id)
        with self._lock:
            if key not in self._messages:
                raise KeyError(key)
            return 'acknowledged' if key in self._acknowledged else 'pending'
