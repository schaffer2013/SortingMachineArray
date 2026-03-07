from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import random


DEFAULT_SIM_CARD_LIST_PAYLOAD = {
    "version": 1,
    "list_name": "default_demo_cards",
    "description": "Seeded demo list for sim visuals",
    "random_seed": 42,
    "shuffle": True,
    "entries": [
        {"name": "Lightning Bolt", "count": 4},
        {"name": "Counterspell", "count": 4},
        {"name": "Llanowar Elves", "count": 4},
        {"name": "Doom Blade", "count": 4},
        {"name": "Pacifism", "count": 4},
        {"name": "Arcane Signet", "count": 4},
        {"name": "Evolving Wilds", "count": 4},
        {"name": "Island", "count": 8},
        {"name": "Mountain", "count": 8},
    ],
}


@dataclass(frozen=True)
class SimCardListEntry:
    name: str
    count: int


@dataclass(frozen=True)
class SimCardListConfig:
    version: int
    list_name: str
    description: str
    random_seed: int
    shuffle: bool
    entries: list[SimCardListEntry]


def ensure_sim_card_list_file(path: Path) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_SIM_CARD_LIST_PAYLOAD, indent=2) + "\n", encoding="utf-8")
    return path


def load_sim_card_list(path: Path) -> SimCardListConfig:
    ensure_sim_card_list_file(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return _validate_and_parse(data)


def expand_and_shuffle_instance_ids(config: SimCardListConfig) -> list[str]:
    expanded: list[str] = []
    for entry in config.entries:
        for index in range(1, entry.count + 1):
            expanded.append(f"{entry.name}#{index}")

    if config.shuffle:
        rng = random.Random(config.random_seed)
        rng.shuffle(expanded)
    return expanded


def load_expand_shuffle_instance_ids(path: Path) -> tuple[SimCardListConfig, list[str]]:
    config = load_sim_card_list(path)
    return config, expand_and_shuffle_instance_ids(config)


def _validate_and_parse(data: dict) -> SimCardListConfig:
    if not isinstance(data, dict):
        raise ValueError("Sim card list must be a JSON object")

    version = _require_int(data, "version")
    list_name = _require_non_empty_str(data, "list_name")
    description = _require_str(data, "description")
    random_seed = _require_int(data, "random_seed")
    shuffle = _require_bool(data, "shuffle")

    entries_raw = data.get("entries")
    if not isinstance(entries_raw, list) or not entries_raw:
        raise ValueError("Sim card list 'entries' must be a non-empty list")

    entries: list[SimCardListEntry] = []
    for index, entry in enumerate(entries_raw, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Sim card list entry {index} must be an object")
        name = _require_non_empty_str(entry, "name")
        count = _require_int(entry, "count")
        if count <= 0:
            raise ValueError(f"Sim card list entry {index} count must be > 0")
        entries.append(SimCardListEntry(name=name, count=count))

    return SimCardListConfig(
        version=version,
        list_name=list_name,
        description=description,
        random_seed=random_seed,
        shuffle=shuffle,
        entries=entries,
    )


def _require_str(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Sim card list field '{key}' must be a string")
    return value


def _require_non_empty_str(payload: dict, key: str) -> str:
    value = _require_str(payload, key).strip()
    if not value:
        raise ValueError(f"Sim card list field '{key}' must not be empty")
    return value


def _require_int(payload: dict, key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Sim card list field '{key}' must be an integer")
    return value


def _require_bool(payload: dict, key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"Sim card list field '{key}' must be a boolean")
    return value
