"""
Chess 19xx Game Connector.

Connector for the Chess 19xx DOS game emulator.
URL: https://archive.org/details/Chess_19xx_-
"""

from functools import partial
from typing import Optional
from PIL import ImageGrab
from sklearn.ensemble import GradientBoostingClassifier
from chess import Board, Piece, PieceType, Color, WHITE, BLACK, parse_square, Move
import cv2 as cv
import numpy as np
from PIL import Image
import pathlib
import time
import logging

import pyautogui
pyautogui.FAILSAFE = False
ImageGrab.grab = partial(ImageGrab.grab, all_screens=True)

import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.resolve()))

from connector import GameConnector
from utils.nameToType import nameToPiece, nameToColor


def prepare(img: Image.Image) -> np.ndarray:
    """
    Resize, grayscale, normalize, and flatten image for classification.
    
    Args:
        img: PIL Image to prepare
        
    Returns:
        Flattened numpy array ready for classifier
    """
    img = img.resize((64, 48))
    img = np.array(img)
    img = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
    img = img / 255
    img = img.flatten()
    return img


class Chess19xxConnector(GameConnector):
    """
    Game connector for Chess 19xx DOS game.
    
    On-screen translations (Swedish -> English):
    - tid -> time
    - spel styrka -> game strength
    - gjorda drag -> moves made
    - forutsedda drag -> predicted moves
    - ladda nr? -> load number?
    
    Controls:
    - F2: play chess against itself
    - F3: set number of players
    - F4: change sides
    - F7: change background
    """

    def __init__(self) -> None:
        super().__init__(
            name="Chess 19xx",
            author="Accent-Chess",
            year="19xx"
        )
        
        self.squareSize = (64, 48)
        self.classifier: Optional[GradientBoostingClassifier] = None
        self.board_region: Optional[tuple[int, int, int, int]] = None
        self._initialized = False
    
    def _load_classifier(self) -> None:
        """Load the piece classifier from training images."""
        images = []
        labels = []
        
        squares = pathlib.Path(__file__).parent.resolve() / "squares"
        for example in squares.glob("**/*.png"):
            images.append(prepare(Image.open(example)))
            labels.append(example.parent.name)
        
        self.classifier = GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=1.0,
            max_depth=1,
            random_state=0
        )
        self.classifier.fit(images, labels)
    
    def _find_game_window(self) -> bool:
        """
        Find the game window on screen.
        
        Returns:
            True if the game window was found
        """
        reference_path = pathlib.Path(__file__).parent.resolve()
        base = pyautogui.locateOnScreen(str(reference_path) + '/reference.png')
        
        if base is None:
            logging.warning("Could not find Chess 19xx reference image")
            return False
        
        # Adjust base to capture the board
        self.board_region = (
            base[0] + 35,   # left
            base[1] + 3,    # top
            514,            # width
            385             # height
        )
        return True
    
    # =========================================================================
    # GameConnector Implementation
    # =========================================================================
    
    def initialize(self) -> bool:
        """Initialize the connector and find the emulator."""
        try:
            self._load_classifier()
            if self._find_game_window():
                self._initialized = True
                return True
            return False
        except Exception as e:
            logging.error(f"Failed to initialize Chess 19xx: {e}")
            return False
    
    def is_emulator_ready(self) -> bool:
        """Check if the emulator is found and ready."""
        if not self._initialized:
            return False
        return self._find_game_window()
    
    def get_board_state(self) -> Board:
        """Read and return the current board state from the emulator."""
        if not self.board_region:
            raise RuntimeError("Connector not initialized")
        
        screenshot = pyautogui.screenshot(region=self.board_region)
        
        board = Board()
        for x in range(8):
            for y in range(8):
                square_image = screenshot.crop((
                    x * self.squareSize[0],
                    y * self.squareSize[1],
                    (x + 1) * self.squareSize[0],
                    (y + 1) * self.squareSize[1]
                ))
                
                piece = self._get_piece(square_image)
                color = self._get_color(square_image)
                
                coordinate = ["a", "b", "c", "d", "e", "f", "g", "h"][x] + str(7 - y + 1)
                
                if piece is not None:
                    board.set_piece_at(parse_square(coordinate), Piece(piece, color))
        
        return board
    
    def setup_new_game(self) -> bool:
        """Set up a new game in the emulator."""
        # For now, assume the game is already set up
        # TODO: Implement menu navigation to start new game
        return True
    
    def setup_position(self, board: Board) -> bool:
        """Set up a specific position in the emulator."""
        # Chess 19xx may not support arbitrary positions
        # For now, just verify the board matches
        current = self.get_board_state()
        return current.fen() == board.fen()
    
    def execute_move(self, move: Move) -> bool:
        """Execute a move on the emulator."""
        if not self.board_region:
            return False
        
        original_pos = pyautogui.position()
        
        pyautogui.moveTo(0, 0)
        
        screen_width, _ = pyautogui.size()
        pyautogui.moveRel(screen_width, 0)
        
        pyautogui.moveRel(
            self.board_region[0] - screen_width + 75,
            self.board_region[1],
        )
        
        pyautogui.click()
        
        text = move.uci()
        for char in text:
            pyautogui.keyDown(char)
            pyautogui.keyUp(char)
        
        pyautogui.keyDown('enter')
        pyautogui.keyUp('enter')
        
        pyautogui.press('esc')
        pyautogui.moveTo(original_pos)
        
        return True
    
    def wait_for_engine_move(self, expected_pre_state: Optional[Board] = None) -> Optional[Move]:
        """Wait for the emulator's engine to make its move.
        
        Args:
            expected_pre_state: The expected board state before the engine moves.
                               If provided, we wait until the screen stably matches this state
                               before capturing pre_state to avoid race conditions.
        """
        from utils.moveFromFens import moveFromFens
        
        # If we have an expected pre-state, wait until the screen stably matches it
        if expected_pre_state is not None:
            expected_fen = expected_pre_state.fen().split()[0]  # Just piece placement
            max_wait = 10  # seconds
            start = time.time()
            stable_samples = 0
            required_stable_samples = 2  # Must match for at least 2 consecutive reads
            
            while time.time() - start < max_wait:
                current = self.get_board_state()
                current_fen = current.fen().split()[0]
                if current_fen == expected_fen:
                    stable_samples += 1
                    if stable_samples >= required_stable_samples:
                        break
                else:
                    stable_samples = 0
                time.sleep(0.2)
            else:
                logging.warning("Screen didn't stably match expected state, proceeding anyway")
        
        pre_state = self.get_board_state()
        
        # Wait for engine to finish thinking
        while self.is_engine_thinking():
            time.sleep(0.1)
        
        post_state = self.get_board_state()
        
        try:
            move = moveFromFens(pre_state, post_state)
            return move
        except Exception as e:
            logging.error(f"Failed to detect engine move: {e}")
            return None
    
    def is_engine_thinking(self) -> bool:
        """Check if the emulator's engine is currently calculating."""
        if not self.board_region:
            return False
        
        timer_region = (
            self.board_region[0] + 520,
            self.board_region[1] + 120,
            120,
            34
        )
        
        screenshot1 = pyautogui.screenshot(region=timer_region)
        time.sleep(1.5)
        screenshot2 = pyautogui.screenshot(region=timer_region)
        
        diff = cv.absdiff(np.array(screenshot1), np.array(screenshot2))
        
        # If timer is blinking, engine is thinking
        return not (np.sum(diff) > 10)
    
    def stop_calculation(self) -> bool:
        """Stop any ongoing calculation in the emulator."""
        # Chess 19xx doesn't support stopping mid-calculation
        return False
    
    def shutdown(self) -> None:
        """Gracefully shut down the emulator connection."""
        self._initialized = False
        self.board_region = None
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _get_piece(self, square: Image.Image) -> Optional[PieceType]:
        """Classify the piece on a square."""
        if not self.classifier:
            return None
        
        piece_name = self.classifier.predict([prepare(square)])
        
        # Save for training data collection
        path = pathlib.Path(__file__).parent.resolve() / "squares" / str(piece_name[0])
        path.mkdir(parents=True, exist_ok=True)
        square.save(path / (str(len(list(path.glob('*.png')))) + '.png'))
        
        if piece_name[0] == 'empty':
            return None
        return nameToPiece(piece_name[0])
    
    def _get_color(self, square: Image.Image) -> Color:
        """Determine the color of a piece on a square."""
        image = np.array(square)
        image = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
        
        color = image[35, 35]
        
        if color < 100:
            return BLACK
        else:
            return WHITE


# Keep old class name for backwards compatibility
Chess_19xx = Chess19xxConnector