from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import json

from sorter.config.calibration import CalibrationProfile
from sorter.domain.models import MachineSnapshot, PileId, PileState


@dataclass(frozen=True)
class SequenceStepDefinition:
    name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SequenceDefinition:
    name: str
    version: int
    steps: tuple[SequenceStepDefinition, ...]

    @staticmethod
    def from_file(path: Path) -> "SequenceDefinition":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return SequenceDefinition(
            name=str(payload["name"]),
            version=int(payload["version"]),
            steps=tuple(
                SequenceStepDefinition(name=str(step["name"]), params=dict(step.get("params", {})))
                for step in payload["steps"]
            ),
        )


@dataclass
class SequenceExecutionContext:
    snapshot: MachineSnapshot
    calibration: CalibrationProfile
    state: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, step_name: str, output: dict[str, Any]) -> dict[str, Any]:
        self.events.append({"step": step_name, "output": output})
        self.state[step_name] = output
        return output


SequenceStepHandler = Callable[[SequenceExecutionContext, dict[str, Any]], dict[str, Any]]


class SequenceRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, SequenceStepHandler] = {}

    def register(self, name: str) -> Callable[[SequenceStepHandler], SequenceStepHandler]:
        def decorator(handler: SequenceStepHandler) -> SequenceStepHandler:
            self._handlers[name] = handler
            return handler

        return decorator

    def get(self, name: str) -> SequenceStepHandler:
        if name not in self._handlers:
            raise KeyError(f"Unknown sequence step: {name}")
        return self._handlers[name]


class SequenceExecutor:
    def __init__(self, registry: SequenceRegistry):
        self.registry = registry

    def execute(self, definition: SequenceDefinition, context: SequenceExecutionContext) -> SequenceExecutionContext:
        context.state["sequence"] = {"name": definition.name, "version": definition.version}
        for step in definition.steps:
            handler = self.registry.get(step.name)
            output = handler(context, step.params)
            context.record(step.name, output)
        return context


def build_default_registry() -> SequenceRegistry:
    registry = SequenceRegistry()

    @registry.register("split_piles")
    def split_piles(context: SequenceExecutionContext, params: dict[str, Any]) -> dict[str, Any]:
        unregistered_label = str(params.get("unregistered_label", "unregistered"))
        registered_label = str(params.get("registered_label", "registered"))
        piles = _ordered_piles(context.snapshot)
        midpoint = len(piles) // 2
        assignments = {
            unregistered_label: [pile.pile_id.as_key() for pile in piles[:midpoint]],
            registered_label: [pile.pile_id.as_key() for pile in piles[midpoint:]],
        }
        context.state["pile_groups"] = assignments
        return {"groups": assignments}

    @registry.register("scan_piles")
    def scan_piles(context: SequenceExecutionContext, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "occupancy": {
                pile.pile_id.as_key(): not pile.is_empty()
                for pile in _ordered_piles(context.snapshot)
            }
        }

    @registry.register("probe_piles")
    def probe_piles(context: SequenceExecutionContext, params: dict[str, Any]) -> dict[str, Any]:
        card_height_mm = float(params.get("card_height_mm", 0.31))
        return {
            "heights_mm": {
                pile.pile_id.as_key(): round(pile.num_cards() * card_height_mm, 3)
                for pile in _ordered_piles(context.snapshot)
            }
        }

    @registry.register("plan_rebalance")
    def plan_rebalance(context: SequenceExecutionContext, params: dict[str, Any]) -> dict[str, Any]:
        source_group = str(params["source_group"])
        target_group = str(params["target_group"])
        max_cards_per_pile = int(params["max_cards_per_pile"])
        groups = context.state["pile_groups"]
        source_keys = groups[source_group]
        target_keys = groups[target_group]
        total_cards = sum(context.snapshot.piles[key].num_cards() for key in source_keys + target_keys)
        target_counts = _balanced_counts(total_cards, len(target_keys), max_cards_per_pile)
        return {
            "source_group": source_group,
            "target_group": target_group,
            "max_cards_per_pile": max_cards_per_pile,
            "target_counts": dict(zip(target_keys, target_counts, strict=True)),
        }

    @registry.register("plan_registration_pass")
    def plan_registration_pass(context: SequenceExecutionContext, params: dict[str, Any]) -> dict[str, Any]:
        from_group = str(params["from_group"])
        to_group = str(params["to_group"])
        groups = context.state["pile_groups"]
        from_keys = groups[from_group]
        to_keys = groups[to_group]
        total_cards = sum(context.snapshot.piles[key].num_cards() for key in from_keys)
        target_counts = _balanced_counts(total_cards, len(to_keys), None)
        return {
            "from_group": from_group,
            "to_group": to_group,
            "cards_to_process": total_cards,
            "destination_target_counts": dict(zip(to_keys, target_counts, strict=True)),
            "per_card_steps": [
                "image_top_card",
                "optional_max_accuracy_recognition",
                "move_card",
                "submit_registration_job_async",
            ],
        }

    return registry


def _ordered_piles(snapshot: MachineSnapshot) -> list[PileState]:
    return sorted(snapshot.piles.values(), key=lambda pile: (pile.y_mm, pile.x_mm, pile.pile_id.as_key()))


def _balanced_counts(total_cards: int, pile_count: int, max_cards_per_pile: int | None) -> list[int]:
    if pile_count <= 0:
        raise ValueError("pile_count must be positive")
    base, remainder = divmod(total_cards, pile_count)
    counts = [base + (1 if index < remainder else 0) for index in range(pile_count)]
    if max_cards_per_pile is not None and any(count > max_cards_per_pile for count in counts):
        raise ValueError("target piles cannot hold cards below configured max_cards_per_pile")
    return counts
