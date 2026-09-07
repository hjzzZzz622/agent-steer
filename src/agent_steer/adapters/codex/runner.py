"""Own one Codex thread/turn, poll shared inbox, steer without restarting."""
from pathlib import Path
import time
from .client import AppServer, RPCError


def run_session(queue, prompt, cwd, model, timeout=300, codex_bin='codex',
                sandbox='read-only', command=None, sink=lambda event: None,
                on_tick=None, output_schema=None):
    deadline = time.monotonic() + timeout
    with AppServer(command or [codex_bin, 'app-server']) as server:
        def request(method, params):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Codex session timed out')
            return server.request(method, params, timeout=min(15, remaining))

        request('initialize', {'clientInfo': {'name': 'agent_steer', 'version': '0.3.0'}})
        server.send({'method': 'initialized', 'params': {}})
        thread = request('thread/start', {'cwd': str(Path(cwd).resolve()), 'model': model,
                         'approvalPolicy': 'never', 'sandbox': sandbox})['thread']['id']
        params = {'threadId': thread, 'input': [{'type': 'text', 'text': prompt}]}
        if output_schema is not None:
            params['outputSchema'] = output_schema
        turn = request('turn/start', params)['turn']['id']
        run_id = f'codex:{thread}:{turn}'
        queue.register(run_id, str(Path(cwd).resolve()))
        sink({'method': 'steering/session', 'params': {'run_id': run_id,
              'threadId': thread, 'turnId': turn}})
        try:
            while time.monotonic() < deadline:
                # Process lifecycle notifications before polling; never intentionally
                # deliver a queued message into a subsequent turn.
                event = server.event(0.1)
                while event is not None:
                    sink(event)
                    data = event.get('params', {})
                    if (event.get('method') == 'turn/completed' and data.get('threadId') == thread
                            and data.get('turn', {}).get('id') == turn):
                        return dict(data['turn'], run_id=run_id)
                    event = server.event(0)
                if on_tick:
                    on_tick(run_id)

                def emit(messages):
                    response = request('turn/steer', {'threadId': thread, 'expectedTurnId': turn,
                        'input': [{'type': 'text', 'text': f'[{m.id}] {m.text}'} for m in messages]})
                    if response.get('turnId') != turn:
                        raise RPCError('turn/steer returned unexpected turnId')
                    sink({'method': 'steering/accepted', 'params': {
                        'run_id': run_id, 'ids': [m.id for m in messages], 'turnId': turn}})

                try:
                    queue.emit_pending(run_id, emit)
                except RPCError:
                    # Completion can race the request even after draining events.
                    # If the terminal event arrives, report that outcome and leave
                    # unaccepted guidance pending; never start another turn.
                    grace = min(deadline, time.monotonic() + 0.5)
                    while time.monotonic() < grace:
                        event = server.event(max(0, grace - time.monotonic()))
                        if event is None:
                            break
                        sink(event)
                        data = event.get('params', {})
                        if (event.get('method') == 'turn/completed' and data.get('threadId') == thread
                                and data.get('turn', {}).get('id') == turn):
                            return dict(data['turn'], run_id=run_id)
                    raise
            raise TimeoutError('Codex session timed out')
        except BaseException:
            # Best-effort cancellation before closing the transport. Preserve inbox.
            try:
                server.request('turn/interrupt', {'threadId': thread, 'turnId': turn}, timeout=2)
            except (OSError, RuntimeError, EOFError, TimeoutError):
                pass
            raise
