from PIL import Image

class Card:
    def __init__(self, name, rank=None, rarity=None, image:Image=None, imageFile = None):
        self.name = name
        self.rank = rank
        self.rarity = rarity
        self.image = image  # Expected to be a PIL Image object
        if (image is None) and (imageFile is not None):
            self.image = Image.open(imageFile)

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