from __future__ import annotations

from sorter.adapters.sim.sim_world import SimWorld
from sorter.ports.card_catalog import CardCatalogPort
from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult


class SimRecognizerAdapter:
    def __init__(self, world: SimWorld, catalog: CardCatalogPort):
        self.world = world
        self.catalog = catalog

    def recognize_top_card(self, frame: Frame) -> RecognitionResult:
        card_name = frame.metadata.get("card_name")
        if card_name is None:
            return RecognitionResult(
                card_name=None,
                confidence=1.0,
                backend="sim_truth",
                requested_mode="sim_truth",
                effective_mode="sim_truth",
                mode_features=("perfect_truth",),
            )
        # In simulation we already know the rendered card identity, so do not
        # fault runs when catalog metadata is incomplete.
        return RecognitionResult(
            card_name=card_name,
            confidence=1.0,
            backend="sim_truth",
            scryfall_id=frame.metadata.get("scryfall_id"),
            oracle_id=frame.metadata.get("oracle_id"),
            requested_mode="sim_truth",
            effective_mode="sim_truth",
            mode_features=("perfect_truth",),
        )
