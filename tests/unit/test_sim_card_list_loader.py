from __future__ import annotations

from pathlib import Path
import json
import random
import tempfile

from sorter.adapters.persistence.sim_card_list_loader import (
    DEFAULT_SIM_CARD_LIST_PAYLOAD,
    expand_and_shuffle_instance_ids,
    load_expand_shuffle_instance_ids,
    load_sim_card_list,
)


def test_sim_card_list_file_is_created_when_missing(tmp_path: Path) -> None:
    card_list_path = tmp_path / "config" / "sim_card_lists" / "default_cards.json"

    config = load_sim_card_list(card_list_path)

    assert card_list_path.exists()
    assert config.random_seed == 42
    assert config.shuffle is True
    raw = json.loads(card_list_path.read_text(encoding="utf-8"))
    assert raw["list_name"] == DEFAULT_SIM_CARD_LIST_PAYLOAD["list_name"]


def test_expansion_and_shuffle_is_deterministic_with_seed_42(tmp_path: Path) -> None:
    payload = {
        "version": 1,
        "list_name": "seeded",
        "description": "seeded test",
        "random_seed": 42,
        "shuffle": True,
        "entries": [
            {"name": "Alpha", "count": 2},
            {"name": "Beta", "count": 2},
        ],
    }
    card_list_path = tmp_path / "cards.json"
    card_list_path.write_text(json.dumps(payload), encoding="utf-8")

    _, first = load_expand_shuffle_instance_ids(card_list_path)
    _, second = load_expand_shuffle_instance_ids(card_list_path)

    expected = ["Alpha#alpha", "Alpha#alpha", "Beta#beta", "Beta#beta"]
    random.Random(42).shuffle(expected)
    assert first == expected
    assert second == expected


def test_expansion_without_shuffle_preserves_order() -> None:
    config_payload = {
        "version": 1,
        "list_name": "ordered",
        "description": "ordered test",
        "random_seed": 42,
        "shuffle": False,
        "entries": [
            {"name": "Gamma", "count": 2},
            {"name": "Delta", "count": 1},
        ],
    }
    config = load_sim_card_list_from_payload(config_payload)

    expanded = expand_and_shuffle_instance_ids(config)

    assert expanded == ["Gamma#gamma", "Gamma#gamma", "Delta#delta"]


def test_expansion_uses_supplied_identity_suffix_map() -> None:
    config_payload = {
        "version": 1,
        "list_name": "oracle",
        "description": "oracle ids",
        "random_seed": 42,
        "shuffle": False,
        "entries": [
            {"name": "Gamma", "count": 2},
            {"name": "Delta", "count": 1},
        ],
    }
    config = load_sim_card_list_from_payload(config_payload)

    expanded = expand_and_shuffle_instance_ids(
        config,
        id_suffix_by_name={"Gamma": "oracle-gamma", "Delta": "oracle-delta"},
    )

    assert expanded == ["Gamma#oracle-gamma", "Gamma#oracle-gamma", "Delta#oracle-delta"]


def load_sim_card_list_from_payload(payload: dict):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        handle.write(json.dumps(payload))
        path = Path(handle.name)
    try:
        return load_sim_card_list(path)
    finally:
        if path.exists():
            path.unlink()
