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
            return RecognitionResult(card_name=None, confidence=1.0)
        if self.catalog.get_card_meta(card_name) is None:
            return RecognitionResult(card_name=card_name, confidence=0.5)
        return RecognitionResult(card_name=card_name, confidence=1.0)
