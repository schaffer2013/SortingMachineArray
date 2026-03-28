from __future__ import annotations

from pathlib import Path
import json
import random
import tempfile

from sorter.adapters.persistence.sim_card_list_loader import (
    DEFAULT_SIM_CARD_LIST_PAYLOAD,
    build_default_sim_card_list_payload,
    expand_and_shuffle_instances,
    expand_and_shuffle_instance_ids,
    load_catalog_image_candidates,
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
    assert raw["entries"]


def test_load_catalog_image_candidates_reads_available_catalog_entries(tmp_path: Path) -> None:
    catalog_path = tmp_path / "cards.json"
    catalog_path.write_text(
        json.dumps(
            {
                "cards": [
                    {"name": "Alpha", "images": ["SimulatedCardImages/lea/Alpha.jpg"]},
                    {"name": "Beta", "images": ["SimulatedCardImages/Beta.jpg"]},
                    {"name": "Gamma", "images": []},
                ]
            }
        ),
        encoding="utf-8",
    )

    candidates = load_catalog_image_candidates(catalog_path)

    assert [(candidate.name, candidate.set_id) for candidate in candidates] == [
        ("Alpha", "lea"),
        ("Beta", None),
    ]


def test_build_default_sim_card_list_payload_uses_local_catalog_candidates(tmp_path: Path) -> None:
    catalog_path = tmp_path / "cards.json"
    catalog_path.write_text(
        json.dumps(
            {
                "cards": [
                    {"name": "Alpha", "images": ["SimulatedCardImages/lea/Alpha.jpg"]},
                    {"name": "Beta", "images": ["SimulatedCardImages/leb/Beta.jpg"]},
                    {"name": "Gamma", "images": ["SimulatedCardImages/Gamma.jpg"]},
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = build_default_sim_card_list_payload(catalog_path=catalog_path, desired_entry_count=2, random_seed=7)

    assert payload["list_name"] == "default_demo_cards"
    assert payload["entries"]
    assert len(payload["entries"]) == 2
    assert all(entry["count"] == 1 for entry in payload["entries"])


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


def test_expansion_prefers_supplied_scryfall_id_style_suffixes() -> None:
    config_payload = {
        "version": 1,
        "list_name": "scryfall ids",
        "description": "scryfall ids",
        "random_seed": 42,
        "shuffle": False,
        "entries": [
            {"name": "Alpha Adept", "count": 1},
            {"name": "Beta Burst", "count": 1},
        ],
    }
    config = load_sim_card_list_from_payload(config_payload)

    expanded = expand_and_shuffle_instance_ids(
        config,
        id_suffix_by_name={
            "Alpha Adept": "c1a2b3c4-d5e6-7890-abcd-ef1234567890",
            "Beta Burst": "11111111-2222-3333-4444-555555555555",
        },
    )

    assert expanded == [
        "Alpha Adept#c1a2b3c4-d5e6-7890-abcd-ef1234567890",
        "Beta Burst#11111111-2222-3333-4444-555555555555",
    ]


def test_sim_card_list_parses_set_aliases() -> None:
    config_payload = {
        "version": 1,
        "list_name": "set aliases",
        "description": "set parsing",
        "random_seed": 42,
        "shuffle": False,
        "entries": [
            {"name": "Alpha Adept", "set": "6ED", "count": 1},
            {"name": "Beta Burst", "setId": "lea", "count": 1},
            {"name": "Gamma Grove", "count": 1},
        ],
    }

    config = load_sim_card_list_from_payload(config_payload)

    assert config.entries[0].set_id == "6ed"
    assert config.entries[1].set_id == "lea"
    assert config.entries[2].set_id is None


def test_expand_instances_keeps_set_id_metadata() -> None:
    config_payload = {
        "version": 1,
        "list_name": "set expansion",
        "description": "set parsing",
        "random_seed": 42,
        "shuffle": False,
        "entries": [
            {"name": "Alpha Adept", "set": "6ED", "count": 2},
            {"name": "Beta Burst", "count": 1},
        ],
    }
    config = load_sim_card_list_from_payload(config_payload)

    expanded = expand_and_shuffle_instances(config)

    assert [entry.card_id for entry in expanded] == [
        "Alpha Adept#alphaadept",
        "Alpha Adept#alphaadept",
        "Beta Burst#betaburst",
    ]
    assert [entry.set_id for entry in expanded] == ["6ed", "6ed", None]


def load_sim_card_list_from_payload(payload: dict):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        handle.write(json.dumps(payload))
        path = Path(handle.name)
    try:
        return load_sim_card_list(path)
    finally:
        if path.exists():
            path.unlink()
