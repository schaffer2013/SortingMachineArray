# run.py

from main_controller import MainController

if __name__ == "__main__":
    controller = MainController("config.json")
    controller.initialize()
    controller.start_sorting()
