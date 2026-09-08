"""Dependency-free MCP JSON-RPC server for the steering queue."""
import json
import sys
import uuid


TOOLS = [
    {'name': 'steering_submit', 'description': 'Submit runtime guidance for an active agent run.', 'inputSchema': {'type': 'object', 'required': ['run_id', 'text'], 'properties': {'run_id': {'type': 'string'}, 'text': {'type': 'string'}}}},
    {'name': 'steering_get_pending', 'description': 'Read unacknowledged guidance for this run.', 'inputSchema': {'type': 'object', 'required': ['run_id'], 'properties': {'run_id': {'type': 'string'}}}},
    {'name': 'steering_ask_user', 'description': 'Create a clarification question for the user and pause at the host boundary.', 'inputSchema': {'type': 'object', 'required': ['run_id', 'question'], 'properties': {'run_id': {'type': 'string'}, 'question': {'type': 'string'}, 'options': {'type': 'array', 'items': {'type': 'string'}}}}},
    {'name': 'steering_answer', 'description': 'Answer an open clarification question.', 'inputSchema': {'type': 'object', 'required': ['run_id', 'question_id', 'answer'], 'properties': {'run_id': {'type': 'string'}, 'question_id': {'type': 'string'}, 'answer': {'type': 'string'}}}},
]


class MCPServer:
    def __init__(self, queue):
        self.queue = queue
        with queue._connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS questions (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL, question TEXT NOT NULL,
                options TEXT NOT NULL, answer TEXT, created_at TEXT NOT NULL,
                answered_at TEXT)''')

    def _result(self, value):
        return {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}], 'structuredContent': value}

    def call(self, name, args):
        if name == 'steering_submit':
            message = self.queue.submit(args['run_id'], args['text'])
            return self._result({'message': message.to_dict()})
        if name == 'steering_get_pending':
            return self._result({'messages': [m.to_dict() for m in self.queue.get_pending(args['run_id'])]})
        if name == 'steering_ask_user':
            question_id = str(uuid.uuid4())
            options = args.get('options') or []
            with self.queue._connection() as db:
                db.execute("INSERT INTO questions (id,run_id,question,options,created_at,answer,answered_at) VALUES (?,?,?,?,datetime('now'),NULL,NULL)",
                           (question_id, args['run_id'], args['question'], json.dumps(options, ensure_ascii=False)))
            return self._result({'question': {'id': question_id, 'run_id': args['run_id'], 'question': args['question'], 'options': options, 'status': 'open'}})
        if name == 'steering_answer':
            with self.queue._connection() as db:
                row = db.execute('SELECT * FROM questions WHERE id=? AND run_id=?', (args['question_id'], args['run_id'])).fetchone()
                if row is None:
                    raise KeyError('unknown question in this session')
                if row['answer'] is not None:
                    raise ValueError('question already answered')
                db.execute("UPDATE questions SET answer=?, answered_at=datetime('now') WHERE id=?", (args['answer'], args['question_id']))
                value = {'id': row['id'], 'run_id': row['run_id'], 'question': row['question'], 'options': json.loads(row['options']), 'answer': args['answer'], 'status': 'answered'}
            return self._result({'question': value})
        raise ValueError('unknown tool')

    def handle(self, request):
        method = request.get('method')
        if method == 'initialize':
            return {'jsonrpc': '2.0', 'id': request.get('id'), 'result': {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'agent-steer', 'version': '0.4.0'}}}
        if method == 'tools/list':
            return {'jsonrpc': '2.0', 'id': request.get('id'), 'result': {'tools': TOOLS}}
        if method == 'tools/call':
            try:
                result = self.call(request['params']['name'], request['params'].get('arguments') or {})
                return {'jsonrpc': '2.0', 'id': request.get('id'), 'result': result}
            except (KeyError, ValueError) as exc:
                return {'jsonrpc': '2.0', 'id': request.get('id'), 'error': {'code': -32602, 'message': str(exc)}}
        return {'jsonrpc': '2.0', 'id': request.get('id'), 'error': {'code': -32601, 'message': 'method not found'}}


def serve(queue, stdin=None, stdout=None):
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    server = MCPServer(queue)
    for line in stdin:
        if line.strip():
            stdout.write(json.dumps(server.handle(json.loads(line)), ensure_ascii=False) + '\n')
            stdout.flush()


def main():
    from .core.sqlite import SQLiteSteeringQueue
    import argparse
    parser = argparse.ArgumentParser(prog='agent-steer-mcp')
    parser.add_argument('--db', required=True)
    args = parser.parse_args()
    serve(SQLiteSteeringQueue(args.db))
