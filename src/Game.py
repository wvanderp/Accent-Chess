# Virtual base class for different game implementations.
# Provides:
# - get_state(): returns the current state of the game
# - make_move(): executes a move
# Each game instance has a name, year, and author.

class Game():
    # there should also be a part "documentation" in the code
    # Like where to find the game, and links to images of the game

    def __init__(self, name, year):
        self.name = name
        self.year = year
        self.author = "unknown"

    def get_state(self):
        pass

    def make_move(self, move):
        pass

    def isThinking(self):
        return False
    
    # This class is responsible for implementing the UCI protocol

