# pile_manager.py
from enum import Enum
import json
from typing import List, Tuple, Union
from card import Card
from pile import Pile, PileType
from card_sorter import CardSorter

class Step(Enum):
    MOVE_FROM_FEED = 0
    INITIAL_COLLECTION = 1,
    SCATTER = 2,
    GATHER = 3,
    FINISH = 4



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
                        file = f'SimulatedCardImages\\{image}'
                        newCard = Card(name,imageFile = file)
                        if newCard.image.filename == '':
                            newCard.image.filename = file
                        self.virtualPiles[xIndex][yIndex].add_card(newCard)
                finally:
                    self.piles.append(pile)
            # Sort self.piles by y, then by x
    
    def load_image_piles(self, json_file="image_piles.json"):
        # Open and load the JSON file
        with open(json_file, 'r') as file:
            image_piles = json.load(file)
        return image_piles

    def pick(self, xIndex:int, yIndex:int) -> Card:
        pile = self.getPile(xIndex, yIndex)
        card = pile.pick()
        if self.simulated:
            self.activeVirtualCard = self.virtualPiles[xIndex][yIndex].pick()
        return card
    
    def place(self, xIndex:int, yIndex:int, card:Card):
        pile = self.getPile(xIndex, yIndex)
        if self.simulated:
            self.activeVirtualCard = self.virtualPiles[xIndex][yIndex].place(self.activeVirtualCard.copy())
            self.activeVirtualCard = None
        return pile.place(card)

    def discover_pile(self, pile:Pile, name, image):
        if pile.isFullyDiscovered:
            return
        if image is not None:
            new_card = Card(name, image = image)
            pile.add_card(new_card)
        else:
            pile.isFullyDiscovered = True
    
    def check_pile_status(self, pile:Pile):
        return pile.is_empty()
    
    def get_top_card(self, pile:Pile)-> Card:
        return pile.get_top_card() 

    
    def get_action_piles(self) -> tuple[Pile, Pile]:
        if self.step == Step.MOVE_FROM_FEED:
            return self.find_move_from_feed_piles()
        elif self.step == Step.INITIAL_COLLECTION: 
            return self.find_initial_collect_piles()
        elif self.step == Step.SCATTER: 
            return self.find_scatter_target()
        elif self.step == Step.GATHER: 
            return self.find_gather_target()
        else:
            return (None, None)
    
    def find_move_from_feed_piles(self) -> tuple[Pile, Pile]:
        from_pile = next(
            (pile for pile in self.piles if pile.pile_type == PileType.FEEDER and not pile.isFullyDiscovered),
            None
        )
        
        to_pile = next(
            (pile for pile in self.piles if pile.pile_type != PileType.FEEDER and pile.isFullyDiscovered and not pile.full()),
            None
        )
        if from_pile is None or to_pile is None:
            return None, None
        return from_pile, to_pile

    def find_initial_collect_piles(self) -> tuple[Pile, Pile]:
        from_pile = next(
            (pile for pile in self.piles if pile.pile_type != PileType.FEEDER and not pile.is_empty()),
            None
        )
        
        to_pile = next(
            (pile for pile in self.piles if pile.pile_type == PileType.FEEDER and pile.isFullyDiscovered and not pile.full()),
            None
        )
        if from_pile is None or to_pile is None:
            return None, None
        return from_pile, to_pile
    
    def find_scatter_target(self) -> tuple[Pile, Pile]:
        def next_to_pile()-> Pile : return next(
            (pile for pile in self.piles if pile.pile_type == PileType.SORTING and not pile.full() and (pile.is_empty() or pile.get_top_card().rank <= from_pile.get_top_card().rank)),
            None
        )

        minRank = 10000000

        from_pile = None
        for fp in self.get_piles_by_type(PileType.FEEDER):
            if not fp.is_empty():
                r = fp.get_top_card().rank
                if r < minRank:
                    minRank = r
                    from_pile = fp
            else:
                fp.pile_type = PileType.TEMP
        if from_pile is None:
            self.updateStep()
            return None, None

        to_pile = next_to_pile()
        
        if to_pile == None:
            minRank = 10000000
            for pile in self.piles:
                if pile.pile_type == PileType.SORTING:
                    r = pile.get_top_card().rank
                    if r < minRank:
                        minRank = r

            for pile in self.piles:
                if pile.pile_type == PileType.FEEDER:
                    if pile.is_empty() or pile.get_top_card().rank < minRank:
                        pile.pile_type = PileType.TEMP
            
            to_pile = next_to_pile()

        if from_pile is None or to_pile is None:
            self.updateStep()
            return None, None
        return from_pile, to_pile

    def find_gather_target(self) -> tuple[Pile, Pile]:
        maxRank = -1
        from_pile = None
        for pile in self.get_piles_by_type(PileType.SORTING):
            if not pile.is_empty():
                r = pile.get_top_card().rank
                if r > maxRank:
                    maxRank = r
                    from_pile = pile
        if from_pile is None:
            self.updateStep()
            return None, None
        
        to_pile = next(
            (pile for pile in self.piles if pile.pile_type == PileType.COLLECTION \
             and pile.isFullyDiscovered and not pile.full()),
            None
        )
        if from_pile is None or to_pile is None:
            self.updateStep()
            return None, None
        return from_pile, to_pile
    
    def getPile(self, xIndex:int, yIndex:int) -> Pile:
        return next((pile for pile in self.piles if pile.xIndex == xIndex and pile.yIndex == yIndex), None)
    
    def all_cards_sorted(self):
        return all(pile.is_sorted() for pile in self.piles)
    
    def get_highest_card(self) -> Card:
        highest_card = None
        for pile in self.piles:
            top_card = pile.get_top_card()
            if top_card and (not highest_card or self.cardSorter.compare_cards(top_card, highest_card)):
                highest_card = top_card
        return highest_card
        
    def get_piles_by_type(self, pile_type: Union[PileType, List[PileType]]) -> List[Pile]:
        # If a single pile type is provided, convert it to a list for uniform processing
        if not isinstance(pile_type, list):
            pile_type = [pile_type]
        
        # Filter piles that match any of the provided types
        return [pile for pile in self.piles if pile.pile_type in pile_type]

    def updateStep(self):
        debug = False
        nextStep = self.step
        if self.step == Step.MOVE_FROM_FEED:
            if all(pile.isFullyDiscovered for pile in self.get_piles_by_type(PileType.FEEDER)):
                nextStep = Step.INITIAL_COLLECTION
        elif self.step == Step.INITIAL_COLLECTION:
            if all(pile.is_empty() for pile in self.get_piles_by_type(PileType.SORTING)) and \
            all(pile.is_empty() for pile in self.get_piles_by_type(PileType.COLLECTION)):
                nextStep = Step.SCATTER
                self.label_rank_all_cards()
        elif self.step == Step.SCATTER:
            if len(self.get_piles_by_type(PileType.FEEDER)) <= 0:
                nextStep = Step.GATHER
        elif self.step == Step.GATHER:
            if all(pile.is_empty() for pile in self.get_piles_by_type(PileType.SORTING)):
                if all(pile.is_empty() for pile in self.get_piles_by_type(PileType.TEMP))\
                    and all(pile.is_empty() for pile in self.get_piles_by_type(PileType.FEEDER)):
                        if self.check_all_sorted():
                            nextStep = Step.FINISH
                if nextStep == self.step:
                    if all(pile.is_empty() for pile in self.get_piles_by_type(PileType.TEMP)):
                        for pile in self.get_piles_by_type(PileType.COLLECTION):
                            pile.pile_type = PileType.FEEDER
                        for pile in self.get_piles_by_type(PileType.TEMP):
                            pile.pile_type = PileType.COLLECTION
                    else:
                        for pile in self.get_piles_by_type(PileType.TEMP):
                            pile.pile_type = PileType.FEEDER
                    nextStep = Step.SCATTER
        else:
            raise
        self.step = nextStep

    def label_rank_all_cards(self):
        mapping = self.get_all_sorted_cards()
        for pile in self.piles:
            for card in pile.cards:
                card.rank = mapping[card.name]

    def get_all_sorted_cards(self) -> dict:
        # Step 1: Collect all cards from all piles
        all_cards = set()
        for pile in self.piles:
            all_cards.update(pile.cards)

        # Convert the set to a list to sort it
        all_cards = list(all_cards)

        # Step 2: Sort the cards
        sorted_cards = sorted(all_cards)

        # Step 3: Create a sorted dictionary with card names and ranks
        sorted_dict = {card.name: index + 1 for index, card in enumerate(sorted_cards)}

        return sorted_dict
    
    def check_ordered_tuples(self, tuples_list: List[Tuple[int, ...]]):
        sortedList = tuples_list.copy()
        sortedList.sort()
        # Flatten the list of tuples into a list of individual elements
        flattened = [item for tup in tuples_list for item in tup]
        flattened_sorted = [item for tup in sortedList for item in tup]
        flattened.sort()
        return flattened == flattened_sorted

    def check_all_sorted(self) ->bool:
        if self.all_cards_sorted():
            bookends = []
            for pile in self.piles:
                if not pile.is_empty():
                    bookends.append(pile.get_bookends())
            return self.check_ordered_tuples(bookends)
        return False
