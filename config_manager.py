# config_manager.py

import json

class ConfigManager:
    def __init__(self, config_file):
        self.config = self.load_config(config_file)
    
    def load_config(self, config_file):
        with open(config_file, 'r') as file:
            return json.load(file)
    
    def get_config(self, key):
        return self.config.get(key)
