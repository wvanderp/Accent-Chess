# virtual base class for the different games
# has a get_state method to return the state of the game
# a make_move method to make a move
# every game has a name and a year

class Game():
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
    
    # the game class is also in charge of implementing the UCI protocol

    