# pile_manager.py

from pile import Pile
from card_sorter import CardSorter

class PileManager:
    def __init__(self, config):
        self.config = config
        self.piles = []
        self.cardSorter = CardSorter()
        self.knownCards = {}
        self.initialize_piles()
    
    def initialize_piles(self):
        for x, y in self.config.get_config('pile_coordinates'):
            pile = Pile(x, y, self.config.get_config('max_cards_per_pile'))
            self.piles.append(pile)
    
    def update_pile(self, pile, card):
        pile.add_card(card)
        self.knownCards[card] = pile
    
    def check_pile_status(self, pile):
        return pile.is_empty()
    
    def get_top_card(self, pile):
        return pile.get_top_card()
    
    def find_scatter_target(self, card):
        for pile in self.piles:
            if pile.is_empty() or (self.cardSorter.compare_cards(pile.get_top_card(), card) and len(pile.cards) < pile.max_cards):
                return pile
        return None
    
    def find_gather_target(self):
        for pile in reversed(self.piles):
            if len(pile.cards) < pile.max_cards:
                return pile
        return None
    
    def all_cards_sorted(self):
        return all(pile.is_sorted() for pile in self.piles)
    
    def get_highest_card(self):
        highest_card = None
        for pile in self.piles:
            top_card = pile.get_top_card()
            if top_card and (not highest_card or self.cardSorter.compare_cards(top_card, highest_card)):
                highest_card = top_card
        return highest_card
