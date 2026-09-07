"""Small synchronous App Server JSON-lines client with background stdout reader."""
from collections import deque
import json
import queue
import subprocess
import threading
import time


class RPCError(RuntimeError):
    pass


class AppServer:
    def __init__(self, command):
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        text=True, bufsize=1)
        self.incoming = queue.Queue()
        self.events = deque()
        self.counter = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                self.incoming.put(json.loads(line))
        except (ValueError, OSError) as exc:
            self.incoming.put(exc)
        finally:
            self.incoming.put(EOFError('Codex App Server disconnected'))

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + '\n')
        self.process.stdin.flush()

    def _receive(self, timeout):
        try:
            value = self.incoming.get(timeout=max(0, timeout))
        except queue.Empty:
            return None
        if isinstance(value, Exception):
            raise value
        if not isinstance(value, dict):
            raise RPCError('App Server returned a non-object message')
        # No interactive approval UI in this MVP. Never auto-grant server requests.
        if 'method' in value and 'id' in value:
            self.send({'id': value['id'], 'error': {'code': -32601,
                       'message': 'This adapter cannot handle interactive server requests'}})
            return {'method': 'adapter/requestRejected', 'params': {'method': value['method']}}
        return value

    def request(self, method, params, timeout=15):
        self.counter += 1
        ident = self.counter
        self.send({'id': ident, 'method': method, 'params': params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = self._receive(deadline - time.monotonic())
            if value is None:
                continue
            if value.get('id') == ident and 'method' not in value:
                if 'error' in value:
                    raise RPCError(f'{method}: {value["error"]}')
                return value.get('result', {})
            if 'method' in value:
                self.events.append(value)
        raise TimeoutError(f'{method} response timed out; acceptance may be unknown')

    def event(self, timeout=0.2):
        if self.events:
            return self.events.popleft()
        return self._receive(timeout)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.reader.join(timeout=1)
        self.process.stdin.close()
        self.process.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
