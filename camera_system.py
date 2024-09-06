# camera_system.py

from typing import List, Optional
from PIL import Image
from card import Card
import os


class CameraSystem:
    def __init__(self, config, simulated = False, virtualPiles: Optional[List[List[Card]]] = None):
        self.camera_position = (0, 0)
        self.config = config
        self.simulated = simulated
        self.virtualPiles = virtualPiles

    def capture_image(self, virtualCard:Card = None, xIndex = None, yIndex = None ) -> Image:
        # Placeholder for image capture logic
        print("Capturing image")
        if self.simulated:
            if virtualCard is not None:
                return virtualCard.image
            return None
        return Image.open("test_image.jpg")
    
    def process_image_name(self, image):
        # Placeholder for image processing logic to identify cards
        print("Processing image")
        if image is None:
            return None
        if self.simulated:
            return self.extract_card_name(image.filename)
        return "Identified Card"
    
    def find_card(self, image):
        # Detect and return the card based on its image
        return "CardName"

    
    def extract_card_name(self, image_filename: str) -> str:
        # Extract the base name without the extension
        base_name = os.path.splitext(os.path.basename(image_filename))[0]
        return base_name