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
    sub.add_parser('mcp', help='run the dependency-free MCP server over JSON lines')
    sub.add_parser('skill-path', help='print the bundled interaction skill path')
    codex = sub.add_parser('codex-run', help='start a Codex App Server turn and accept steering')
    codex.add_argument('prompt')
    codex.add_argument('--cwd', required=True)
    codex.add_argument('--model', required=True)
    codex.add_argument('--codex-bin', default='codex')
    codex.add_argument('--timeout', type=float, default=300)
    codex.add_argument('--sandbox', choices=('read-only', 'workspace-write'), default='read-only')
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
        if args.command == 'mcp':
            from .mcp import serve
            serve(queue)
            return 0
        if args.command == 'skill-path':
            print(str(Path(__file__).resolve().parents[2] / 'skills' / 'agent-steer' / 'SKILL.md'))
            return 0
        if args.command == 'codex-run':
            from .adapters.codex.runner import run_session
            if args.timeout <= 0:
                raise ValueError('timeout must be positive')
            def output(event):
                print(json.dumps(event, ensure_ascii=False), flush=True)
            result = run_session(queue, args.prompt, args.cwd, args.model,
                                 timeout=args.timeout, codex_bin=args.codex_bin,
                                 sandbox=args.sandbox, sink=output)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result['status'] == 'completed' else 1
        if args.command == 'claude-hook':
            handle(queue, json.load(sys.stdin), sys.stdout)
            return 0
        if args.command == 'sessions':
            result = queue.sessions()
        elif args.command == 'messages':
            result = queue.messages(args.session)
        elif args.command == 'submit':
            if args.session not in {s['session_id'] for s in queue.sessions()}:
                raise ValueError('unknown session; start a configured agent session and run sessions')
            result = queue.submit(args.session, args.text).to_dict()
        else:
            getattr(queue, args.command)(args.session, args.message_id)
            result = {'ok': True}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, OSError, sqlite3.Error, RuntimeError, EOFError) as exc:
        print(f'agent-steer: {exc}', file=sys.stderr)
        return 1
