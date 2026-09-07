"""Inject at first completed fixture boundary, then exercise production hook."""
import io
import json
from pathlib import Path
import sys
import time
from agent_steer.adapters.claude_code.hook import handle
from agent_steer.core.sqlite import SQLiteSteeringQueue


def main():
    config = json.loads(Path(sys.argv[1]).read_text())
    payload = json.load(sys.stdin)
    if payload.get('session_id') != config['session'] or payload.get('agent_id'):
        return
    queue = SQLiteSteeringQueue(config['db'])
    trace = Path(config['trace'])
    if payload.get('hook_event_name') == 'PostToolUse' and trace.exists():
        calls = [json.loads(line) for line in trace.read_text().splitlines()]
        if calls and calls[0]['selection'] == config['initial']:
            try:
                # Main benchmark uses sequential fixture calls; marker makes
                # accidental repeated hook invocation unable to re-submit.
                with open(config['boundary'], 'x') as stream:
                    stream.write(str(time.time_ns()))
            except FileExistsError:
                pass
            else:
                if config['condition'] == 'steered':
                    queue.submit(config['session'], config['guidance'])
    class RecordingOutput:
        def __init__(self):
            self.buffer = io.StringIO()

        def write(self, value):
            sys.stdout.write(value)
            self.buffer.write(value)

        def flush(self):
            sys.stdout.flush()

    output = RecordingOutput()
    handle(queue, payload, output)
    value = output.buffer.getvalue()
    if value:
        with open(config['emissions'], 'a') as stream:
            stream.write(json.dumps({'at_ns': time.time_ns(), 'output': json.loads(value)}) + '\n')


if __name__ == '__main__':
    main()
