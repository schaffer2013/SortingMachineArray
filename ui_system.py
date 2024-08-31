# ui_system.py

import pygame

class UISystem:
    def __init__(self, pile_manager):
        self.pile_manager = pile_manager
        self.window = pygame.display.set_mode((800, 600))
        self.pileImages = []
    
    def update_display(self):
        # Update the UI with the current state of each pile
        self.window.fill((255, 255, 255))
        for pile in self.pile_manager.piles:
            # Placeholder for displaying pile images
            pass
        pygame.display.flip()
    
    def configure_pile(self, pile):
        # Allow the user to configure the pile's properties
        pass
