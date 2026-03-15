from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import random
from uuid import uuid4

from sorter.domain.ranking_service import CompiledRanking
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
    hidden_piles: dict[str, list[str]]
    card_by_id: dict[str, CardMeta]
    image_by_card_id: dict[str, str | None]
    coords: dict[str, tuple[float, float]]
    compiled_ranking: CompiledRanking | None = None
    held_card_id: str | None = None

    @staticmethod
    def from_fixture(path: Path, override_seed: int | None = None) -> "SimWorld":
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        seed = int(override_seed if override_seed is not None else data.get("seed", 42))
        random.seed(seed)
        piles: dict[str, PileState] = {}
        hidden_piles: dict[str, list[str]] = {}
        card_by_id: dict[str, CardMeta] = {}
        image_by_card_id: dict[str, str | None] = {}
        coords: dict[str, tuple[float, float]] = {}
        project_root = path.parents[2]
        card_set_by_instance_id_raw = data.get("card_set_by_instance_id", {})
        card_set_by_instance_id = {
            str(card_id): str(set_id).strip().lower()
            for card_id, set_id in card_set_by_instance_id_raw.items()
            if isinstance(card_id, str) and isinstance(set_id, str) and set_id.strip()
        }

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
            hidden_stack: list[str] = []
            for raw_card in pile_cfg.get("cards", []):
                if "#" in raw_card:
                    base, instance = raw_card.split("#", 1)
                    card_id = f"{base}#{instance}"
                else:
                    card_id = f"{raw_card}#{uuid4().hex[:6]}"
                hidden_stack.append(card_id)
                card_name = base if "#" in raw_card else raw_card
                card_by_id[card_id] = CardMeta(name=card_name)
                image_by_card_id[card_id] = _resolve_image_for_name(
                    card_name,
                    project_root,
                    set_id=card_set_by_instance_id.get(card_id),
                )
            hidden_piles[key] = list(hidden_stack)
            pile = PileState(
                pile_id=pile_id,
                role=role,
                capacity=int(pile_cfg.get("capacity", 85)),
                x_mm=coords[key][0],
                y_mm=coords[key][1],
                card_stack=[],
                discovered=False,
                stack_count_known=False,
            )
            piles[key] = pile

        snapshot = MachineSnapshot(piles=piles, pose=MachinePose(), run_state=RunState(phase="IDLE"))
        return SimWorld(
            scenario_name=data.get("name", path.stem),
            seed=seed,
            snapshot=snapshot,
            hidden_piles=hidden_piles,
            card_by_id=card_by_id,
            image_by_card_id=image_by_card_id,
            coords=coords,
        )

    def rank_lookup(self) -> dict[str, int]:
        if self.compiled_ranking is None:
            raise RuntimeError("SimWorld rank lookup requested before compiled ranking was injected")
        return self.compiled_ranking.card_id_to_rank

    def set_compiled_ranking(self, compiled_ranking: CompiledRanking) -> None:
        self.compiled_ranking = compiled_ranking

    def explain_card(self, card_id_or_name: str) -> dict | None:
        if self.compiled_ranking is None:
            return None
        explanation = self.compiled_ranking.explain_card(card_id_or_name)
        if explanation is None:
            return None
        return {
            "card_id": explanation.card_id,
            "card_name": explanation.card_name,
            "factual_fields": explanation.factual_fields,
            "derived_fields": explanation.derived_fields,
            "sort_key": explanation.sort_key,
            "ordinal_rank": explanation.ordinal_rank,
        }

    def move_to_pile(self, pile_id: PileId) -> None:
        pile = self.snapshot.get_pile(pile_id)
        if pile is not None:
            x_mm, y_mm = pile.x_mm, pile.y_mm
        else:
            x_mm, y_mm = self.coords.get(pile_id.as_key(), (0.0, 0.0))
        self.snapshot.pose.x_mm = x_mm
        self.snapshot.pose.y_mm = y_mm

    def pick_from(self, pile_id: PileId) -> None:
        pile = self.snapshot.get_pile(pile_id)
        hidden_stack = self.hidden_piles.get(pile_id.as_key())
        if pile is None or hidden_stack is None or not hidden_stack:
            raise RuntimeError("Cannot pick from empty pile")
        self.held_card_id = hidden_stack.pop()
        if pile.card_stack and pile.card_stack[-1] == self.held_card_id:
            pile.card_stack.pop()
        next_top_id = hidden_stack[-1] if hidden_stack else None
        if next_top_id is None:
            pile.card_stack.clear()
            pile.mark_empty_confirmed(source="pick_reveal")
        else:
            if pile.has_known_count():
                pile.card_stack = list(hidden_stack)
            else:
                pile.card_stack = [next_top_id]
            pile.mark_top_card_seen(
                card_name=self.card_by_id[next_top_id].name,
                confidence=1.0,
                source="pick_reveal",
                count_known=pile.has_known_count(),
            )
        self.snapshot.pose.holding_card_id = self.held_card_id

    def place_to(self, pile_id: PileId) -> None:
        if self.held_card_id is None:
            raise RuntimeError("No held card to place")
        pile = self.snapshot.get_pile(pile_id)
        if pile is None:
            raise RuntimeError("Destination pile missing")
        hidden_stack = self.hidden_piles.get(pile_id.as_key())
        if hidden_stack is None:
            raise RuntimeError("Destination hidden pile missing")
        hidden_stack.append(self.held_card_id)
        if pile.has_known_count():
            pile.card_stack.append(self.held_card_id)
        else:
            pile.card_stack = [self.held_card_id]
        placed_card_name = self.card_by_id[self.held_card_id].name
        pile.mark_top_card_seen(
            card_name=placed_card_name,
            confidence=1.0,
            source="placement_assumption",
            count_known=pile.has_known_count(),
        )
        self.held_card_id = None
        self.snapshot.pose.holding_card_id = None

    def observe_top_card(
        self,
        pile_id: PileId,
        frame_id: str | None = None,
        source: str = "sim_camera",
    ) -> str | None:
        pile = self.snapshot.get_pile(pile_id)
        if pile is None:
            return None
        hidden_stack = self.hidden_piles.get(pile_id.as_key(), [])
        top_id = hidden_stack[-1] if hidden_stack else None
        if top_id is None:
            pile.card_stack.clear()
            pile.mark_empty_confirmed(source=source, frame_id=frame_id)
            return None
        if pile.has_known_count():
            pile.card_stack = list(hidden_stack)
        else:
            pile.card_stack = [top_id]
        card_name = self.card_by_id[top_id].name
        pile.mark_top_card_seen(
            card_name=card_name,
            confidence=1.0,
            source=source,
            frame_id=frame_id,
            count_known=pile.has_known_count(),
        )
        return card_name

    def top_card_name(self, pile_id: PileId) -> str | None:
        return self.observe_top_card(pile_id)

    def top_card_image_path(self, pile_id: PileId) -> str | None:
        pile = self.snapshot.get_pile(pile_id)
        if pile is None:
            return None
        top_id = pile.top_card_id()
        if top_id is None:
            return None
        return self.image_by_card_id.get(top_id)
