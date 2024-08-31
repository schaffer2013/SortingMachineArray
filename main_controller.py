# main_controller.py

from config_manager import ConfigManager
from gantry_system import GantrySystem
from camera_system import CameraSystem
from pile_manager import PileManager
from ui_system import UISystem

class MainController:
    def __init__(self, config_file):
        self.config = ConfigManager(config_file)
        self.gantry = GantrySystem(self.config)
        self.camera = CameraSystem(self.config)
        self.pileManager = PileManager(self.config)
        self.ui = UISystem(self.pileManager)
    
    def initialize(self):
        self.pileManager.initialize_piles()
        for pile in self.pileManager.piles:
            self.gantry.move_to(pile.x, pile.y)
            image = self.camera.capture_image()
            card = self.camera.process_image(image)
            self.pileManager.update_pile(pile, card)
        self.ui.update_display()
    
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
    
    def move_card(self, from_pile, to_pile):
        self.gantry.move_to(from_pile.x, from_pile.y)
        self.gantry.lower_z()
        self.gantry.activate_suction()
        self.gantry.raise_z()
        self.gantry.move_to(to_pile.x, to_pile.y)
        self.gantry.lower_z()
        self.gantry.deactivate_suction()
        self.gantry.raise_z()
