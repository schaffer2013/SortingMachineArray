# pile.py

class Pile:
    def __init__(self, x, y, max_cards):
        self.x = x
        self.y = y
        self.max_cards = max_cards
        self.cards = []
    
    def is_empty(self):
        return len(self.cards) == 0
    
    def add_card(self, card):
        if len(self.cards) < self.max_cards:
            self.cards.append(card)
    
    def remove_card(self):
        if not self.is_empty():
            return self.cards.pop()
    
    def get_top_card(self):
        if not self.is_empty():
            return self.cards[-1]
    
    def is_sorted(self):
        return all(self.cards[i] <= self.cards[i + 1] for i in range(len(self.cards) - 1))
