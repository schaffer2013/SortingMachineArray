from __future__ import annotations

from pathlib import Path
import json
import random


def load_scenario(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def distribute_cards_to_piles(
    card_ids: list[str],
    num_piles: int,
    num_empty_piles: int = 0,
    seed: int = 42,
) -> list[list[str]]:
    if num_piles <= 0:
        raise ValueError("num_piles must be > 0")
    if num_empty_piles < 0 or num_empty_piles >= num_piles:
        raise ValueError("num_empty_piles must be in [0, num_piles)")

    rng = random.Random(seed)
    shuffled = list(card_ids)
    rng.shuffle(shuffled)

    empty_indices = set(rng.sample(range(num_piles), num_empty_piles))
    piles = [[] for _ in range(num_piles)]
    non_empty = [index for index in range(num_piles) if index not in empty_indices]

    for index, card_id in enumerate(shuffled):
        pile_index = non_empty[index % len(non_empty)]
        piles[pile_index].append(card_id)
    return piles


def write_scenario_fixture(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
