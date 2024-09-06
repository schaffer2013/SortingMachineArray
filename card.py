from PIL import Image
import copy
from sortedcontainers import SortedSet

class Card:
    RARITY_ORDER = {
        "MYTHIC": 1,
        "RARE": 2,
        "OTHER": 3  # Add more rarities as needed
    }

    TYPE_ORDER = {
        "creature": 1,
        "artifact": 2,
        "battle": 3,
        "instant": 4,
        "sorcery": 5,
        "planeswalker": 6,
        "enchantment": 7,
        "non-basic land": 8,
        "basic land": 9,
        "other": 10  # Default for unrecognized types
    }

    COLOR_ORDER = {
        "white": 1,
        "blue": 2,
        "black": 3,
        "red": 4,
        "green": 5,
        "colorless": 6,
        "default": 7  # Default for cards without recognized color
    }

    def __init__(self, name, rarity=None, card_type=None, color=None, image: Image = None, imageFile=None):
        self.name = name
        self.rarity = rarity if rarity is not None else "OTHER"  # Default to 'OTHER' if not provided
        self.card_type = card_type if card_type is not None else "other"  # Default to 'other' if not provided
        self.color = color if color is not None else "default"  # Default to 'default' if not provided
        self.image = image  # Expected to be a PIL Image object
        self.rank = 99999
        if image is None and imageFile is not None:
            self.image = Image.open(imageFile)

    def __lt__(self, other):
        # Compare rarity first
        if self.RARITY_ORDER[self.rarity] != self.RARITY_ORDER[other.rarity]:
            return self.RARITY_ORDER[self.rarity] < self.RARITY_ORDER[other.rarity]
        
        # If rarity is the same, compare card type
        if self.TYPE_ORDER[self.card_type] != self.TYPE_ORDER[other.card_type]:
            return self.TYPE_ORDER[self.card_type] < self.TYPE_ORDER[other.card_type]

        # If rarity and card type are the same, compare color
        if self.COLOR_ORDER[self.color] != self.COLOR_ORDER[other.color]:
            return self.COLOR_ORDER[self.color] < self.COLOR_ORDER[other.color]
        
        # If rarity, card type, and color are the same, compare alphabetically by name
        return self.name < other.name

    def __eq__(self, other):
        return (
            self.RARITY_ORDER[self.rarity] == self.RARITY_ORDER[other.rarity] and
            self.TYPE_ORDER[self.card_type] == self.TYPE_ORDER[other.card_type] and
            self.COLOR_ORDER[self.color] == self.COLOR_ORDER[other.color] and
            self.name == other.name
        )

    def __hash__(self):
        # Combine the hash of each attribute that is part of equality comparison
        return hash((self.name, self.rarity, self.card_type, self.color))

    def show(self):
        self.image.show()

    def copy(self):
        return copy.deepcopy(self)


class CardSet:
    def __init__(self):
        self.cards = SortedSet()

    def add_card(self, card: Card):
        self.cards.add(card)

    def get_rank(self, card_name: str) -> int:
        for index, card in enumerate(self.cards):
            if card.name == card_name:
                return index + 1  # 1-based index for rank
        return -1  # Return -1 if the card is not found

    def get_all_cards(self):
        return list(self.cards)

# Example usage in the main block
if __name__ == "__main__":
    card_set = CardSet()
    
    # Create some card instances with colors
    card1 = Card(name="Fireball", rarity="MYTHIC", card_type="sorcery", color="red")
    card2 = Card(name="Lightning Bolt", rarity="RARE", card_type="instant", color="red")
    card3 = Card(name="Forest", rarity="OTHER", card_type="basic land", color="green")
    card4 = Card(name="Grizzly Bears", rarity="OTHER", card_type="creature", color="green")
    card5 = Card(name="Island", rarity="OTHER", card_type="basic land", color="blue")
    card6 = Card(name="Plains", rarity="OTHER", card_type="basic land", color="white")

    # Add cards to the set
    card_set.add_card(card1)
    card_set.add_card(card2)
    card_set.add_card(card3)
    card_set.add_card(card4)
    card_set.add_card(card5)
    card_set.add_card(card6)

    # Get rank of a specific card
    rank = card_set.get_rank("Grizzly Bears")
    print(f"Rank of 'Grizzly Bears': {rank}")

    # Print all cards
    print("\nCards in the set:")
    for card in card_set.get_all_cards():
        print(f"{card.name} (Rarity: {card.rarity}, Type: {card.card_type}, Color: {card.color})")
