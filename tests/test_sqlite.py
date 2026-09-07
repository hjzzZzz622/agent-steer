import tempfile
from pathlib import Path
import unittest
from agent_steer.core.sqlite import SQLiteSteeringQueue


class DurableQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'inbox.sqlite3'
        self.queue = SQLiteSteeringQueue(self.path)

    def test_core_contract_survives_reopen(self):
        first = self.queue.submit('a', 'first')
        second = self.queue.submit('a', 'second')
        self.queue.submit('b', 'isolated')
        reopened = SQLiteSteeringQueue(self.path)
        self.assertEqual(reopened.get_pending('a'), (first, second))
        self.assertEqual(reopened.get_pending('a'), (first, second))
        with self.assertRaises(KeyError):
            reopened.ack('b', first.id)
        reopened.ack('a', first.id)
        reopened.ack('a', first.id)
        self.assertEqual(self.queue.status('a', first.id), 'acknowledged')
        self.assertEqual(self.queue.get_pending('a'), (second,))
        with self.assertRaises(KeyError):
            self.queue.status('a', 'missing')

    def test_failed_output_remains_retryable(self):
        message = self.queue.submit('a', 'correction')
        def broken_output(messages):
            raise BrokenPipeError('host disconnected')
        with self.assertRaises(BrokenPipeError):
            self.queue.emit_pending('a', broken_output)
        emitted = []
        self.assertEqual(self.queue.emit_pending('a', emitted.extend), 1)
        self.assertEqual(emitted, [message])
        self.assertEqual(self.queue.status('a', message.id), 'pending')

    def test_batches_preserve_fifo(self):
        messages = [self.queue.submit('a', str(i)) for i in range(10)]
        emitted = []
        self.assertEqual(self.queue.emit_pending('a', emitted.extend), 8)
        self.assertEqual(self.queue.emit_pending('a', emitted.extend), 2)
        self.assertEqual(emitted, messages)

    def test_input_limits(self):
        for value in ['', ' ', 'x' * 8001]:
            with self.assertRaises(ValueError):
                self.queue.submit('a', value)
