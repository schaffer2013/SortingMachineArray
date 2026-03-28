from sorter.application.acceptance_envelope import evaluate_acceptance_envelope


def test_evaluate_acceptance_envelope_passes_for_current_baseline_shape():
    envelope = evaluate_acceptance_envelope(
        pytest_passed=True,
        sim_truth_summary={"name_accuracy": 1.0},
        fuzzy_greenfield_summary={"name_accuracy": 0.667},
        fuzzy_small_pool_summary={"name_accuracy": 0.833},
        fuzzy_golden_small_pool_summary={"name_accuracy": 0.833, "review_count": 0},
    )

    assert envelope.overall_passed is True
    assert all(gate.passed for gate in envelope.gates)


def test_evaluate_acceptance_envelope_fails_when_greenfield_drops_below_floor():
    envelope = evaluate_acceptance_envelope(
        pytest_passed=True,
        sim_truth_summary={"name_accuracy": 1.0},
        fuzzy_greenfield_summary={"name_accuracy": 0.2},
        fuzzy_small_pool_summary={"name_accuracy": 0.3},
        fuzzy_golden_small_pool_summary={"name_accuracy": 0.9, "review_count": 0},
    )

    failing = {gate.name for gate in envelope.gates if not gate.passed}

    assert envelope.overall_passed is False
    assert "fuzzy_greenfield_outperforms_legacy_floor" in failing
