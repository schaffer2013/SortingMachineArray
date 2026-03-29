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


def test_end_effector_radius_matches_dime_to_magic_card_ratio() -> None:
    ui = PygameDebugUI.__new__(PygameDebugUI)

    assert ui._end_effector_radius_px() == 10


def test_substate_label_humanizes_phase_and_active_command() -> None:
    run_state = SimpleNamespace(phase="VERIFYING", active_command="VacuumOn")
    snapshot = SimpleNamespace(run_state=run_state, pose=SimpleNamespace(x_mm=0.0, y_mm=0.0, z_mm=0.0))
    world = SimpleNamespace(snapshot=snapshot)
    orchestrator = SimpleNamespace(world=world)

    ui = PygameDebugUI.__new__(PygameDebugUI)
    any_ui = ui  # type: Any
    any_ui.orchestrator = orchestrator

    assert ui._substate_label() == "Verifying / pulling vac"


def test_camera_pose_applies_calibration_offset() -> None:
    ui = PygameDebugUI.__new__(PygameDebugUI)
    any_ui = ui  # type: Any
    any_ui.calibration = SimpleNamespace(camera_offset_x_mm=12.5, camera_offset_y_mm=-4.0)

    assert ui._camera_pose_mm(100.0, 80.0) == (112.5, 76.0)


def test_pile_reference_xy_prefers_calibrated_card_center() -> None:
    ui = PygameDebugUI.__new__(PygameDebugUI)
    any_ui = ui  # type: Any
    pile = SimpleNamespace(pile_id=SimpleNamespace(as_key=lambda: "1,0"), x_mm=200.0, y_mm=100.0)
    any_ui.orchestrator = SimpleNamespace(
        world=SimpleNamespace(snapshot=SimpleNamespace(piles={"1,0": pile}))
    )
    any_ui.calibration = SimpleNamespace(
        camera_offset_x_mm=12.5,
        camera_offset_y_mm=-4.0,
        pile_positions_mm=((240.0, 160.0),),
    )

    assert ui._pile_reference_xy(pile) == (240.0, 160.0)


def test_held_card_rect_stays_centered_on_picker_pose() -> None:
    ui = PygameDebugUI.__new__(PygameDebugUI)
    any_ui = ui  # type: Any
    any_ui.orchestrator = SimpleNamespace(world=SimpleNamespace(coords={}))
    layout = {"scale": 1.0}
    any_ui._card_size_px = lambda layout: (70, 98)
    any_ui._pose_to_screen = lambda x_mm, y_mm, layout: (300.0, 220.0)

    rect = ui._held_card_rect(100.0, 80.0, 1.0, layout)

    assert rect.center == (300, 220)


def test_pile_display_numbers_follow_physical_order() -> None:
    ui = PygameDebugUI.__new__(PygameDebugUI)
    piles = [
        SimpleNamespace(pile_id=SimpleNamespace(as_key=lambda: "0,1")),
        SimpleNamespace(pile_id=SimpleNamespace(as_key=lambda: "2,0")),
        SimpleNamespace(pile_id=SimpleNamespace(as_key=lambda: "5,9")),
    ]

    display_numbers = ui._pile_display_numbers(piles)

    assert display_numbers == {"0,1": 1, "2,0": 2, "5,9": 3}


def test_pile_badge_rect_is_centered_above_card() -> None:
    ui = PygameDebugUI.__new__(PygameDebugUI)
    any_ui = ui  # type: Any
    any_ui.font = SimpleNamespace(
        render=lambda text, antialias, color: SimpleNamespace(get_width=lambda: 80, get_height=lambda: 18)
    )
    pile = SimpleNamespace(pile_id=SimpleNamespace(as_key=lambda: "1,0"), role=SimpleNamespace(value="FEEDER"))
    rect = SimpleNamespace(centerx=300, top=220)

    badge_rect = ui._pile_badge_rect(pile, rect, {"1,0": 2})

    assert badge_rect.centerx == 300
    assert badge_rect.bottom == 210


def test_review_lines_explain_what_operator_should_check() -> None:
    ui = PygameDebugUI.__new__(PygameDebugUI)

    lines = ui._review_lines(
        {
            "review": {
                "pile_number": 1,
                "phase_label": "post-move verification",
                "attempts": 3,
                "recognized_name": "pooit",
                "confidence": 0.248,
                "action": "Check pile 1 camera view/top card, then rerun.",
            }
        }
    )

    assert lines[0] == "Review needed: Pile 1 post-move verification failed after 3 attempts."
    assert lines[1] == "Saw 'pooit' at confidence 0.248."
    assert lines[2] == "Check pile 1 camera view/top card, then rerun."


def test_recognizer_status_lines_show_configured_and_last_scan_backends() -> None:
    ui = PygameDebugUI.__new__(PygameDebugUI)
    any_ui = ui  # type: Any
    recognizer = SimpleNamespace(
        primary=SimpleNamespace(
            sorter_backend="fuzzy_enigma",
            card_engine_requested_backend="moss_machine",
            card_engine_backend_fallback=True,
            card_engine_mode="greenfield",
        ),
        fallback=SimpleNamespace(sorter_backend="sim_truth"),
    )
    any_ui.orchestrator = SimpleNamespace(
        recognizer=recognizer,
        last_recognition={
            "backend": "moss_machine",
            "effective_mode": "greenfield",
            "fallback_used": False,
        },
    )

    lines = ui._recognizer_status_lines()

    assert lines[0] == "Recognizer: fuzzy_enigma"
    assert lines[1] == "Card engine: requested=moss_machine mode=greenfield fallback=on"
    assert lines[2] == "Policy fallback: sim_truth"
    assert lines[3] == "Last scan: backend=moss_machine mode=greenfield"


def test_recognizer_status_lines_show_last_scan_fallback() -> None:
    ui = PygameDebugUI.__new__(PygameDebugUI)
    any_ui = ui  # type: Any
    any_ui.orchestrator = SimpleNamespace(
        recognizer=SimpleNamespace(sorter_backend="sim_truth"),
        last_recognition={
            "backend": "sim_truth",
            "requested_mode": "greenfield",
            "fallback_used": True,
        },
    )

    lines = ui._recognizer_status_lines()

    assert lines[0] == "Recognizer: sim_truth"
    assert lines[1] == "Last scan: backend=sim_truth mode=greenfield via fallback"
