from __future__ import annotations

import json

from sorter.application.recognition_compare import compare_recognition_summaries


def test_compare_recognition_summaries_reports_prediction_and_review_deltas(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(
        json.dumps(
            {
                "backend": "sim_truth",
                "scenario_name": "demo",
                "cases": [
                    {
                        "pile_key": "0,0",
                        "expected_name": "Opt",
                        "predicted_name": "Opt",
                        "confidence": 1.0,
                        "needs_review": False,
                    },
                    {
                        "pile_key": "1,0",
                        "expected_name": "Island",
                        "predicted_name": None,
                        "confidence": 0.0,
                        "needs_review": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    candidate_path.write_text(
        json.dumps(
            {
                "backend": "fuzzy_enigma",
                "scenario_name": "demo",
                "cases": [
                    {
                        "pile_key": "0,0",
                        "expected_name": "Opt",
                        "predicted_name": "Opt",
                        "confidence": 0.75,
                        "needs_review": False,
                    },
                    {
                        "pile_key": "1,0",
                        "expected_name": "Island",
                        "predicted_name": "Island",
                        "confidence": 0.8,
                        "needs_review": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = compare_recognition_summaries(baseline_path, candidate_path)

    assert summary.baseline_backend == "sim_truth"
    assert summary.candidate_backend == "fuzzy_enigma"
    assert summary.total_compared_cases == 2
    assert summary.changed_prediction_count == 1
    assert summary.candidate_review_reduction == 1
