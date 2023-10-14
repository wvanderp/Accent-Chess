#!/usr/bin/env pypy -u
# -*- coding: utf-8 -*-

# https://github.com/thomasahle/sunfish/blob/master/uci.py

from __future__ import print_function
from __future__ import division
import importlib
import re
import sys
import time
import logging
import argparse
import os

from chess import WHITE, BLACK, Board, STARTING_FEN

import Game
from games.Chess_19xx.Chess_19xx import Chess_19xx


class Unbuffered(object):
    def __init__(self, stream):
        self.stream = stream

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
        sys.stderr.write(data)
        sys.stderr.flush()

    def __getattr__(self, attr):
        return getattr(self.stream, attr)


def main(game: Chess_19xx):
    # Disable buffering

    os.remove('uci.log')
    logging.basicConfig(filename='uci.log', level=logging.DEBUG)
    out = Unbuffered(sys.stdout)

    def output(line):
        print(line, file=out)
        logging.debug(line)

    pos = Board(STARTING_FEN)

    logging.debug("Starting UCI")

    stack = [""]
    while True:
        if stack:
            command = stack.pop()
        else:
            command = input()

        logging.debug(f'>>> {command} ')

        # a switch with all the commands

        
        if command == 'quit':
            break

        elif command == 'uci':
            output('id name ' + game.name)
            output('id author ' + game.author)
            output('uciok')

        elif command == 'isready':
            output('readyok')

        elif command == 'ucinewgame':
            board = game.get_state()

            if board.fen() != STARTING_FEN:
                logging.debug('Board is not correct')
                logging.debug(board.fen())
            else :
                logging.debug('Board is correct')


        # syntax specified in UCI
        # position [fen  | startpos ]  moves  ....

        elif command.startswith('position startpos'):
            if command == 'position startpos':
                pos = Board(STARTING_FEN)
                continue
        
            moves = command.split('moves')[1].strip().split(" ")
            for move in moves:
                pos.push_san(move)

            

        elif command.startswith('go'):
            continue

        elif command.startswith('time'):
          continue

        elif command.startswith('otim'):
          continue

        else:
            pass


if __name__ == '__main__':
    game = Chess_19xx()
    main(game)
