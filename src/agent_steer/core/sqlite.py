"""Durable local steering inbox. Single-user filesystem trust boundary."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from .models import Guidance


class SQLiteSteeringQueue:
    def __init__(self, path):
        self.path = str(Path(path).expanduser().resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS messages (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT UNIQUE NOT NULL, run_id TEXT NOT NULL,
                    text TEXT NOT NULL, created_at TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    emitted INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY, cwd TEXT NOT NULL,
                    last_seen TEXT NOT NULL);
            ''')

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _message(row):
        return Guidance(run_id=row['run_id'], text=row['text'], id=row['id'],
                        created_at=row['created_at'])

    def submit(self, run_id, text):
        message = Guidance(run_id=run_id, text=text)
        if len(text) > 8000:
            raise ValueError('guidance is limited to 8000 characters')
        with self._connection() as db:
            db.execute('INSERT INTO messages (id,run_id,text,created_at) VALUES (?,?,?,?)',
                       (message.id, run_id, text, message.created_at))
        return message

    def get_pending(self, run_id):
        with self._connection() as db:
            return tuple(self._message(r) for r in db.execute(
                'SELECT * FROM messages WHERE run_id=? AND acknowledged=0 ORDER BY seq', (run_id,)))

    def ack(self, run_id, message_id):
        with self._connection() as db:
            result = db.execute('UPDATE messages SET acknowledged=1 WHERE run_id=? AND id=?',
                                (run_id, message_id))
            if not result.rowcount:
                raise KeyError('unknown message in this session')

    def status(self, run_id, message_id):
        with self._connection() as db:
            row = db.execute('SELECT acknowledged FROM messages WHERE run_id=? AND id=?',
                             (run_id, message_id)).fetchone()
            if row is None:
                raise KeyError('unknown message in this session')
            return 'acknowledged' if row[0] else 'pending'

    def register(self, session_id, cwd):
        with self._connection() as db:
            db.execute('''INSERT INTO sessions VALUES (?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                ON CONFLICT(session_id) DO UPDATE SET cwd=excluded.cwd,last_seen=excluded.last_seen''',
                       (session_id, cwd))

    def sessions(self):
        with self._connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM sessions ORDER BY last_seen DESC')]

    def messages(self, run_id):
        with self._connection() as db:
            return [dict(self._message(r).to_dict(), emitted=bool(r['emitted']),
                         status='acknowledged' if r['acknowledged'] else 'pending')
                    for r in db.execute('SELECT * FROM messages WHERE run_id=? ORDER BY seq', (run_id,))]

    def retry(self, run_id, message_id):
        with self._connection() as db:
            result = db.execute('''UPDATE messages SET emitted=0
                WHERE run_id=? AND id=? AND acknowledged=0''', (run_id, message_id))
            if not result.rowcount:
                raise ValueError('message missing or already acknowledged')

    def emit_pending(self, run_id, emit):
        """Serialize outputs, flush via callback, then record emission, never ack.

        Callback errors roll back. Process crashes can duplicate output. Successful
        stdout writes do not prove host ingestion; manual retry is available.
        """
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = list(db.execute('''SELECT * FROM messages
                WHERE run_id=? AND acknowledged=0 AND emitted=0 ORDER BY seq LIMIT 8''', (run_id,)))
            if rows:
                emit(tuple(self._message(r) for r in rows))
                db.executemany('UPDATE messages SET emitted=1 WHERE id=?', [(r['id'],) for r in rows])
            return len(rows)
