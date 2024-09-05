# pile.py

from enum import Enum
from typing import List
from card import Card

class PileType(Enum):
    FEEDER = "Feeder"
    SORTING = "Sorting"
    COLLECTION = "Collection"
    BLACKHOLE = "Blackhole"

class Pile:
    def __init__(self, x: int, y: int, x_index: int, y_index: int, max_cards: int, pile_type: PileType = PileType.SORTING):
        self.x = x
        self.y = y
        self.xIndex = x_index
        self.yIndex = y_index
        self.isFullyDiscovered = False
        self.max_cards = max_cards
        self.cards: List[Card] = []
        self.pile_type = pile_type

    def num_cards(self) -> int:
        return len(self.cards)
    
    def full(self) -> bool:
        return self.num_cards() >= self.max_cards

    def pick(self):
        if len(self.cards) < 1:
            raise
        return self.cards.pop()

    def place(self, card:Card):
        self.add_card(card)
    
    def is_empty(self):
        return len(self.cards) == 0
    
    def add_card(self, card):
        if isinstance(card, Card) and len(self.cards) < self.max_cards:
            self.cards.append(card)
    
    def remove_card(self) -> Card:
        if not self.is_empty():
            return self.cards.pop()
    
    def get_top_card(self) -> Card:
        if not self.is_empty():
            return self.cards[-1]
    
    def is_sorted(self):
        return all(self.cards[i] <= self.cards[i + 1] for i in range(len(self.cards) - 1))
