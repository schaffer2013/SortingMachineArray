# gantry_system.py

import math

def pythagorean_distance(point1, point2):
    x1, y1 = point1
    x2, y2 = point2
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
class GantrySystem:
    def __init__(self, config, simulated = False):
        self.x_position = 0
        self.y_position = 0
        self.z_position = 0
        self.suctionCupState = False
        self.config = config
        self.active_card = None
        self.isMoving = False

        self.fps = 10
        self.reset()
    
    def pickCard(self, card):
        self.active_card = card
    
    def placeCard(self):
        c = self.active_card.copy()
        self.active_card = None
        return c

    def reset(self):
        self.total_dist = 0

    def move_to(self, x, y, immediateMove = True):
        pt1 = (self.x_position, self.y_position)
        pt2 = (x, y)
        self.total_dist += pythagorean_distance(pt1, pt2)
        if immediateMove:
            self.x_position = x
            self.y_position = y
        else:
            self.targetX = x
            self.deltaX = (self.targetX - self.x_position) / self.fps
            self.targetY = y
            self.deltaY = (self.targetY - self.y_position) / self.fps
            self.isMoving = True
        print(f"Moving to ({x}, {y})")

    def update(self) -> bool:
        if abs(self.targetX - self.x_position) < abs(self.deltaX):
            self.x_position = self.targetX
        else:
            self.x_position += self.deltaX
        if abs(self.targetY - self.y_position) < abs(self.deltaY):
            self.y_position = self.targetY
        else:
            self.y_position += self.deltaY
        
        if self.x_position == self.targetX and self.y_position == self.targetY:
            self.isMoving = False
            return True
        return False
    
    def lower_z(self):
        self.z_position = self.config.get_config("z_lowered_position")
        print("Lowering Z axis")
    
    def raise_z(self):
        self.z_position = self.config.get_config("z_raised_position")
        print("Raising Z axis")
    
    def activate_suction(self):
        self.suctionCupState = True
        print("Suction cup activated")
    
    def deactivate_suction(self):
        self.suctionCupState = False
        print("Suction cup deactivated")
