from __future__ import annotations

from pathlib import Path
import json
import sqlite3
from datetime import datetime, UTC

from sorter.domain.events import DomainEvent
from sorter.domain.models import MachineSnapshot
from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult


DDL = [
    """
    CREATE TABLE IF NOT EXISTS runs (
      run_id TEXT PRIMARY KEY,
      mode TEXT NOT NULL,
      scenario_name TEXT,
      status TEXT NOT NULL,
      started_at TEXT NOT NULL,
      finished_at TEXT,
      config_snapshot_json TEXT NOT NULL,
      result_metrics_json TEXT
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
      captured_at_utc TEXT,
      camera_id TEXT,
      source_mode TEXT,
      metadata_json TEXT,
      recognized_name TEXT,
      confidence REAL,
      recognizer_backend TEXT,
      scryfall_id TEXT,
      oracle_id TEXT,
      requested_mode TEXT,
      effective_mode TEXT,
      mode_flags_json TEXT,
      mode_features_json TEXT,
      pipeline_summary_json TEXT,
      failure_code TEXT,
      review_reason TEXT,
      needs_review INTEGER,
      fallback_used INTEGER,
      alternatives_json TEXT,
      debug_json TEXT
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
            self._ensure_run_columns(conn)
            self._ensure_frame_columns(conn)
            conn.commit()

    def _ensure_run_columns(self, conn: sqlite3.Connection) -> None:
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        migrations = {
            "result_metrics_json": "ALTER TABLE runs ADD COLUMN result_metrics_json TEXT",
        }
        for column, statement in migrations.items():
            if column not in existing:
                conn.execute(statement)

    def _ensure_frame_columns(self, conn: sqlite3.Connection) -> None:
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(frames)").fetchall()
        }
        migrations = {
            "captured_at_utc": "ALTER TABLE frames ADD COLUMN captured_at_utc TEXT",
            "camera_id": "ALTER TABLE frames ADD COLUMN camera_id TEXT",
            "source_mode": "ALTER TABLE frames ADD COLUMN source_mode TEXT",
            "metadata_json": "ALTER TABLE frames ADD COLUMN metadata_json TEXT",
            "recognizer_backend": "ALTER TABLE frames ADD COLUMN recognizer_backend TEXT",
            "scryfall_id": "ALTER TABLE frames ADD COLUMN scryfall_id TEXT",
            "oracle_id": "ALTER TABLE frames ADD COLUMN oracle_id TEXT",
            "requested_mode": "ALTER TABLE frames ADD COLUMN requested_mode TEXT",
            "effective_mode": "ALTER TABLE frames ADD COLUMN effective_mode TEXT",
            "mode_flags_json": "ALTER TABLE frames ADD COLUMN mode_flags_json TEXT",
            "mode_features_json": "ALTER TABLE frames ADD COLUMN mode_features_json TEXT",
            "pipeline_summary_json": "ALTER TABLE frames ADD COLUMN pipeline_summary_json TEXT",
            "failure_code": "ALTER TABLE frames ADD COLUMN failure_code TEXT",
            "review_reason": "ALTER TABLE frames ADD COLUMN review_reason TEXT",
            "needs_review": "ALTER TABLE frames ADD COLUMN needs_review INTEGER",
            "fallback_used": "ALTER TABLE frames ADD COLUMN fallback_used INTEGER",
            "alternatives_json": "ALTER TABLE frames ADD COLUMN alternatives_json TEXT",
            "debug_json": "ALTER TABLE frames ADD COLUMN debug_json TEXT",
        }
        for column, statement in migrations.items():
            if column not in existing:
                conn.execute(statement)

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

    def save_frame(self, run_id: str, seq: int, frame: Frame, recognition: RecognitionResult | None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO frames(
                    frame_id,
                    run_id,
                    seq,
                    pile_id,
                    path,
                    captured_at_utc,
                    camera_id,
                    source_mode,
                    metadata_json,
                    recognized_name,
                    confidence,
                    recognizer_backend,
                    scryfall_id,
                    oracle_id,
                    requested_mode,
                    effective_mode,
                    mode_flags_json,
                    mode_features_json,
                    pipeline_summary_json,
                    failure_code,
                    review_reason,
                    needs_review,
                    fallback_used,
                    alternatives_json,
                    debug_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    frame.frame_id,
                    run_id,
                    seq,
                    frame.pile_id.as_key() if frame.pile_id is not None else None,
                    frame.path,
                    frame.captured_at_utc,
                    frame.camera_id,
                    frame.source_mode,
                    json.dumps(frame.metadata),
                    recognition.card_name if recognition is not None else None,
                    recognition.confidence if recognition is not None else None,
                    recognition.backend if recognition is not None else None,
                    recognition.scryfall_id if recognition is not None else None,
                    recognition.oracle_id if recognition is not None else None,
                    recognition.requested_mode if recognition is not None else None,
                    recognition.effective_mode if recognition is not None else None,
                    json.dumps(recognition.mode_flags) if recognition is not None else None,
                    json.dumps(list(recognition.mode_features)) if recognition is not None else None,
                    json.dumps(recognition.pipeline_summary) if recognition is not None else None,
                    recognition.failure_code if recognition is not None else None,
                    recognition.review_reason if recognition is not None else None,
                    int(recognition.needs_review) if recognition is not None else None,
                    int(recognition.fallback_used) if recognition is not None else None,
                    json.dumps(list(recognition.alternatives)) if recognition is not None else None,
                    json.dumps(recognition.debug) if recognition is not None else None,
                ),
            )
            conn.commit()

    def finish_run(self, run_id: str, status: str, metrics: dict | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, finished_at = ?, result_metrics_json = ? WHERE run_id = ?",
                (
                    status,
                    datetime.now(UTC).isoformat(),
                    json.dumps(metrics) if metrics is not None else None,
                    run_id,
                ),
            )
            conn.commit()
