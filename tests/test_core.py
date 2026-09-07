import json
import unittest
from concurrent.futures import ThreadPoolExecutor

from agent_steer.core import InMemorySteeringQueue, Guidance
from agent_steer.adapters.base import apply_pending


class SteeringTests(unittest.TestCase):
    def setUp(self):
        self.queue = InMemorySteeringQueue()

    def test_fifo_run_isolation_and_non_destructive_read(self):
        first = self.queue.submit('a', 'first')
        second = self.queue.submit('a', 'second')
        self.queue.submit('b', 'private to b')
        self.assertEqual(self.queue.get_pending('a'), (first, second))
        self.assertEqual(self.queue.get_pending('a'), (first, second))
        self.assertEqual(self.queue.get_pending('unknown'), ())

    def test_ack_is_idempotent_and_scoped(self):
        msg = self.queue.submit('a', 'change date')
        with self.assertRaises(KeyError):
            self.queue.ack('b', msg.id)
        self.assertEqual(self.queue.status('a', msg.id), 'pending')
        self.queue.ack('a', msg.id)
        self.queue.ack('a', msg.id)
        self.assertEqual(self.queue.status('a', msg.id), 'acknowledged')
        self.assertEqual(self.queue.get_pending('a'), ())
        with self.assertRaises(KeyError):
            self.queue.status('a', 'missing')

    def test_invalid_message(self):
        for run, text in [('', 'ok'), ('a', ' '), (None, 'ok'), ('a', 3)]:
            with self.assertRaises(ValueError):
                self.queue.submit(run, text)

    def test_wire_roundtrip_and_validation(self):
        msg = self.queue.submit('a', '查询 0906')
        payload = json.loads(json.dumps(msg.to_dict()))
        self.assertEqual(Guidance.from_dict(payload), msg)
        payload['version'] = '2'
        with self.assertRaises(ValueError):
            Guidance.from_dict(payload)

    def test_concurrent_producers_do_not_lose_messages(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            messages = list(pool.map(lambda i: self.queue.submit('a', str(i)), range(100)))
        self.assertEqual(len({m.id for m in messages}), 100)
        self.assertEqual(len(self.queue.get_pending('a')), 100)

    def test_failed_application_is_pending_for_retry(self):
        msg = self.queue.submit('a', 'retry')
        def fail(message):
            raise RuntimeError('host unavailable')
        with self.assertRaises(RuntimeError):
            apply_pending(self.queue, 'a', fail)
        self.assertEqual(self.queue.status('a', msg.id), 'pending')
        seen = []
        self.assertEqual(apply_pending(self.queue, 'a', seen.append), 1)
        self.assertEqual(seen, [msg])
        self.assertEqual(apply_pending(self.queue, 'a', seen.append), 0)

    def test_date_correction_preserves_run(self):
        state = {'run_id': 'report-1', 'date': '0907', 'completed_steps': ['plan']}
        self.queue.submit(state['run_id'], '0907 数据尚未落库，请查询 0906')
        def apply(message):
            state['date'] = '0906'
        apply_pending(self.queue, state['run_id'], apply)
        self.assertEqual(state, {'run_id': 'report-1', 'date': '0906', 'completed_steps': ['plan']})


if __name__ == '__main__':
    unittest.main()
