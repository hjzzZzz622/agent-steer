import unittest
import tempfile
from pathlib import Path

from agent_steer.adapters.langgraph.middleware import SteeringMiddleware, interrupt_payload
from agent_steer.core import InMemorySteeringQueue
from agent_steer.core.sqlite import SQLiteSteeringQueue


class LangGraphMiddlewareTests(unittest.TestCase):
    def test_boundary_updates_state_and_acknowledges_after_success(self):
        queue = InMemorySteeringQueue()
        state = {'date': '0907', 'completed': ['read_csv']}
        queue.submit('thread-1', '改查 0906')
        middleware = SteeringMiddleware(queue, lambda message, current: {'date': '0906'})
        applied = middleware.before_node('thread-1', 'query', state)
        self.assertEqual(state, {'date': '0906', 'completed': ['read_csv']})
        self.assertEqual(state and applied[0].node, 'query')
        self.assertEqual(queue.get_pending('thread-1'), ())
        self.assertEqual(interrupt_payload(applied)['messages'][0]['text'], '改查 0906')

    def test_failed_apply_stays_pending_for_retry(self):
        queue = InMemorySteeringQueue()
        queue.submit('thread-1', '改用 0814 快照')
        calls = []
        def apply(message, state):
            calls.append(message.id)
            if len(calls) == 1:
                raise RuntimeError('checkpoint unavailable')
            return {'snapshot': '0814'}
        middleware = SteeringMiddleware(queue, apply)
        with self.assertRaises(RuntimeError):
            middleware.before_node('thread-1', 'aggregate', {})
        self.assertEqual(len(queue.get_pending('thread-1')), 1)
        state = {}
        applied = middleware.before_node('thread-1', 'aggregate', state)
        self.assertEqual(state['snapshot'], '0814')
        self.assertEqual(len(applied), 1)

    def test_sqlite_queue_survives_interrupt_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            queue = SQLiteSteeringQueue(Path(folder) / 'state.sqlite3')
            queue.submit('graph-thread-7', 'mTKE 分子使用 ip_gpu_count')
            resumed = SQLiteSteeringQueue(Path(folder) / 'state.sqlite3')
            state = {'numerator': 'optimized_gpu_cards', 'steps': ['load']}
            middleware = SteeringMiddleware(resumed, lambda m, s: {'numerator': 'ip_gpu_count'})
            state, applied = middleware.wrap_node('graph-thread-7', 'calculate', state, lambda s: {'steps': s['steps'] + ['calculate']})
            self.assertEqual(state, {'numerator': 'ip_gpu_count', 'steps': ['load', 'calculate']})
            self.assertEqual(len(applied), 1)
            self.assertEqual(resumed.messages('graph-thread-7')[0]['status'], 'acknowledged')

    def test_run_isolation(self):
        queue = InMemorySteeringQueue()
        queue.submit('thread-a', 'A')
        queue.submit('thread-b', 'B')
        middleware = SteeringMiddleware(queue, lambda m, s: {'value': m.text})
        state = {}
        middleware.before_node('thread-a', 'node', state)
        self.assertEqual(state['value'], 'A')
        self.assertEqual(queue.get_pending('thread-b')[0].text, 'B')