def _resolve_image_for_name(card_name: str, project_root: Path, set_id: str | None = None) -> str | None:
    image_dirs = [
        project_root / "SimulatedCardImages",
        project_root / "data" / "card_catalog" / "images",
    ]
    preferred_subdirs = [set_id.lower()] if set_id else ["default", ""]
    variants = [
        card_name,
        card_name.replace(" ", "_"),
        card_name.replace("/", "_"),
        card_name.replace(" ", "_").replace("/", "_"),
    ]

    for directory in image_dirs:
        if not directory.exists():
            continue
        for subdir in preferred_subdirs:
            scoped_dir = directory / subdir if subdir else directory
            if not scoped_dir.exists():
                continue
            for variant in variants:
                candidate = scoped_dir / f"{variant}.jpg"
                if candidate.exists():
                    return str(candidate)
                candidate_png = scoped_dir / f"{variant}.png"
                if candidate_png.exists():
                    return str(candidate_png)

    target = _normalize_name(card_name)
    for directory in image_dirs:
        if not directory.exists():
            continue
        if set_id:
            for subdir in preferred_subdirs:
                scoped_dir = directory / subdir if subdir else directory
                if not scoped_dir.exists():
                    continue
                for file_path in scoped_dir.iterdir():
                    if not file_path.is_file():
                        continue
                    if file_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                        continue
                    if _normalize_name(file_path.stem) == target:
                        return str(file_path)
            continue

        # No explicit set: allow any set folder match as fallback.
        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            if _normalize_name(file_path.stem) == target:
                return str(file_path)

    return None


def _normalize_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())
