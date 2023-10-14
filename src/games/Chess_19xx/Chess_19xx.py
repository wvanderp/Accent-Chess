from functools import partial
from PIL import ImageGrab
from sklearn.ensemble import GradientBoostingClassifier
from chess import Board, Piece, PIECE_TYPES, COLORS, WHITE, BLACK, parse_square, PIECE_NAMES, Move
import cv2 as cv
import numpy as np
from PIL import Image
import pathlib
import time

import pyautogui
pyautogui.FAILSAFE = False
ImageGrab.grab = partial(ImageGrab.grab, all_screens=True)

from Game import Game
from utils.nameToType import nameToPiece, nameToColor

# resize, grayscale, normalize, and flatten image
def prepare(img: Image):
    img = img.resize((64, 48))
    img = np.array(img)
    img = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
    # img = cv.threshold(img, 150, 255, cv.THRESH_BINARY)[1]

    # if np.average(img) > 127:
    #     img = cv.bitwise_not(img)

    img = img / 255
    img = img.flatten()

    return img


class Chess_19xx(Game):

    # url: https://archive.org/details/Chess_19xx_-

    # onscreen translations
    # se -> en
    # tid | time
    # spel styrka | game strength
    # gjorda drag | moves made
    # forutsedda drag | predicted moves
    # ladda nr? | charge number?

    # controls
    # f2 play chess against it self
    # f3 set number of players
    # f4 change sides
    # f7 change background

    def __init__(self):
        super().__init__("Chess 19xx", "19xx")

        self.squareSize = (64, 48)

        # load the classifier
        images = []
        labels = []

        squares = pathlib.Path(__file__).parent.resolve() / "squares"
        for example in squares.glob("**/*.png"):
            images.append(prepare(Image.open(example)))
            labels.append(example.parent.name)

        self.classifier = GradientBoostingClassifier(n_estimators=100, learning_rate=1.0,
                                                     max_depth=1, random_state=0)

        self.classifier.fit(images, labels)

        # get the base of the game
        referencePath = pathlib.Path(__file__).parent.resolve()
        base = pyautogui.locateOnScreen(str(referencePath) + '/reference.png')

        if base is None:
            raise Exception("Could not find reference image")

        # adjust base to capture the board
        self.board = (
            base[0] + 35,  # left
            base[1] + 3,  # top
            514,  # width
            385  # height
        )

    def get_state(self) -> Board:

        # take a screenshot of the board
        screenshot = pyautogui.screenshot(
            region=self.board
        )

        # path = pathlib.Path(__file__).parent.resolve() / 'main.png'
        # screenshot = Image.open(path)

        # find the pieces

        board = Board()
        for x in range(0, 8):
            for y in range(0, 8):
                squareImage = screenshot.crop((
                    x * self.squareSize[0],
                    y * self.squareSize[1],
                    (x + 1) * self.squareSize[0],
                    (y + 1) * self.squareSize[1]
                ))

                # get the piece on the square
                piece = self.getPiece(squareImage)
                color = self.getColor(squareImage)

                # # add the piece to the board
                coordinate = ["a", "b", "c", "d", "e",
                              "f", "g", "h"][x] + str(7 - y + 1)

                # squareImage.save("squares/" + str(coordinate) + '.png')

                board.set_piece_at(parse_square(
                    coordinate), Piece(piece, color))

        return board

    pieceImages = {
        'pawn': "pawn.png",
        'rook': "rook.png",
        'knight': "knight.png",
        'bishop': "bishop.png",
        'queen': "queen.png",
        'king': "king.png"
    }

    def getPiece(self, square: Image) -> PIECE_TYPES:
        pieceName = self.classifier.predict([prepare(square)])

        # make directory if it doesn't exist
        path = pathlib.Path(pathlib.Path(
            __file__).parent.resolve() / "squares/" / str(pieceName[0]))
        path.mkdir(parents=True, exist_ok=True)
        square.save(path / (str(len(list(path.glob('*.png')))) + '.png'))

        if pieceName[0] == 'empty':
            return None
        return nameToPiece(pieceName[0])

    # get the color of the piece
    def getColor(self, square: Image) -> COLORS:
        image = np.array(square)

        # convert to black and white
        image = cv.cvtColor(image, cv.COLOR_BGR2GRAY)

        # sample the color at 35, 35
        color = image[35, 35]

        if color < 100:
            return BLACK
        else:
            return WHITE

    def make_move(self, move: Move):
        originalMousePosition = pyautogui.position()

        pyautogui.moveTo(0, 0)

        # move the mouse the with of the screen
        screenWidth, _ = pyautogui.size()
        pyautogui.moveRel(screenWidth, 0)

        # move the mouse on the board
        pyautogui.moveRel(
            self.board[0] - screenWidth + 75,  # left
            self.board[1],  # top
        )

        # click to capture the mouse
        pyautogui.click()

        # make the move
        # pyautogui.typewrite("d2d4", interval=0.5)
        text = move.uci()

        for char in text:
            pyautogui.keyDown(char)
            pyautogui.keyUp(char)
        
        pyautogui.keyDown('enter')
        pyautogui.keyUp('enter')


        # press escape to un capture the mouse
        pyautogui.press('esc')

        # move mouse back to original position
        pyautogui.moveTo(originalMousePosition)

    def isThinking(self) -> bool:
        # check if the game is thinking
        # by checking if the time is blinking

        timerRegion = (
                self.board[0] + 520,  # left
                self.board[1] + 120,  # top
                120,  # width
                34  # height
            )

        # take a screenshot of the board
        screenshot = pyautogui.screenshot(
            region=timerRegion
        )

        # sleep for 1.5 seconds
        time.sleep(1.5)

        # take another screenshot
        screenshot2 = pyautogui.screenshot(
            region=timerRegion
        )

        # compare the two screenshots
        diff = cv.absdiff(np.array(screenshot), np.array(screenshot2))

        # if the difference is greater than 10
        # the timer is blinking
        return not (np.sum(diff) > 10)