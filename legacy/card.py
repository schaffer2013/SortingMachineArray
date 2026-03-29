import copy
import json
from io import BytesIO
from pathlib import Path

from PIL import Image
import requests
from sortedcontainers import SortedSet


class Card:
    RARITY_ORDER = {
        "MYTHIC": 1,
        "RARE": 1,
        "OTHER": 3,
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
        "other": 10,
    }

    COLOR_ORDER = {
        "white": 1,
        "blue": 2,
        "black": 3,
        "red": 4,
        "green": 5,
        "multi": 6,
        "colorless": 7,
        "default": 8,
    }

    COLOR_TRANSLATION = {
        "w": "white",
        "u": "blue",
        "b": "black",
        "r": "red",
        "g": "green",
        "c": "colorless",
    }

    JSON_FILE = "card_data.json"

    def __init__(self, name, rarity=None, card_type=None, color=None, image: Image = None, imageFile=None):
        self.name = name
        self.rarity = rarity if rarity is not None else "OTHER"
        self.card_type = card_type if card_type is not None else "other"
        self.color = color if color is not None else "default"
        self.image = image
        self.rank = 99999
        if image is None and imageFile is not None:
            self.image = Image.open(imageFile)

        self.load_or_fetch_data()

    @property
    def display_name(self) -> str:
        return self.name.replace("_", " ").strip()

    def load_or_fetch_data(self):
        card_data = self.load_card_data()

        if card_data:
            self._apply_cached_data(card_data)
            return

        self.fetch_card_data()

    def load_card_data(self):
        cache_path = Path(self.JSON_FILE)
        if not cache_path.exists():
            return None
        with cache_path.open("r", encoding="utf-8") as file:
            card_data = json.load(file)
        return card_data.get(self.name) or card_data.get(self.display_name)

    def save_card_data(self, card_data):
        cache_path = Path(self.JSON_FILE)
        if cache_path.exists():
            with cache_path.open("r", encoding="utf-8") as file:
                all_card_data = json.load(file)
        else:
            all_card_data = {}

        all_card_data[self.name] = card_data

        with cache_path.open("w", encoding="utf-8") as file:
            json.dump(all_card_data, file, indent=4)

    def fetch_card_data(self):
        try:
            from sorter.adapters.persistence.card_engine_catalog_sync import (
                CardEngineCatalogSyncRequest,
                load_offline_catalog_query,
                resolve_catalog_card,
            )

            project_root = Path(__file__).resolve().parent
            query = load_offline_catalog_query(project_root)
            card_data = resolve_catalog_card(
                query,
                CardEngineCatalogSyncRequest(name=self.display_name),
            )

            self._apply_catalog_data(card_data)

            image_url = card_data.get("image_url")
            normalized_image_url = self._normalize_image_url(image_url)
            if normalized_image_url and self.image is None:
                self.image = self._download_image(normalized_image_url)

            self.save_card_data(
                {
                    "name": self.display_name,
                    "scryfall_id": card_data.get("scryfall_id"),
                    "oracle_id": card_data.get("oracle_id"),
                    "rarity": self.rarity,
                    "card_type": self.card_type,
                    "color": self.color,
                    "image_url": normalized_image_url,
                }
            )
        except Exception as e:
            print(f"Error fetching data for {self.name}: {e}")

    def _apply_cached_data(self, card_data: dict):
        self.rarity = self._normalize_rarity(card_data.get("rarity"))
        self.card_type = self._normalize_cached_card_type(card_data.get("card_type"))
        self.color = self._normalize_cached_color(card_data.get("color"))
        image_url = self._normalize_image_url(card_data.get("image_url"))
        if image_url and self.image is None:
            self.image = self._download_image(image_url)

    def _apply_catalog_data(self, card_data: dict):
        self.rarity = self._normalize_rarity(card_data.get("rarity"))
        self.card_type = self._normalize_catalog_card_type(card_data)
        self.color = self._normalize_catalog_color(card_data)

    def _normalize_rarity(self, rarity: object) -> str:
        if isinstance(rarity, str) and rarity.strip():
            normalized = rarity.strip().upper()
            if normalized in self.RARITY_ORDER:
                return normalized
        return "OTHER"

    def _normalize_catalog_card_type(self, card_data: dict) -> str:
        if card_data.get("is_basic_land"):
            return "basic land"
        if card_data.get("is_land"):
            return "non-basic land"

        card_types = [str(card_type).strip().lower() for card_type in card_data.get("card_types") or [] if str(card_type).strip()]
        if "creature" in card_types:
            return "creature"
        for card_type in card_types:
            if card_type in self.TYPE_ORDER:
                return card_type
        return "other"

    def _normalize_catalog_color(self, card_data: dict) -> str:
        if "land" in self.card_type:
            symbols = card_data.get("color_identity") or []
        else:
            symbols = card_data.get("colors") or []
        return self._normalize_color_symbols(symbols)

    def _normalize_cached_card_type(self, card_type: object) -> str:
        if not isinstance(card_type, str) or not card_type.strip():
            return "other"
        normalized = card_type.strip().lower()
        if normalized == "land":
            return "non-basic land"
        if normalized in self.TYPE_ORDER:
            return normalized
        return "other"

    def _normalize_cached_color(self, color: object) -> str:
        if not isinstance(color, str) or not color.strip():
            return "default"
        normalized = color.strip().lower()
        if normalized in self.COLOR_ORDER:
            return normalized
        return "default"

    def _normalize_color_symbols(self, values: list[object]) -> str:
        translated = []
        for value in values:
            key = str(value).strip().lower()
            if not key:
                continue
            translated_value = self.COLOR_TRANSLATION.get(key)
            if translated_value:
                translated.append(translated_value)

        unique = sorted(set(translated), key=lambda name: self.COLOR_ORDER.get(name, 99))
        if not unique:
            return "colorless"
        if len(unique) > 1:
            return "multi"
        return unique[0]

    def _normalize_image_url(self, image_url: object) -> str | None:
        if not isinstance(image_url, str) or not image_url.strip():
            return None
        return image_url.strip().rsplit("?", 1)[0]

    def _download_image(self, image_url: str) -> Image.Image:
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))

    def __lt__(self, other):
        if self.RARITY_ORDER[self.rarity] != self.RARITY_ORDER[other.rarity]:
            return self.RARITY_ORDER[self.rarity] < self.RARITY_ORDER[other.rarity]

        if self.TYPE_ORDER[self.card_type] != self.TYPE_ORDER[other.card_type]:
            return self.TYPE_ORDER[self.card_type] < self.TYPE_ORDER[other.card_type]

        if self.COLOR_ORDER[self.color] != self.COLOR_ORDER[other.color]:
            return self.COLOR_ORDER[self.color] < self.COLOR_ORDER[other.color]

        return self.name < other.name

    def __eq__(self, other):
        return (
            self.RARITY_ORDER[self.rarity] == self.RARITY_ORDER[other.rarity]
            and self.TYPE_ORDER[self.card_type] == self.TYPE_ORDER[other.card_type]
            and self.COLOR_ORDER[self.color] == self.COLOR_ORDER[other.color]
            and self.name == other.name
        )

    def __hash__(self):
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
                return index + 1
        return -1

    def get_all_cards(self):
        return list(self.cards)


if __name__ == "__main__":
    card_set = CardSet()

    card_set.add_card(Card(name="Fireball"))
    card_set.add_card(Card(name="Lightning Bolt"))
    card_set.add_card(Card(name="Forest"))
    card_set.add_card(Card(name="Grizzly Bears"))
    card_set.add_card(Card(name="Island"))
    card_set.add_card(Card(name="Plains"))
    card_set.add_card(Card(name="Atraxa, Grand Unifier"))
    card_set.add_card(Card(name="Kamahl, Fist of Krosa"))

    rank = card_set.get_rank("Grizzly Bears")
    print(f"Rank of 'Grizzly Bears': {rank}")

    print("\nCards in the set:")
    for card in card_set.get_all_cards():
        print(f"{card.name} (Rarity: {card.rarity}, Type: {card.card_type}, Color: {card.color})")
