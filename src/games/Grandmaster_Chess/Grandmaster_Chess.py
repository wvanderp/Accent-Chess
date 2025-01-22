from functools import partial
from PIL import ImageGrab
from sklearn.ensemble import GradientBoostingClassifier
from chess import Board, Piece, PIECE_TYPES, COLORS, WHITE, BLACK, parse_square, PIECE_NAMES, Move
import cv2 as cv
import numpy as np
from PIL import Image
import pathlib
import time
from hashlib import sha256

import pyautogui
pyautogui.FAILSAFE = False
ImageGrab.grab = partial(ImageGrab.grab, all_screens=True)

from Game import Game
from utils.nameToType import nameToPiece, nameToColor

# Resize, grayscale, normalize, and flatten image
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


class GrandmasterChess(Game):

    # URL: https://archive.org/details/msdos_Grandmaster_Chess_1993

    def __init__(self):
        super().__init__("Grandmaster Chess", "1993")

        self.squareSize = (59, 55)

        # Load the classifier
        images = []
        labels = []

        squares = pathlib.Path(__file__).parent.resolve() / "squares"
        for example in squares.glob("**/*.png"):
            images.append(prepare(Image.open(example)))
            labels.append(example.parent.name)

        self.classifier = GradientBoostingClassifier(n_estimators=100, learning_rate=1.0,
                                                     max_depth=1, random_state=0)

        self.classifier.fit(images, labels)

        # Get the base of the game
        referencePath = pathlib.Path(__file__).parent.resolve()
        base = pyautogui.locateOnScreen(str(referencePath) + '/reference.png')

        if base is None:
            raise Exception("Could not find the reference image")

        # Adjust base to capture the board
        self.board = (
            base[0] -491,  # left
            base[1] -380,  # top
            472,  # width
            440  # height
        )

    def get_state(self) -> Board:
        # Take a screenshot of the board
        screenshot = pyautogui.screenshot(
            region=self.board
        )

        # path = pathlib.Path(__file__).parent.resolve() / 'main.png'
        # screenshot = Image.open(path)

        # Find the pieces

        board = Board()
        for x in range(0, 8):
            for y in range(0, 8):
                squareImage = screenshot.crop((
                    x * self.squareSize[0],
                    y * self.squareSize[1],
                    (x + 1) * self.squareSize[0],
                    (y + 1) * self.squareSize[1]
                ))

                # Get the piece on the square
                piece = self.getPiece(squareImage)
                color = self.getColor(squareImage)

                # # Add the piece to the board
                coordinate = ["a", "b", "c", "d", "e",
                              "f", "g", "h"][x] + str(7 - y + 1)

                board.set_piece_at(parse_square(
                    coordinate), Piece(piece, color))

        return board

    def getPiece(self, square: Image) -> PIECE_TYPES:
        pieceName = self.classifier.predict([prepare(square)])

        # Make directory if it doesn't exist
        path = pathlib.Path(pathlib.Path(
            __file__).parent.resolve() / "squares/" / str(pieceName[0]))
        path.mkdir(parents=True, exist_ok=True)
        square.save(path / (sha256(square.tobytes()).hexdigest() + '.png'))

        if pieceName[0] == 'empty':
            return None
        return nameToPiece(pieceName[0])

    # Get the color of the piece
    def getColor(self, square: Image) -> COLORS:
        white = [255,255,255]
        black = [93, 85, 81]

        image = np.array(square)

        # Find the most common color not including white and black
        colors = np.unique(image.reshape(-1, image.shape[-1]), axis=0)
        colors = colors[~np.all(colors == white, axis=1)]
        colors = colors[~np.all(colors == black, axis=1)]

        # print(colors)

        if colors[0][0] == 44:
            return BLACK
        else:
            return WHITE


    def make_move(self, move: Move):
        originalMousePosition = pyautogui.position()

        # Move the mouse to the width of the screen
        screenWidth, _ = pyautogui.size()
        pyautogui.moveRel(screenWidth, 0)

        # Move the mouse on the board
        pyautogui.moveRel(
            self.board[0] - screenWidth + 150,  # left
            self.board[1] + 40,  # top
        )

        # Click to capture the mouse
        pyautogui.click()

        # Make the move
        # pyautogui.typewrite("d2d4", interval=0.5)
        text = move.uci()

        for char in text:
            pyautogui.keyDown(char)
            pyautogui.keyUp(char)
        
        pyautogui.keyDown('enter')
        pyautogui.keyUp('enter')


        # Press escape to uncapture the mouse
        pyautogui.press('esc')

        # Move mouse back to the original position
        pyautogui.moveTo(originalMousePosition)

    def isThinking(self) -> bool:
        # Check if the game is thinking
        # by checking if the timer is blinking

        timerRegion = (
                self.board[0] + 520,  # left
                self.board[1] + 120,  # top
                120,  # width
                34  # height
            )

        # Take a screenshot of the board
        screenshot = pyautogui.screenshot(
            region=timerRegion
        )

        screenshot.save('timer.png')

        # Sleep for 1.5 seconds
        time.sleep(1.5)

        # Take another screenshot
        screenshot2 = pyautogui.screenshot(
            region=timerRegion
        )

        # Compare the two screenshots
        diff = cv.absdiff(np.array(screenshot), np.array(screenshot2))

        # If the difference is greater than 10
        # the timer is blinking
        return not (np.sum(diff) > 10)