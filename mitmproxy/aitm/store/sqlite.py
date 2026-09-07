"""SQLite semantic state. Metadata/counters/deltas/evidence/episodes."""
from __future__ import annotations

import json
import os
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY, session TEXT, source TEXT, ts INTEGER, priority TEXT, posture TEXT, fp TEXT, meta TEXT);
CREATE TABLE IF NOT EXISTS counters(session TEXT, fp TEXT, bucket TEXT, n INTEGER, PRIMARY KEY(session, fp, bucket));
CREATE TABLE IF NOT EXISTS deltas(id TEXT PRIMARY KEY, session TEXT, subject TEXT, kind TEXT, summary TEXT, confidence REAL);
CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, hash TEXT, sensitivity TEXT, retention TEXT, access TEXT, location TEXT, expires_at INTEGER);
CREATE TABLE IF NOT EXISTS episodes(id TEXT PRIMARY KEY, session TEXT, task TEXT, summary TEXT, state TEXT, obs INTEGER);
CREATE INDEX IF NOT EXISTS idx_obs_session ON observations(session);
CREATE INDEX IF NOT EXISTS idx_delta_session ON deltas(session);
"""

class Store:
    def __init__(self, path: str, max_disk_bytes: int = 10737418240):
        self.path = path
        self.max_disk = max_disk_bytes
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        self._migrate_episodes()
        self.db.commit()

    def _migrate_episodes(self) -> None:
        cols = [r[1] for r in self.db.execute("PRAGMA table_info(episodes)")]
        if not cols:
            return
        sql = self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='episodes'"
        ).fetchone()
        legacy_agent = "agent" in cols
        unique_session = bool(sql and "UNIQUE" in sql[0])
        if not legacy_agent and not unique_session:
            return
        self.db.execute("ALTER TABLE episodes RENAME TO episodes_old")
        self.db.executescript(SCHEMA)
        if legacy_agent:
            self.db.execute(
                "INSERT OR IGNORE INTO episodes(id, session, task, summary, state, obs) "
                "SELECT id, session, task, summary, state, obs FROM episodes_old")
        else:
            self.db.execute(
                "INSERT OR IGNORE INTO episodes SELECT * FROM episodes_old")
        self.db.execute("DROP TABLE episodes_old")

    def _q(self, sql: str, args: tuple = ()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def save_observation(self, obs: dict, fp: str, posture: str) -> None:
        self._q("INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?,?)", (
            obs.get("id"), obs.get("sessionId"), obs.get("source"),
            obs.get("timestamp"), obs.get("priority"), posture, fp,
            json.dumps(obs.get("metadata", {}))[:8192],
        ))

    def add_counter(self, session: str, fp: str, bucket: str, n: int) -> None:
        with self.lock:
            cur = self.db.execute("SELECT n FROM counters WHERE session=? AND fp=? AND bucket=?", (session, fp, bucket))
            row = cur.fetchone()
            v = (row[0] if row else 0) + n
            self.db.execute("INSERT OR REPLACE INTO counters VALUES(?,?,?,?)", (session, fp, bucket, v))
            self.db.commit()

    def save_delta(self, delta: dict) -> None:
        self._q("INSERT OR IGNORE INTO deltas VALUES(?,?,?,?,?,?)", (
            delta.get("id"), delta.get("sessionId"), delta.get("subject"),
            delta.get("kind"), delta.get("summary"), delta.get("confidence", 0.0),
        ))
    def save_evidence(self, ev: dict) -> None:
        self._q("INSERT OR IGNORE INTO evidence VALUES(?,?,?,?,?,?,?)", (
            ev.get("id"), ev.get("representation_hash", ""), ev.get("sensitivity", "private"),
            ev.get("retention", "session"), ev.get("access", "meta"),
            ev.get("location", ""), ev.get("expires_at"),
        ))

    def upsert_episode(self, ep: dict) -> None:
        self._q("INSERT OR REPLACE INTO episodes VALUES(?,?,?,?,?,?)", (
            ep.get("id"), ep.get("sessionId"), ep.get("taskId"),
            ep.get("summary", ""), ep.get("state", "active"), ep.get("observations", 0),
        ))

    def disk_ok(self, extra: int = 0) -> bool:
        try:
            return os.path.getsize(self.path) + extra <= self.max_disk
        except OSError:
            return True

    def fetch(self, sql: str, args: tuple = ()) -> list:
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def close(self) -> None:
        with self.lock:
            self.db.commit()
            self.db.close()
