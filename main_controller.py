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

    def start_sorting(self):
        while not self.pileManager.all_cards_sorted():
            self.scatter()
            self.gather()
        self.gantry.return_home()
    
    def scatter(self):
        for pile in self.pileManager.feed_piles:
            card = pile.get_top_card()
            if card:
                target_pile = self.pileManager.find_scatter_target(card)
                if target_pile:
                    self.move_card(pile, target_pile)
    
    def gather(self):
        while self.pileManager.active_sort_piles:
            highest_card = self.pileManager.get_highest_card()
            target_pile = self.pileManager.find_gather_target()
            if highest_card and target_pile:
                self.move_card(highest_card.pile, target_pile)
    
    def move_card(self, from_pile:Pile, to_pile:Pile):
        if from_pile is not None and to_pile is not None:
            self.gantry.move_to(from_pile.x, from_pile.y)
            self.gantry.lower_z()
            self.gantry.activate_suction()
            self.gantry.pickCard(self.pileManager.pick(from_pile.xIndex, from_pile.yIndex))
            self.gantry.raise_z()
            self.gantry.move_to(to_pile.x, to_pile.y)
            self.gantry.lower_z()
            self.gantry.deactivate_suction()
            self.gantry.raise_z()
            self.pileManager.place(to_pile.xIndex, to_pile.yIndex, self.gantry.placeCard())
            self.gantry.move_to(from_pile.x, from_pile.y)
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
        else:
            a = 1
    
