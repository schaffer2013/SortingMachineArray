from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sorter.interfaces.pygame_debug import PygameDebugUI, PoseAnimationSegment


def test_pose_animation_state_updates_when_machine_pose_changes() -> None:
    pose = SimpleNamespace(x_mm=0.0, y_mm=0.0, z_mm=0.0, holding_card_id="Card#1", vacuum_on=True)
    snapshot = SimpleNamespace(pose=pose, piles={})
    world = SimpleNamespace(snapshot=snapshot, coords={"0,0": (0.0, 0.0)}, image_by_card_id={"Card#1": "held.jpg"})
    orchestrator = SimpleNamespace(world=world)

    ui = PygameDebugUI.__new__(PygameDebugUI)
    any_ui = ui  # type: Any
    any_ui.orchestrator = orchestrator
    any_ui.pose_anim = PoseAnimationSegment()
    any_ui.last_pose_target = (0.0, 0.0, 0.0)

    pose.x_mm = 150.0
    pose.y_mm = 75.0

    ui._update_animation_from_pose()

    assert ui.pose_anim.active is True
    assert ui.pose_anim.held_card_id == "Card#1"
    assert ui.pose_anim.end_x_mm == 150.0
    assert ui.pose_anim.end_y_mm == 75.0
