from __future__ import annotations

from sorter.domain.machine_state import LegacyWorkflowState, NextMove


def plan_next_move(workflow: LegacyWorkflowState, rank_lookup: dict[str, int]) -> NextMove | None:
    return workflow.plan_next(rank_lookup)
