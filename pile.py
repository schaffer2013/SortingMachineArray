# pile.py

from card import Card

class Pile:
    def __init__(self, x, y, x_index, y_index, max_cards):
        self.x = x
        self.y = y
        self.xIndex = x_index
        self.yIndex = y_index
        self.max_cards = max_cards
        self.cards = []
    
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
