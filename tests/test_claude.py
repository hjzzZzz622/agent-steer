import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor


class ClaudeEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'queue.sqlite3')

    def cli(self, *args, payload=None, ok=True):
        result = subprocess.run([sys.executable, '-m', 'agent_steer', '--db', self.db, *args],
                                input=payload, text=True, capture_output=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def hook(self, event='PostToolUse', session='s1'):
        return self.cli('claude-hook', payload=json.dumps({
            'hook_event_name': event, 'session_id': session, 'cwd': self.tmp.name}))

    def submit(self, text='0907 数据尚未落库，请查询 0906', session='s1'):
        return json.loads(self.cli('submit', '--session', session, text).stdout)

    def test_separate_process_delivery_retry_and_ack(self):
        self.hook('SessionStart')
        sessions = json.loads(self.cli('sessions').stdout)
        self.assertEqual(sessions[0]['session_id'], 's1')
        msg = self.submit()
        self.assertEqual(self.hook(session='s2').stdout, '')
        output = json.loads(self.hook().stdout)['hookSpecificOutput']
        self.assertEqual(output['hookEventName'], 'PostToolUse')
        self.assertIn('请查询 0906', output['additionalContext'])
        self.assertIn(msg['id'], output['additionalContext'])
        self.assertEqual(self.hook().stdout, '')
        status = json.loads(self.cli('messages', '--session', 's1').stdout)[0]
        self.assertEqual((status['status'], status['emitted']), ('pending', True))
        self.cli('retry', '--session', 's1', msg['id'])
        self.assertIn(msg['id'], self.hook('PostToolUseFailure').stdout)
        self.cli('ack', '--session', 's1', msg['id'])
        self.assertEqual(json.loads(self.cli('messages', '--session', 's1').stdout)[0]['status'], 'acknowledged')
        self.assertNotEqual(self.cli('retry', '--session', 's1', msg['id'], ok=False).returncode, 0)

    def test_concurrent_hooks_emit_once(self):
        self.hook('SessionStart')
        msg = self.submit()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.hook().stdout, range(4)))
        self.assertEqual(sum(msg['id'] in r for r in results), 1)

    def test_subagent_does_not_consume_parent_guidance(self):
        self.hook('SessionStart')
        msg = self.submit()
        result = self.cli('claude-hook', payload=json.dumps({
            'hook_event_name': 'PostToolUse', 'session_id': 's1',
            'cwd': self.tmp.name, 'agent_id': 'child-agent'}))
        self.assertEqual(result.stdout, '')
        status = json.loads(self.cli('messages', '--session', 's1').stdout)[0]
        self.assertFalse(status['emitted'])
        self.assertIn(msg['id'], self.hook().stdout)

    def test_bad_input_does_not_consume(self):
        self.hook('SessionStart')
        msg = self.submit()
        for payload in ['bad json', '[]', '{}', '{"session_id": 5}']:
            result = self.cli('claude-hook', payload=payload, ok=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
        self.assertIn(msg['id'], self.hook().stdout)
        self.assertNotEqual(self.cli('submit', '--session', 'typo', 'hello', ok=False).returncode, 0)

    def test_generated_settings_command_works_and_refuses_overwrite(self):
        path = Path(self.tmp.name) / 'settings with spaces.json'
        self.cli('claude-settings', '--output', str(path))
        config = json.loads(path.read_text())
        command = config['hooks']['SessionStart'][0]['hooks'][0]['command']
        result = subprocess.run(command, shell=True, text=True, capture_output=True,
                                input=json.dumps({'session_id': 'configured', 'cwd': self.tmp.name,
                                                  'hook_event_name': 'SessionStart'}))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.cli('sessions').stdout)[0]['session_id'], 'configured')
        self.assertNotEqual(self.cli('claude-settings', '--output', str(path), ok=False).returncode, 0)
        self.assertEqual(json.loads(path.read_text()), config)
