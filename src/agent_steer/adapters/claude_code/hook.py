"""Claude Code synchronous command hook protocol."""
import json
import shlex
import sys

EVENTS = ('SessionStart', 'PostToolUse', 'PostToolUseFailure')


def handle(queue, payload, stdout):
    if not isinstance(payload, dict):
        raise ValueError('hook input must be an object')
    for field in ('session_id', 'cwd', 'hook_event_name'):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise ValueError(f'hook requires non-empty {field}')
    event = payload['hook_event_name']
    if event not in EVENTS:
        raise ValueError('unsupported hook event')
    # Subagents should not consume parent-session guidance.
    if payload.get('agent_id'):
        return
    session = payload['session_id']
    queue.register(session, payload['cwd'])
    if event == 'SessionStart':
        return

    def emit(messages):
        context = ('User runtime guidance for this session. Continue the existing task, '
                   'preserve completed work, and incorporate the following corrections '
                   'where applicable under existing permissions. Briefly acknowledge '
                   'what you changed. Message IDs are for deduplication.\n'
                   + json.dumps([m.to_dict() for m in messages], ensure_ascii=False))
        json.dump({'hookSpecificOutput': {'hookEventName': event,
                                         'additionalContext': context}}, stdout, ensure_ascii=False)
        stdout.write('\n')
        stdout.flush()

    queue.emit_pending(session, emit)


def settings(db_path):
    # POSIX shell quoting; use the installed interpreter even outside an active venv.
    command = shlex.join([sys.executable, '-m', 'agent_steer', '--db', db_path, 'claude-hook'])
    return {'hooks': {event: [{'matcher': '*', 'hooks': [
        {'type': 'command', 'command': command, 'timeout': 10}]}] for event in EVENTS}}
