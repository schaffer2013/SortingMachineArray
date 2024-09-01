# pile_manager.py
from typing import List
from card import Card
from pile import Pile
from card_sorter import CardSorter

class PileManager:
    def __init__(self, config):
        self.config = config
        self.piles: List[Pile] = []
        self.cardSorter = CardSorter()
        self.initialize_piles()
    
    def initialize_piles(self):
        if len(self.piles) ==0:
            xCords = self.config.get_config('x_column_coordinates')
            xCords.sort()
            yCords = self.config.get_config('y_row_coordinates')
            yCords.sort(reverse=True)
            for x in xCords:
                for y in yCords:
                    pile = Pile(x, y, xCords.index(x), yCords.index(y), self.config.get_config('max_cards_per_pile'))
                    self.piles.append(pile)
    
    def update_pile(self, pile:Pile, name, image):
        new_card = Card(name, image = image)
        pile.add_card(new_card)
    
    def check_pile_status(self, pile:Pile):
        return pile.is_empty()
    
    def get_top_card(self, pile:Pile)-> Card:
        return pile.get_top_card() 
    
    def find_scatter_target(self, card) -> Pile:
        for pile in self.piles:
            if pile.is_empty() or (self.cardSorter.compare_cards(pile.get_top_card(), card) and len(pile.cards) < pile.max_cards):
                return pile
        return None
    
    def find_gather_target(self) -> Pile:
        for pile in reversed(self.piles):
            if len(pile.cards) < pile.max_cards:
                return pile
        return None
    
    def all_cards_sorted(self):
        return all(pile.is_sorted() for pile in self.piles)
    
    def get_highest_card(self) -> Card:
        highest_card = None
        for pile in self.piles:
            top_card = pile.get_top_card()
            if top_card and (not highest_card or self.cardSorter.compare_cards(top_card, highest_card)):
                highest_card = top_card
        return highest_card
