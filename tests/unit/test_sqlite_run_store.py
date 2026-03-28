from __future__ import annotations

import sqlite3

from sorter.adapters.persistence.sqlite_run_store import SQLiteRunStore
from sorter.domain.models import PileId
from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult


def test_sqlite_run_store_persists_rich_frame_and_recognition_fields(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite3")
    frame = Frame(
        frame_id="frame-1",
        path="C:/tmp/card.jpg",
        pile_id=PileId(0, 0),
        metadata={"card_name": "Opt"},
        captured_at_utc="2026-03-27T12:00:00+00:00",
        camera_id="sim_topdown",
        source_mode="sim",
    )
    recognition = RecognitionResult(
        card_name="Opt",
        confidence=0.91,
        backend="fuzzy_enigma",
        scryfall_id="opt-id",
        oracle_id="oracle-opt",
        needs_review=False,
        fallback_used=False,
        alternatives=({"name": "Opt", "score": 0.91},),
        debug={"active_roi": "standard"},
    )

    store.start_run("run-1", mode="sim", scenario_name="demo", config_snapshot={"seed": 42})
    store.save_frame("run-1", 1, frame, recognition)

    with sqlite3.connect(store.db_path) as conn:
        store.finish_run("run-1", "COMPLETED", metrics={"scan_count": 3, "retry_count": 1})
        row = conn.execute(
            """
            SELECT
                pile_id,
                path,
                captured_at_utc,
                camera_id,
                source_mode,
                recognized_name,
                confidence,
                recognizer_backend,
                scryfall_id,
                oracle_id,
                needs_review,
                fallback_used
            FROM frames
            WHERE frame_id = 'frame-1'
            """
        ).fetchone()
        metrics_row = conn.execute(
            "SELECT result_metrics_json FROM runs WHERE run_id = 'run-1'"
        ).fetchone()

    assert row == (
        "0,0",
        "C:/tmp/card.jpg",
        "2026-03-27T12:00:00+00:00",
        "sim_topdown",
        "sim",
        "Opt",
        0.91,
        "fuzzy_enigma",
        "opt-id",
        "oracle-opt",
        0,
        0,
    )
    assert metrics_row == ('{"scan_count": 3, "retry_count": 1}',)
