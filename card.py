import json
import os
from io import BytesIO
from PIL import Image
import copy
import requests
from sortedcontainers import SortedSet
import scrython

class Card:
    RARITY_ORDER = {
        "MYTHIC": 1,
        "RARE": 1,
        "OTHER": 3  # Add more rarities as needed
    }

    TYPE_ORDER = {
        "creature": 1,
        "artifact": 1,
        "battle": 1,
        "instant": 1,
        "sorcery": 1,
        "planeswalker": 1,
        "enchantment": 1,
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
        "multi": 6,
        "colorless": 7,
        "default": 8  # Default for cards without recognized color
    }

    COLOR_TRANSLATION = {
        'w': 'white',
        'u': 'blue',
        'b': 'black',
        'r': 'red',
        'g': 'green',
        'c': 'colorless'  # 'c' is sometimes used for colorless mana
    }

    JSON_FILE = "card_data.json"

    def __init__(self, name, rarity=None, card_type=None, color=None, image: Image = None, imageFile=None):
        self.name = name
        self.rarity = rarity if rarity is not None else "OTHER"  # Default to 'OTHER' if not provided
        self.card_type = card_type if card_type is not None else "other"  # Default to 'other' if not provided
        self.color = color if color is not None else "default"  # Default to 'default' if not provided
        self.image = image  # Expected to be a PIL Image object
        self.rank = 99999
        if image is None and imageFile is not None:
            self.image = Image.open(imageFile)

        # Load card data from JSON or fetch from Scryfall if necessary
        self.load_or_fetch_data()

    def load_or_fetch_data(self):
        card_data = self.load_card_data()

        if card_data:
            # Load attributes from JSON file
            self.rarity = card_data.get('rarity', "OTHER")
            self.card_type = card_data.get('card_type', "other")
            self.color = card_data.get('color', "default")
            image_url = card_data.get('image_url')

            # Download and assign image
            if image_url and not self.image:
                response = requests.get(image_url)
                self.image = Image.open(BytesIO(response.content))
        else:
            # Fetch from Scryfall and save to JSON
            self.fetch_card_data()

    def load_card_data(self):
        """Load card data from a JSON file if available."""
        if os.path.exists(self.JSON_FILE):
            with open(self.JSON_FILE, 'r') as file:
                card_data = json.load(file)
                if self.name in card_data:
                    return card_data[self.name]
                if self.name.replace('_', ' ') in card_data:
                    return card_data[self.name]
        return None

    def save_card_data(self, card_data):
        """Save card data to a JSON file."""
        if os.path.exists(self.JSON_FILE):
            with open(self.JSON_FILE, 'r') as file:
                all_card_data = json.load(file)
        else:
            all_card_data = {}

        all_card_data[self.name] = card_data

        with open(self.JSON_FILE, 'w') as file:
            json.dump(all_card_data, file, indent=4)

    def fetch_card_data(self):
        try:
            card_data = scrython.cards.Named(fuzzy=self.name.replace('_', ' '))

            # Set card attributes from Scryfall API response
            self.rarity = card_data.rarity().upper()
            try:
                dummy = self.RARITY_ORDER[self.rarity]
            except:
                self.rarity = "OTHER"
            try:
                self.card_type = card_data.type_line().split(" — ")[0].lower()  # Basic type
                if 'creature' in self.card_type:
                    self.card_type = 'creature'
                dummy = self.TYPE_ORDER[self.card_type]
            except:
                self.card_type = card_data.type_line().split(" — ")[0].lower().split(" ")[-1]
            try:
                if self.card_type == 'land':
                    self.card_type = 'non-basic land'
                dummy = self.TYPE_ORDER[self.card_type]
            except:
                self.card_type = 'other'

            # Handle color for lands differently
            if 'land' in self.card_type:
                color_identity = card_data.color_identity()
                self.color = 'colorless' if not color_identity else ','.join(
                    [self.COLOR_TRANSLATION[color.lower()] for color in color_identity]
                ).lower()
            else:
                colors = card_data.colors()
                self.color = 'colorless' if not colors else ','.join(
                    [self.COLOR_TRANSLATION[color.lower()] for color in colors]
                ).lower()
            if ',' in self.color:
                self.color = 'multi'

            # Download and assign image
            image_urls = card_data.image_uris()
            if 'normal' in image_urls:
                url = image_urls['normal'].rsplit('?', 1)[0]
            else: 
                url = image_urls[0].rsplit('?', 1)[0]
            response = requests.get(url)
            self.image = Image.open(BytesIO(response.content))

            # Save card data to JSON file
            card_info = {
                "rarity": self.rarity,
                "card_type": self.card_type,
                "color": self.color,
                "image_url": url
            }
            self.save_card_data(card_info)

        except Exception as e:
            print(f"Error fetching data for {self.name}: {e}")

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
        if self.image:
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
    
    # Fetch data for cards using Scrython
    card_set.add_card(Card(name="Fireball"))
    card_set.add_card(Card(name="Lightning Bolt"))
    card_set.add_card(Card(name="Forest"))
    card_set.add_card(Card(name="Grizzly Bears"))
    card_set.add_card(Card(name="Island"))
    card_set.add_card(Card(name="Plains"))
    card_set.add_card(Card(name="Atraxa, Grand Unifier"))
    card_set.add_card(Card(name="Kamahl, Fist of Krosa"))
    
    # Get rank of a specific card
    rank = card_set.get_rank("Grizzly Bears")
    print(f"Rank of 'Grizzly Bears': {rank}")

    # Print all cards
    print("\nCards in the set:")
    for card in card_set.get_all_cards():
        print(f"{card.name} (Rarity: {card.rarity}, Type: {card.card_type}, Color: {card.color})")
