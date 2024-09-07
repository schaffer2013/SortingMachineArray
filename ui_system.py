from enum import Enum
from functools import cache
import pygame
import sys
from PIL import Image
from main_controller import MainController
from pile_manager import PileManager, Step

class UISystem:
    CARD_WIDTH = 70
    CARD_HEIGHT = 97
    BORDER_THICKNESS = 5

    class ActionStep(Enum):
        INITIAL_MOVE = 0
        PICK_AND_MOVE = 1,
        PLACE_AND_MOVE = 2,
        FINISH = 3

    def __init__(self, controller: MainController):
        self.controller = controller  
        self.pile_manager = controller.pileManager
        self.sort = False
        pygame.init()
        self.window = pygame.display.set_mode((1000, 600))
        pygame.display.set_caption("Card Sorting Machine UI")
        self.clock = pygame.time.Clock()

        # Example buttons
        self.buttons = [
            {"rect": pygame.Rect(50, 500, 100, 50), "color": (0, 200, 0), "text": "Sort", "description": "sort"},
            {"rect": pygame.Rect(200, 500, 100, 50), "color": (200, 0, 0), "text": "Stop", "description": "stop"}
        ]

        # Hover state
        self.hovered_pile = None
    
    def initialize(self):
        self.controller.initialize()
        for pile in self.pile_manager.piles:
            tlX, tlY = self.getTopLeftFromCenter(pile.x, pile.y, self.CARD_WIDTH, self.CARD_HEIGHT)
            self.buttons.append({"rect": pygame.Rect(tlX, tlY, self.CARD_WIDTH, self.CARD_HEIGHT), "color": None, "text": None, "description": f"pile({pile.xIndex}, {pile.yIndex})"})

    def update_display(self):
        self.window.fill((255, 255, 255))
        self.draw_piles()
        self.draw_buttons()
        self.draw_gantry()
        self.draw_hover_image()  # Draw the hovered image if any
        pygame.display.flip()

    def draw_piles(self):
        # Draw the piles (placeholder implementation)
        for pile in self.pile_manager.piles:
            # Replace with actual drawing logic for piles
                # Blit the Pygame image to the window, centered
            topCard = pile.get_top_card()
            if topCard:
                topCardImage = topCard.image
                pygame_image, width, height = self.resize_image(topCardImage, max_width = self.CARD_WIDTH, max_height=self.CARD_HEIGHT)
                self.window.blit(pygame_image, self.getTopLeftFromCenter(pile.x, pile.y, width, height))
            # Check if the pile is fully discovered
            if not pile.isFullyDiscovered:
                # Calculate the rectangle's top-left position
                top_left = self.getTopLeftFromCenter(pile.x, pile.y, self.CARD_WIDTH, self.CARD_HEIGHT)
                
                # Draw a red border around the pile
                pygame.draw.rect(
                    self.window,
                    (255, 0, 0),  # Red color in RGB
                    pygame.Rect(top_left[0]- self.BORDER_THICKNESS, top_left[1] - self.BORDER_THICKNESS, self.CARD_WIDTH + self.BORDER_THICKNESS *2, self.CARD_HEIGHT+ self.BORDER_THICKNESS *2),
                    self.BORDER_THICKNESS
                )

    def draw_gantry(self):
    # Draw the piles (placeholder implementation)
        card = self.controller.gantry.active_card
        x = self.controller.gantry.x_position
        y = self.controller.gantry.y_position
        if card:
            topCardImage = card.image
            pygame_image, width, height = self.resize_image(topCardImage, max_width = self.CARD_WIDTH, max_height=self.CARD_HEIGHT)
            self.window.blit(pygame_image, self.getTopLeftFromCenter(x, y, width, height))
        else:
            s = 10
            pygame.draw.rect(
                self.window,
                (255, 0, 0),  # Red cotlor in RGB
                pygame.Rect(x - s, y - s, 2*s, 2*s)
            )

    @cache
    def getTopLeftFromCenter(self, cardCenterX, cardCenterY, width, height):
        topLeftX = cardCenterX - width/2
        topLeftY = cardCenterY - height/2
        return (topLeftX, topLeftY)

    def draw_buttons(self):
        for button in self.buttons:
            if button["color"]:
                pygame.draw.rect(self.window, button["color"], button["rect"])
            
            if button["text"]:
                font = pygame.font.Font(None, 36)
                text_surf = font.render(button["text"], True, (255, 255, 255))
                text_rect = text_surf.get_rect(center=button["rect"].center)
                self.window.blit(text_surf, text_rect)

    def draw_hover_image(self):
        if self.hovered_pile:
            pile = self.pile_manager.getPile(self.hovered_pile[0], self.hovered_pile[1])
            if pile and not pile.is_empty():
                card = pile.get_top_card()
                if card and card.image:
                    # Resize the card image
                    pygame_image, width, height = self.resize_image(card.image, max_width=200, max_height=300)
                    
                    # Calculate the position for the image
                    image_x = self.window.get_width() - width - 20
                    image_y = 20
                    
                    # Blit the image to the window
                    self.window.blit(pygame_image, (image_x, image_y))
                    
                    # Render the rank text
                    font = pygame.font.Font(None, 24)
                    rank_text = f"Rank: {card.rank if card.rank is not None else 'N/A'}"
                    rank_surf = font.render(rank_text, True, (0, 0, 0))  # Black color
                    rank_rect = rank_surf.get_rect(topleft=(image_x, image_y + height + 10))
                    self.window.blit(rank_surf, rank_rect)


    def configure_pile(self, pile):
        # Placeholder for pile configuration logic
        pass

    def run(self):
        running = True
        step = self.ActionStep.INITIAL_MOVE
        to_pile = None
        from_pile = None
        while running:
            self.clock.tick(30)  # Run at 30 frames per second
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self.handle_click(event.pos)
                elif event.type == pygame.MOUSEMOTION:
                    self.handle_mouse_motion(event.pos)

            if self.sort:
                if step == self.ActionStep.INITIAL_MOVE and not self.controller.gantry.isMoving:
                    (from_pile, to_pile) = (None, None)
                    count = 0
                    while (from_pile, to_pile) == (None, None):
                        (from_pile, to_pile) = self.get_action_pile()
                        count += 1
                        if count > 4:
                            self.sort = False
                            print(f'Total travel: {self.controller.gantry.total_dist} mm')
                            self.controller.gantry.reset()
                            break
                    self.controller.move_to_pile(from_pile)
                elif step == self.ActionStep.PICK_AND_MOVE and not self.controller.gantry.isMoving:
                    self.controller.pick_card_and_move(from_pile, to_pile)
                elif step == self.ActionStep.PLACE_AND_MOVE and not self.controller.gantry.isMoving:
                    self.controller.place_card_and_move(from_pile, to_pile)
                elif step == self.ActionStep.FINISH and not self.controller.gantry.isMoving:
                    self.controller.process_and_finish(from_pile)
                moveDone = self.controller.gantry.update()
                if moveDone:
                    if step == self.ActionStep.INITIAL_MOVE:
                        nextStep = self.ActionStep.PICK_AND_MOVE
                    if step == self.ActionStep.PICK_AND_MOVE:
                        nextStep = self.ActionStep.PLACE_AND_MOVE
                    if step == self.ActionStep.PLACE_AND_MOVE:
                        nextStep = self.ActionStep.FINISH
                    if step == self.ActionStep.FINISH:
                        nextStep = self.ActionStep.INITIAL_MOVE
                    step = nextStep
            self.update_display()

        pygame.quit()
        sys.exit()

    def handle_click(self, mouse_pos):
        for button in self.buttons:
            if button["rect"].collidepoint(mouse_pos):
                self.handle_button_action(button["description"])

    def handle_mouse_motion(self, mouse_pos):
        self.hovered_pile = None
        for button in self.buttons:
            if button["rect"].collidepoint(mouse_pos):
                description = button["description"]
                if description.startswith("pile"):
                    xIndex, yIndex = map(int, description.strip("pile()").split(", "))
                    self.hovered_pile = (xIndex, yIndex)
                break

    def get_action_pile(self):
        from_pile, to_pile = self.pile_manager.get_action_piles()
        return (from_pile, to_pile)
        #self.controller.move_card(from_pile, to_pile)

    def handle_button_action(self, action):
        if action == "sort":
            self.sort = True
            print("Sorting started...")
        elif action == "stop":
            self.sort = False
            print("Sorting stopped...")
            # Stop sorting process
        else:
            print(action)
        a = 1

    def resize_image(self, image, max_width=None, max_height=None):
        """Resize the image while maintaining the aspect ratio."""
        original_width, original_height = image.size
        
        if max_width and max_height:
            aspect_ratio = original_width / original_height
            if aspect_ratio > 1:
                # Landscape orientation
                new_width = min(max_width, original_width)
                new_height = int(new_width / aspect_ratio)
                if new_height > max_height:
                    new_height = max_height
                    new_width = int(new_height * aspect_ratio)
            else:
                # Portrait orientation
                new_height = min(max_height, original_height)
                new_width = int(new_height * aspect_ratio)
                if new_width > max_width:
                    new_width = max_width
                    new_height = int(new_width / aspect_ratio)
        elif max_width:
            new_width = min(max_width, original_width)
            new_height = int((new_width / original_width) * original_height)
        elif max_height:
            new_height = min(max_height, original_height)
            new_width = int((new_height / original_height) * original_width)
        else:
            new_width, new_height = original_width, original_height
        
        resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        # Convert the resized PIL image to a format Pygame can use
        mode = resized_image.mode
        size = resized_image.size
        data = resized_image.tobytes()

        # Create a Pygame surface from the resized PIL image
        pygame_image = pygame.image.fromstring(data, size, mode)
        return pygame_image, size[0], size[1]
