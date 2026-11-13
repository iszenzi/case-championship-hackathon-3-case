import json
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager


def uid(prefix):
    return prefix + "-" + uuid.uuid4().hex[:12]


class Store:
    def __init__(self, root):
        self.path = Path(root) / "data" / "copilot.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, at REAL, action TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pilots(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS court_runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS judicial_runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS scenario_runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def all(self, table):
        if table not in ("cases", "documents", "pilots", "court_runs", "judicial_runs", "scenario_runs"):
            raise ValueError("Unknown table")
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute(f"SELECT payload FROM {table} ORDER BY rowid DESC")]

    def get(self, table, ident):
        if table not in ("cases", "documents", "pilots", "court_runs", "judicial_runs", "scenario_runs"):
            raise ValueError("Unknown table")
        with self.connect() as db:
            row = db.execute(f"SELECT payload FROM {table} WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise KeyError("Запись не найдена")
        return json.loads(row[0])

    def put(self, table, obj, action=None, details=None):
        if table not in ("cases", "documents", "pilots", "court_runs", "judicial_runs", "scenario_runs"):
            raise ValueError("Unknown table")
        with self.connect() as db:
            db.execute(f"INSERT INTO {table}(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                       (obj["id"], json.dumps(obj, ensure_ascii=False)))
            if action:
                db.execute("INSERT INTO events(case_id,at,action,payload) VALUES(?,?,?,?)",
                           (obj["id"], time.time(), action, json.dumps(details or {}, ensure_ascii=False)))
        return obj

    def events(self, ident):
        with self.connect() as db:
            return [dict(row) | {"payload": json.loads(row["payload"])} for row in db.execute(
                "SELECT seq,at,action,payload FROM events WHERE case_id=? ORDER BY seq", (ident,))]

    def delete(self, table, ident):
        if table not in ("documents", "pilots"):
            raise ValueError("Удаление недоступно")
        with self.connect() as db:
            db.execute(f"DELETE FROM {table} WHERE id=?", (ident,))
