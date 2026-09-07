import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

from agent_steer.adapters.codex.client import AppServer, RPCError
from agent_steer.adapters.codex.runner import run_session
from agent_steer.core.sqlite import SQLiteSteeringQueue


SERVER = '''
import json, sys
for line in sys.stdin:
    msg=json.loads(line)
    method=msg.get('method')
    if 'id' not in msg: continue
    def send(value):
        print(json.dumps(value),flush=True)
    result={}
    if method=='initialize': result={'userAgent':'test'}
    elif method=='thread/start': result={'thread':{'id':'thread-1'}}
    elif method=='turn/start': result={'turn':{'id':'turn-1'}}
    elif method=='turn/steer':
        assert msg['params']['expectedTurnId']=='turn-1'
        if 'reject' in msg['params']['input'][0]['text']:
            send({'id':msg['id'],'error':{'code':-32000,'message':'turn ended'}})
            if 'finished' in msg['params']['input'][0]['text']:
                send({'method':'turn/completed','params':{'threadId':'thread-1',
                      'turn':{'id':'turn-1','status':'completed'}}})
            continue
        result={'turnId':'turn-1'}
    elif method=='fail':
        send({'id':msg['id'],'error':{'code':-32000,'message':'test rejection'}})
        continue
    send({'method':'test/notification','params':{}})
    send({'id':msg['id'],'result':result})
    if method=='turn/steer':
        send({'method':'turn/completed','params':{'threadId':'thread-1',
              'turn':{'id':'turn-1','status':'completed','error':None}}})
'''


class CodexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        script = self.root / 'server.py'
        script.write_text(SERVER)
        self.command = [sys.executable, str(script)]

    def test_response_correlation_and_rpc_error(self):
        with AppServer(self.command) as server:
            self.assertEqual(server.request('initialize', {})['userAgent'], 'test')
            self.assertEqual(server.event(1)['method'], 'test/notification')
            with self.assertRaises(RPCError):
                server.request('fail', {})

    def test_steering_acceptance_is_not_acknowledgement(self):
        queue = SQLiteSteeringQueue(self.root / 'inbox.sqlite3')
        sent = []
        events = []
        def tick(run_id):
            if not sent:
                sent.append(queue.submit(run_id, 'query 0906'))
        result = run_session(queue, 'query 0907', self.root, 'test-model',
                             timeout=5, command=self.command, sink=events.append, on_tick=tick)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(queue.status(result['run_id'], sent[0].id), 'pending')
        self.assertTrue(queue.messages(result['run_id'])[0]['emitted'])
        self.assertTrue(any(e['method'] == 'steering/accepted' for e in events))

    def test_rejection_remains_pending(self):
        queue = SQLiteSteeringQueue(self.root / 'inbox.sqlite3')
        def tick(run_id):
            if not queue.messages(run_id):
                queue.submit(run_id, 'reject')
        with self.assertRaises(RPCError):
            run_session(queue, 'start', self.root, 'test-model', timeout=5,
                        command=self.command, on_tick=tick)
        messages = queue.messages('codex:thread-1:turn-1')
        self.assertFalse(messages[0]['emitted'])
        self.assertEqual(messages[0]['status'], 'pending')

    def test_timeout_interrupts_and_preserves_inbox(self):
        queue = SQLiteSteeringQueue(self.root / 'inbox.sqlite3')
        with self.assertRaises(TimeoutError):
            run_session(queue, 'start', self.root, 'test-model', timeout=0.3,
                        command=self.command)

    def test_completed_turn_wins_rejected_steer_race(self):
        queue = SQLiteSteeringQueue(self.root / 'inbox.sqlite3')
        def tick(run_id):
            if not queue.messages(run_id):
                queue.submit(run_id, 'reject finished')
        result = run_session(queue, 'start', self.root, 'test-model', timeout=5,
                             command=self.command, on_tick=tick)
        self.assertEqual(result['status'], 'completed')
        self.assertFalse(queue.messages(result['run_id'])[0]['emitted'])

    def test_benchmark_orchestration_with_fake_app_server(self):
        from benchmarks.codex_run import trial
        from benchmarks.scenarios import SCENARIOS
        script = self.root / 'benchmark_server.py'
        script.write_text('''
import json, shlex, subprocess, sys
condition, target = sys.argv[1:]
def send(value): print(json.dumps(value),flush=True)
def finish(result):
    send({'method':'item/completed','params':{'item':{
        'type':'agentMessage','text':result}}})
    send({'method':'turn/completed','params':{'threadId':'thread-1',
          'turn':{'id':'turn-1','status':'completed'}}})
for line in sys.stdin:
    msg=json.loads(line)
    if 'id' not in msg: continue
    method=msg.get('method'); result={}
    if method=='thread/start': result={'thread':{'id':'thread-1'}}
    if method=='turn/start': result={'turn':{'id':'turn-1'}}
    if method=='turn/steer': result={'turnId':'turn-1'}
    send({'id':msg['id'],'result':result})
    if method=='turn/start':
        prompt=msg['params']['input'][0]['text']
        command=shlex.split(prompt.split('First run exactly: ',1)[1].split('. Use sequential',1)[0])
        answer=subprocess.check_output(command,text=True)
        if condition=='baseline': finish(answer)
    if method=='turn/steer':
        text=msg['params']['input'][0]['text']
        receipt=text.split('--receipt ',1)[1].split(' ',1)[0]
        command[-1]=target
        command.extend(['--receipt',receipt])
        finish(subprocess.check_output(command,text=True))
''')
        args = SimpleNamespace(model='fake', timeout=5, codex_bin='unused')
        for scenario in SCENARIOS:
            for condition in ('baseline', 'steered'):
                folder = self.root / (scenario['name'] + condition)
                folder.mkdir()
                row = trial(folder, scenario, condition, args,
                            command=[sys.executable, str(script), condition, scenario['target']])
                self.assertTrue(row['success'], row)
                self.assertEqual(row['adopted'], condition == 'steered')
