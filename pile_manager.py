# pile_manager.py
from enum import Enum
import json
from typing import List
from card import Card
from pile import Pile, PileType
from card_sorter import CardSorter

class Step(Enum):
    MOVE_FROM_FEED = 0
    INITIAL_COLLECTION = 1,
    SCATTER = 2,
    GATHER = 3

class PileManager:
    def __init__(self, config, simulated = False, simulatedPiles = None):
        self.config = config
        self.simulated = simulated
        self.piles: List[Pile] = []
        self.cardSorter = CardSorter()
        self.virtualPiles = None
        self.step = Step.MOVE_FROM_FEED
    
    def initialize_piles(self):
        xCords = self.config.get_config('x_column_coordinates')
        xCords.sort()
        yCords = self.config.get_config('y_row_coordinates')
        yCords.sort(reverse=True)
        if self.simulated:
            imagePiles = self.load_image_piles()
            self.virtualPiles: List[List[Pile]] = []
            for xC in range(len(xCords)):
                column = []
                for yC in range(len(yCords)):
                    column.append(Pile(xC, yC, xC, yC, self.config.get_config('max_cards_per_pile')))
                self.virtualPiles.append(column)
        for y in yCords:
            for x in xCords:
                xIndex = xCords.index(x)
                yIndex = yCords.index(y)
                pile_type = PileType.SORTING
                for pile_info in self.config.get_config("initial_feeder_piles"):
                    x_index = pile_info["x_index"]
                    y_index = pile_info["y_index"]
                    if xIndex == x_index and yIndex == y_index:
                        pile_type = PileType.FEEDER
                for pile_info in self.config.get_config("initial_collection_piles"):
                    x_index = pile_info["x_index"]
                    y_index = pile_info["y_index"]
                    if xIndex == x_index and yIndex == y_index:
                        pile_type = PileType.COLLECTION
                pile = Pile(x, y, xIndex, yIndex, self.config.get_config('max_cards_per_pile'), pile_type=pile_type)
                try:
                    #move to a simulated/virtualized pile. when taking an image, return the top image of that pile
                    imagePile = imagePiles[yIndex * 5 + xIndex]
                    for image in imagePile:
                        name = image.split('.')[0]
                        newCard = Card(name,imageFile=f'SimulatedCardImages\\{image}')
                        self.virtualPiles[xIndex][yIndex].add_card(newCard)
                finally:
                    self.piles.append(pile)
            # Sort self.piles by y, then by x
    
    def load_image_piles(self, json_file="image_piles.json"):
        # Open and load the JSON file
        with open(json_file, 'r') as file:
            image_piles = json.load(file)
        return image_piles

    def update_pile(self, pile:Pile, name, image):
        if image is not None:
            new_card = Card(name, image = image)
            pile.add_card(new_card)
        else:
            pile.isFullyDiscovered = True
    
    def check_pile_status(self, pile:Pile):
        return pile.is_empty()
    
    def get_top_card(self, pile:Pile)-> Card:
        return pile.get_top_card() 
    
    def find_scatter_target(self, card) -> Pile:
        for pile in self.piles:
            if pile.is_empty() or (self.cardSorter.compare_cards(pile.get_top_card(), card) and len(pile.cards) < pile.max_cards):
                return pile
        return None
    
    def find_initial_collect_piles(self) -> tuple[Pile, Pile]:
        from_pile = next(
            (pile for pile in self.piles if pile.pile_type == PileType.FEEDER and not pile.isFullyDiscovered),
            None
        )
        
        to_pile = next(
            (pile for pile in self.piles if pile.pile_type != PileType.FEEDER and pile.isFullyDiscovered and not pile.full()),
            None
        )
        
        return from_pile, to_pile


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

