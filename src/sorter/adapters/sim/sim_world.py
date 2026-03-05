from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import random
from uuid import uuid4

from sorter.domain.models import (
    CardMeta,
    MachinePose,
    MachineSnapshot,
    PileId,
    PileState,
    RunState,
)
from sorter.domain.enums import PileRole


@dataclass
class SimWorld:
    scenario_name: str
    seed: int
    snapshot: MachineSnapshot
    card_by_id: dict[str, CardMeta]
    coords: dict[str, tuple[float, float]]
    held_card_id: str | None = None

    @staticmethod
    def from_fixture(path: Path, override_seed: int | None = None) -> "SimWorld":
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        seed = int(override_seed if override_seed is not None else data.get("seed", 42))
        random.seed(seed)
        piles: dict[str, PileState] = {}
        card_by_id: dict[str, CardMeta] = {}
        coords: dict[str, tuple[float, float]] = {}

        for pile_cfg in data.get("piles", []):
            pile_id = PileId(
                x_index=int(pile_cfg["pile_id"]["x_index"]),
                y_index=int(pile_cfg["pile_id"]["y_index"]),
            )
            key = pile_id.as_key()
            coords[key] = (
                float(pile_cfg.get("x_mm", pile_id.x_index * 100.0)),
                float(pile_cfg.get("y_mm", pile_id.y_index * 100.0)),
            )
            role = PileRole[pile_cfg.get("role", "SORTING")]
            stack: list[str] = []
            for raw_card in pile_cfg.get("cards", []):
                if "#" in raw_card:
                    base, instance = raw_card.split("#", 1)
                    card_id = f"{base}#{instance}"
                else:
                    card_id = f"{raw_card}#{uuid4().hex[:6]}"
                stack.append(card_id)
                card_by_id[card_id] = CardMeta(name=base if "#" in raw_card else raw_card)
            piles[key] = PileState(
                pile_id=pile_id,
                role=role,
                capacity=int(pile_cfg.get("capacity", 85)),
                card_stack=stack,
                discovered=bool(pile_cfg.get("discovered", role != PileRole.FEEDER)),
            )

        snapshot = MachineSnapshot(piles=piles, pose=MachinePose(), run_state=RunState(phase="IDLE"))
        return SimWorld(
            scenario_name=data.get("name", path.stem),
            seed=seed,
            snapshot=snapshot,
            card_by_id=card_by_id,
            coords=coords,
        )

    def rank_lookup(self) -> dict[str, int]:
        card_names = sorted({meta.name for meta in self.card_by_id.values()})
        rank_name = {name: idx + 1 for idx, name in enumerate(card_names)}
        return {card_id: rank_name[meta.name] for card_id, meta in self.card_by_id.items()}

    def move_to_pile(self, pile_id: PileId) -> None:
        x_mm, y_mm = self.coords.get(pile_id.as_key(), (0.0, 0.0))
        self.snapshot.pose.x_mm = x_mm
        self.snapshot.pose.y_mm = y_mm

    def pick_from(self, pile_id: PileId) -> None:
        pile = self.snapshot.get_pile(pile_id)
        if pile is None or pile.is_empty():
            raise RuntimeError("Cannot pick from empty pile")
        self.held_card_id = pile.card_stack.pop()
        self.snapshot.pose.holding_card_id = self.held_card_id

    def place_to(self, pile_id: PileId) -> None:
        if self.held_card_id is None:
            raise RuntimeError("No held card to place")
        pile = self.snapshot.get_pile(pile_id)
        if pile is None:
            raise RuntimeError("Destination pile missing")
        pile.card_stack.append(self.held_card_id)
        self.held_card_id = None
        self.snapshot.pose.holding_card_id = None

    def top_card_name(self, pile_id: PileId) -> str | None:
        pile = self.snapshot.get_pile(pile_id)
        if pile is None:
            return None
        top_id = pile.top_card_id()
        if top_id is None:
            pile.discovered = True
            return None
        return self.card_by_id[top_id].name
