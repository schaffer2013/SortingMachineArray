# gantry_system.py

class GantrySystem:
    def __init__(self, config):
        self.x_position = 0
        self.y_position = 0
        self.z_position = 0
        self.suctionCupState = False
        self.config = config
    
    def move_to(self, x, y):
        self.x_position = x
        self.y_position = y
        print(f"Moving to ({x}, {y})")
    
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
