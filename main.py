from main_controller import MainController

if __name__ == "__main__":
    controller = MainController("config.json")
    controller.initialize()
    controller.run()
    #controller.start_sorting()