# main_controller.py

from PIL import Image
from config_manager import ConfigManager
from gantry_system import GantrySystem
from camera_system import CameraSystem
from pile import Pile
from pile_manager import PileManager

class MainController:
    def __init__(self, config_file):
        self.config = ConfigManager(config_file)
        if self.config.simulated:
            self.simulatedPiles = None
        else:
            self.simulatedPiles = None
        self.gantry = GantrySystem(self.config)
        self.pileManager = PileManager(self.config, simulated = self.config.simulated)
        self.camera = CameraSystem(self.config, simulated = self.config.simulated,  virtualPiles = self.pileManager.virtualPiles)

    
    def initialize(self):
        self.pileManager.initialize_piles()
        for pile in self.pileManager.piles:
            self.gantry.move_to(pile.x, pile.y)
            if self.config.simulated:
                activeVirtualPile = self.pileManager.virtualPiles[pile.xIndex][pile.yIndex]
                topVirtualCard =activeVirtualPile.get_top_card()
                image = self.camera.capture_image(virtualCard=topVirtualCard)
            else:
                image = self.camera.capture_image()
            name = self.camera.process_image_name(image)
            self.pileManager.discover_pile(pile, name, image)

    def getVirtualImage(self, pileXIndex: int, pileYIndex: int) -> Image:
        if not self.config.simulated:
            raise
        pile = self.pileManager.getPile(pileXIndex, pileYIndex)
        activeVirtualPile = self.pileManager.virtualPiles[pile.xIndex][pile.yIndex]
        topVirtualCard =activeVirtualPile.get_top_card()
        image = self.camera.capture_image(virtualCard=topVirtualCard)
        return image
    
    def move_card(self, from_pile:Pile, to_pile:Pile):
        if from_pile is not None and to_pile is not None:
            # Move to initial Pile
            self.move_to_pile(from_pile)
            self.pick_card_and_move(from_pile, to_pile)
            self.place_card_and_move(from_pile, to_pile)
            self.process_and_finish(from_pile)
        else:
            raise

    def move_to_pile(self, from_pile: Pile):
        if from_pile is not None:
            self.gantry.move_to(from_pile.x, from_pile.y, immediateMove=False)

    def pick_card_and_move(self, from_pile:Pile, to_pile:Pile):
        """Lower gantry, activate suction, and pick the card from the pile."""
            # Move to second pile
        self.gantry.lower_z()
        self.gantry.activate_suction()
        self.gantry.pickCard(self.pileManager.pick(from_pile.xIndex, from_pile.yIndex))
        self.gantry.raise_z()
        self.gantry.move_to(to_pile.x, to_pile.y, immediateMove=False)

    def place_card_and_move(self, from_pile:Pile, to_pile:Pile):
        # Back to first pile
        self.gantry.lower_z()
        self.gantry.deactivate_suction()
        self.gantry.raise_z()
        self.pileManager.place(to_pile.xIndex, to_pile.yIndex, self.gantry.placeCard())
        self.gantry.move_to(from_pile.x, from_pile.y, immediateMove=False)

    def process_and_finish(self, from_pile: Pile):
        """Process image and finish the pile update."""
        # Process and finish
        if self.config.simulated:
            activeVirtualPile = self.pileManager.virtualPiles[from_pile.xIndex][from_pile.yIndex]
            topVirtualCard =activeVirtualPile.get_top_card()
            image = self.camera.capture_image(virtualCard=topVirtualCard)
            try:
                name = self.camera.process_image_name(image)
            except:
                name = from_pile.get_top_card().name
        else:
            image = self.camera.capture_image()
            name = self.camera.process_image_name(image)
        self.pileManager.discover_pile(from_pile, name, image)
        self.pileManager.updateStep()
    
