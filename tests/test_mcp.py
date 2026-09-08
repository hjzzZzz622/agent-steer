import tempfile
import unittest
from pathlib import Path

from agent_steer.mcp import MCPServer
from agent_steer.core.sqlite import SQLiteSteeringQueue


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'inbox.sqlite3'
        self.queue = SQLiteSteeringQueue(self.db)
        self.server = MCPServer(self.queue)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tools_list_exposes_submit_pending_and_questions(self):
        result = self.server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        names = {tool['name'] for tool in result['result']['tools']}
        self.assertTrue({'steering_submit', 'steering_get_pending', 'steering_ask_user', 'steering_answer'} <= names)

    def test_submit_and_pending_are_available_through_mcp(self):
        self.queue.register('run-1', '/tmp/project')
        submit = self.server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'steering_submit', 'arguments': {'run_id': 'run-1', 'text': 'use 0906'}}})
        self.assertEqual(submit['result']['structuredContent']['message']['text'], 'use 0906')
        pending = self.server.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'steering_get_pending', 'arguments': {'run_id': 'run-1'}}})
        self.assertEqual(pending['result']['structuredContent']['messages'][0]['text'], 'use 0906')

    def test_question_answer_round_trip(self):
        self.queue.register('run-1', '/tmp/project')
        asked = self.server.handle({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'steering_ask_user', 'arguments': {'run_id': 'run-1', 'question': 'Which snapshot?', 'options': ['0814', '0907']}}})
        question_id = asked['result']['structuredContent']['question']['id']
        answer = self.server.handle({'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call', 'params': {'name': 'steering_answer', 'arguments': {'run_id': 'run-1', 'question_id': question_id, 'answer': '0814'}}})
        self.assertEqual(answer['result']['structuredContent']['question']['answer'], '0814')
