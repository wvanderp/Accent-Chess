from games.Grandmaster_Chess.Grandmaster_Chess import GrandmasterChess
from chess import COLORS, WHITE, BLACK, Move, STARTING_FEN
from PIL import Image
import numpy as np
import pathlib
from utils.moveFromFens import moveFromFens 
import time

if __name__ == '__main__':
    game = GrandmasterChess()

    # board = game.get_state()

    # print(board.fen())
    # if board.fen() != STARTING_FEN:
    #     print("ERROR: Board is not in starting position")

    # game.make_move(Move.from_uci("e2e4"))

    # game.isThinking()


    # -------------------

    # read in the move
    while True:
        move = input("Enter move: ")

        pre = game.get_state()

        try:
            game.make_move(pre.push_san(move))
        except:
            print("Invalid move")
            continue

        while game.isThinking():
            time.sleep(0.1)

        post = game.get_state()

        print(pre.fen())
        print(post.fen())

        move = moveFromFens(pre, post)

        print(pre.san(move))

    #  -----------------------------------------

    # board = game.get_state()
    # print(board.fen())

    # if(board.fen() != 'r1bqkb1r/pppppppp/5n2/8/3n4/2N2N2/PPP1PPPP/R1BQKB1R w KQkq - 0 1'):
    #     print('Board is not correct')

    

    # path = pathlib.Path(__file__).parent.resolve() / "squares" /  'f7.png'
    # image = Image.open(path)
    
    # Image.fromarray(prepare(image)).show()

    # print(game.getPiece(image))
