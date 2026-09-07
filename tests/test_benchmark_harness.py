"""A fake model driver validates orchestration, not Claude's behavior."""
import json
from pathlib import Path
import tempfile
import unittest
from benchmarks.run import main

FAKE = '''#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
if '--version' in sys.argv:
    print('fake-driver-for-tests')
    raise SystemExit()
settings = json.loads(Path(sys.argv[sys.argv.index('--settings')+1]).read_text())
session = sys.argv[sys.argv.index('--session-id')+1]
command = settings['hooks']['SessionStart'][0]['hooks'][0]['command']
import shlex
config = json.loads(Path(shlex.split(command)[-1]).read_text())
def hook(event):
    result = subprocess.run(command, shell=True, input=json.dumps({'session_id':session,
        'cwd':str(Path.cwd()), 'hook_event_name':event}),text=True,capture_output=True)
    assert result.returncode == 0, result.stderr
    return result.stdout
hook('SessionStart')
prompt = sys.argv[sys.argv.index('-p')+1]
query = prompt.split('Run this exact query first: ',1)[1].split('. Use sequential',1)[0]
first = subprocess.check_output(shlex.split(query),text=True)
output = hook('PostToolUse')
if output:
    parts = shlex.split(query)
    parts[-1] = config['target']
    first = subprocess.check_output(parts,text=True)
    hook('PostToolUse')
print(json.dumps({'result': first.strip(), 'total_cost_usd':0, 'usage':{'input_tokens':1}}))
'''


class HarnessTests(unittest.TestCase):
    def test_live_orchestration_with_explicit_fake_driver(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'fake-claude'
            fake.write_text(FAKE)
            fake.chmod(0o700)
            output = Path(tmp) / 'results'
            code = main(['--mode', 'claude', '--repeats', '1', '--output', str(output),
                         '--model', 'fake', '--budget-usd', '0.1', '--claude-bin', str(fake)])
            self.assertEqual(code, 0)
            rows = [json.loads(line) for line in (output / 'trials.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), 6)
            for row in rows:
                if row['condition'] == 'steered':
                    self.assertTrue(row['adopted'])
                    self.assertTrue(row['revised_target_success'])
                else:
                    self.assertFalse(row['emitted'])
                    self.assertTrue(row['initial_task_success'])
                    self.assertFalse(row['revised_target_success'])

    def test_missing_claude_fails_before_creating_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'results'
            with self.assertRaises(SystemExit):
                main(['--mode', 'claude', '--model', 'fake', '--budget-usd', '1',
                      '--claude-bin', str(Path(tmp) / 'missing'), '--output', str(output)])
            self.assertFalse(output.exists())
