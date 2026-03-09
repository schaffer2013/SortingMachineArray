from __future__ import annotations

from pathlib import Path
import json

from sorter.adapters.sim.sim_world import SimWorld
from sorter.domain.models import PileId


def test_sim_world_resolves_set_specific_image_then_default(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    fixture_path = project_root / "scenarios" / "fixtures" / "small_stack.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)

    simulated_dir = project_root / "SimulatedCardImages"
    (simulated_dir / "6ed").mkdir(parents=True, exist_ok=True)
    (simulated_dir / "lea").mkdir(parents=True, exist_ok=True)
    (simulated_dir / "6ed" / "Lightning_Bolt.jpg").write_bytes(b"set")
    (simulated_dir / "lea" / "Counterspell.jpg").write_bytes(b"fallback-any-set")

    fixture = {
        "name": "set_images",
        "seed": 42,
        "grid": {"cols": 1, "rows": 1},
        "card_set_by_instance_id": {"Lightning Bolt#s1": "6ed"},
        "piles": [
            {
                "pile_id": {"x_index": 0, "y_index": 0},
                "role": "FEEDER",
                "cards": ["Counterspell#d1", "Lightning Bolt#s1"],
            }
        ],
    }
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    world = SimWorld.from_fixture(fixture_path)
    pile_id = PileId(x_index=0, y_index=0)

    top_image = world.top_card_image_path(pile_id)
    assert top_image is not None
    assert "SimulatedCardImages" in top_image
    assert "6ed" in top_image.lower()

    world.pick_from(pile_id)
    next_image = world.top_card_image_path(pile_id)
    assert next_image is not None
    assert "SimulatedCardImages" in next_image
    assert "lea" in next_image.lower()
