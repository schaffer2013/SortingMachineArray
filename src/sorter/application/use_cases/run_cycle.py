from __future__ import annotations

from sorter.application.use_cases.plan_next_move import plan_next_move
from sorter.domain.machine_state import LegacyWorkflowState, NextMove


def run_cycle(workflow: LegacyWorkflowState, rank_lookup: dict[str, int]) -> NextMove | None:
    return plan_next_move(workflow, rank_lookup)
