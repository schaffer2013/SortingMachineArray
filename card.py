from PIL import Image

class Card:
    def __init__(self, name, rank=None, rarity='common', image:Image=None):
        self.name = name
        self.rank = rank
        self.rarity = rarity
        self.image = image  # Expected to be a PIL Image object

    def __lt__(self, other):
        if self.rank is not None and other.rank is not None:
            return self.rank < other.rank
        return False  # Default behavior if rank is None

    def __eq__(self, other):
        if self.rank is not None and other.rank is not None:
            return self.rank == other.rank
        return False  # Default behavior if rank is None
    
    def show(self):
        self.image.show()
