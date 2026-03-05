from __future__ import annotations

from pathlib import Path
import json
import sqlite3
from datetime import datetime, UTC

from sorter.domain.events import DomainEvent
from sorter.domain.models import MachineSnapshot


DDL = [
    """
    CREATE TABLE IF NOT EXISTS runs (
      run_id TEXT PRIMARY KEY,
      mode TEXT NOT NULL,
      scenario_name TEXT,
      status TEXT NOT NULL,
      started_at TEXT NOT NULL,
      finished_at TEXT,
      config_snapshot_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT NOT NULL,
      seq INTEGER NOT NULL,
      ts TEXT NOT NULL,
      event_type TEXT NOT NULL,
      payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pile_snapshots (
      run_id TEXT NOT NULL,
      seq INTEGER NOT NULL,
      pile_id TEXT NOT NULL,
      role TEXT NOT NULL,
      discovered INTEGER NOT NULL,
      card_stack_json TEXT NOT NULL,
      PRIMARY KEY (run_id, seq, pile_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS frames (
      frame_id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL,
      seq INTEGER NOT NULL,
      pile_id TEXT,
      path TEXT,
      recognized_name TEXT,
      confidence REAL
    )
    """,
]


class SQLiteRunStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            for statement in DDL:
                conn.execute(statement)
            conn.commit()

    def start_run(self, run_id: str, mode: str, scenario_name: str | None, config_snapshot: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs(run_id, mode, scenario_name, status, started_at, config_snapshot_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    mode,
                    scenario_name,
                    "RUNNING",
                    datetime.now(UTC).isoformat(),
                    json.dumps(config_snapshot),
                ),
            )
            conn.commit()

    def append_event(self, run_id: str, seq: int, event: DomainEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events(run_id, seq, ts, event_type, payload_json) VALUES (?, ?, ?, ?, ?)",
                (run_id, seq, event.ts, event.event_type, json.dumps(event.payload)),
            )
            conn.commit()

    def save_snapshot(self, run_id: str, seq: int, snapshot: MachineSnapshot) -> None:
        with self._connect() as conn:
            for key, pile in snapshot.piles.items():
                conn.execute(
                    "INSERT OR REPLACE INTO pile_snapshots(run_id, seq, pile_id, role, discovered, card_stack_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (run_id, seq, key, pile.role.value, int(pile.discovered), json.dumps(pile.card_stack)),
                )
            conn.commit()

    def save_frame(self, run_id: str, seq: int, frame_id: str, path: str | None, pile_key: str | None, recognized_name: str | None, confidence: float | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO frames(frame_id, run_id, seq, pile_id, path, recognized_name, confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (frame_id, run_id, seq, pile_key, path, recognized_name, confidence),
            )
            conn.commit()

    def finish_run(self, run_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ?",
                (status, datetime.now(UTC).isoformat(), run_id),
            )
            conn.commit()
