"""Local steering CLI. All machine-readable output goes to stdout."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from .core.sqlite import SQLiteSteeringQueue
from .adapters.claude_code.hook import handle, settings


def main(argv=None):
    parser = argparse.ArgumentParser(prog='agent-steer')
    parser.add_argument('--db', required=True, help='shared local SQLite path (use the same path in both terminals)')
    sub = parser.add_subparsers(dest='command', required=True)
    config = sub.add_parser('claude-settings', help='generate a new settings file for claude --settings')
    config.add_argument('--output', required=True)
    sub.add_parser('claude-hook', help='read Claude hook JSON on stdin')
    sub.add_parser('sessions', help='list observed sessions; last_seen is not a liveness guarantee')
    for name in ('submit', 'messages', 'ack', 'retry'):
        command = sub.add_parser(name)
        command.add_argument('--session', required=True)
        if name == 'submit':
            command.add_argument('text')
        elif name in ('ack', 'retry'):
            command.add_argument('message_id')
    args = parser.parse_args(argv)
    try:
        db_path = str(Path(args.db).expanduser().resolve())
        if args.command == 'claude-settings':
            output = Path(args.output).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation: never clobber user configuration.
            with output.open('x', encoding='utf-8') as stream:
                json.dump(settings(db_path), stream, indent=2)
                stream.write('\n')
            print(json.dumps({'settings': str(output), 'db': db_path}))
            return 0
        queue = SQLiteSteeringQueue(db_path)
        if args.command == 'claude-hook':
            handle(queue, json.load(sys.stdin), sys.stdout)
            return 0
        if args.command == 'sessions':
            result = queue.sessions()
        elif args.command == 'messages':
            result = queue.messages(args.session)
        elif args.command == 'submit':
            if args.session not in {s['session_id'] for s in queue.sessions()}:
                raise ValueError('unknown session; start Claude with the generated settings and run sessions')
            result = queue.submit(args.session, args.text).to_dict()
        else:
            getattr(queue, args.command)(args.session, args.message_id)
            result = {'ok': True}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
        print(f'agent-steer: {exc}', file=sys.stderr)
        return 1
