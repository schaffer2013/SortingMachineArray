from main_controller import MainController
from ui_system import UISystem

if __name__ == "__main__":
    controller = MainController("config.json")
    ui = UISystem(controller)
    ui.initialize()
    ui.run()