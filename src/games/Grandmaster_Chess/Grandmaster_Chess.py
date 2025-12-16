"""
Grandmaster Chess Game Connector.

Connector for the Grandmaster Chess 1993 DOS game emulator.
URL: https://archive.org/details/msdos_Grandmaster_Chess_1993
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
from hashlib import sha256

import pyautogui
pyautogui.FAILSAFE = False
ImageGrab.grab = partial(ImageGrab.grab, all_screens=True)

import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.resolve()))

from connector import GameConnector
from utils.nameToType import nameToPiece, nameToColor


def _copy_position_metadata(*, source: Board, target: Board) -> None:
    """Copy turn/castling/ep and counters from a trusted board to an observed board."""
    target.turn = source.turn
    target.castling_rights = source.castling_rights
    target.ep_square = source.ep_square
    target.halfmove_clock = source.halfmove_clock
    target.fullmove_number = source.fullmove_number


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


class GrandmasterChessConnector(GameConnector):
    """
    Game connector for Grandmaster Chess 1993 DOS game.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Grandmaster Chess",
            author="Accent-Chess",
            year="1993"
        )
        
        self.squareSize = (59, 55)
        self.classifier: Optional[GradientBoostingClassifier] = None
        self.board_region: Optional[tuple[int, int, int, int]] = None
        self._initialized = False
    
    def _load_classifier(self) -> None:
        """Load the piece classifier from training images."""
        images = []
        labels = []
        
        squares = pathlib.Path(__file__).parent.resolve() / "squares"
        for example in squares.glob("**/*.png"):
            try:
                with Image.open(example) as img:
                    images.append(prepare(img))
                labels.append(example.parent.name)
            except Exception as e:
                # Collected training images can occasionally be corrupt/partial.
                # Skip them rather than failing connector initialization.
                logging.warning(f"Skipping unreadable training image {example}: {e}")
                continue

        if not images:
            raise RuntimeError(f"No readable training images found in {squares}")
        
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
            logging.warning("Could not find Grandmaster Chess reference image")
            return False
        
        # Adjust base to capture the board (convert to int for pyautogui.screenshot)
        self.board_region = (
            int(base[0] - 491),  # left
            int(base[1] - 380),  # top
            472,                  # width
            440                   # height
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
            logging.error(f"Failed to initialize Grandmaster Chess: {e}")
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
        
        # Important: start from an empty board. Using Board() would include the
        # standard starting position and create "phantom" pieces when we set
        # detected pieces on top.
        board = Board(None)
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

        # Click on the game to enter its focus
        # click and hold on (-70 -135) the file menu
        # drag down to (-23 -200) and release
        
        return True
    
    def setup_position(self, board: Board) -> bool:
        """Set up a specific position in the emulator."""
        # Grandmaster Chess may not support arbitrary positions
        # For now, just verify the board matches
        current = self.get_board_state()
        return current.fen() == board.fen()
    
    def execute_move(self, move: Move) -> bool:
        """Execute a move on the emulator."""
        if not self.board_region:
            return False
        
        original_pos = pyautogui.position()
        
        screen_width, _ = pyautogui.size()
        pyautogui.moveRel(screen_width, 0)
        
        pyautogui.moveRel(
            self.board_region[0] - screen_width + 150,
            self.board_region[1] + 40,
        )
        
        pyautogui.click()
        time.sleep(0.2)  # Wait for click to register
        
        text = move.uci()
        logging.debug(f"Typing move: {text}")
        for char in text:
            pyautogui.keyDown(char)
            pyautogui.keyUp(char)
            time.sleep(0.05)  # Small delay between key presses
        
        time.sleep(0.1)
        pyautogui.keyDown('enter')
        pyautogui.keyUp('enter')
        
        # Wait for the move to be processed before pressing ESC
        time.sleep(0.5)
        
        pyautogui.press('esc')
        pyautogui.moveTo(original_pos)
        
        return True
    
    def wait_for_engine_move(self, expected_pre_state: Optional[Board] = None, timeout: float = 180.0) -> Optional[Move]:
        """Wait for the emulator's engine to make its move.
        
        Args:
            expected_pre_state: The expected board state before the engine moves.
                               If provided, we wait until the screen matches this state
                               before capturing pre_state.
            timeout: Maximum time to wait for the engine to move (seconds)
        """
        from utils.moveFromFens import moveFromFens
        
        # If we have an expected pre-state, wait until the screen stably matches it
        # This prevents race conditions where the engine moves too quickly
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
                        # Confirmed stable match
                        break
                else:
                    # Reset if we see a different state
                    stable_samples = 0
                time.sleep(0.2)
            else:
                logging.warning("Screen didn't stably match expected state, proceeding anyway")
        
        # Capture the current state as pre-state after confirming stability
        pre_state = self.get_board_state()
        if expected_pre_state is not None:
            _copy_position_metadata(source=expected_pre_state, target=pre_state)
        pre_fen = pre_state.fen().split()[0]
        logging.debug(f"Pre-state for engine move: {pre_state.fen()}")
        
        # Poll for board changes - wait until the board looks different
        start_time = time.time()
        stable_count = 0
        last_fen = None
        
        while time.time() - start_time < timeout:
            time.sleep(0.5)
            
            current = self.get_board_state()
            current_fen = current.fen().split()[0]
            
            # Check if board changed from pre-state
            if current_fen != pre_fen:
                # Board changed! Now wait for it to stabilize
                if current_fen == last_fen:
                    stable_count += 1
                    if stable_count >= 3:  # Stable for 1.5 seconds
                        post_state = current
                        # Copy metadata from pre_state, then flip the turn since a move was made
                        if expected_pre_state is not None:
                            _copy_position_metadata(source=pre_state, target=post_state)
                            post_state.turn = not pre_state.turn
                        logging.debug(f"Post-state after engine move: {post_state.fen()}")
                        
                        try:
                            move = moveFromFens(pre_state, post_state)
                            return move
                        except Exception as e:
                            logging.error(f"Failed to detect engine move: {e}")
                            return None
                else:
                    stable_count = 0
                    last_fen = current_fen
            else:
                stable_count = 0
                last_fen = current_fen
        
        logging.warning("Timeout waiting for engine move")
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
        # Grandmaster Chess doesn't support stopping mid-calculation
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
        
        # Save for training data collection (using hash to avoid duplicates)
        path = pathlib.Path(__file__).parent.resolve() / "squares" / str(piece_name[0])
        path.mkdir(parents=True, exist_ok=True)
        square.save(path / (sha256(square.tobytes()).hexdigest() + '.png'))
        
        if piece_name[0] == 'empty':
            return None
        return nameToPiece(piece_name[0])
    
    def _get_color(self, square: Image.Image) -> Color:
        """Determine the color of a piece on a square.
        
        Black pieces have a dark red/brown color (red channel >> green/blue).
        White pieces have only gray shades (red ≈ green ≈ blue).
        Board squares have wood textures that must be filtered out.
        """
        # Square colors to filter (white square, dark square, wood textures)
        filter_colors = [
            [255, 255, 255],  # White square
            [93, 85, 81],     # Dark gray square
            [81, 85, 93],     # Alternative dark square
            [93, 56, 20],     # Wood brown
            [95, 55, 24],     # Wood brown
            [60, 36, 12],     # Dark wood
            [125, 81, 36],    # Light wood
            [44, 0, 0],       # Border color (also black piece - handle carefully)
        ]
        
        image = np.array(square)
        colors = np.unique(image.reshape(-1, image.shape[-1]), axis=0)
        
        # Filter out board colors
        for filter_color in filter_colors:
            colors = colors[~np.all(colors == filter_color, axis=1)]
        
        if len(colors) == 0:
            return WHITE
        
        # Count how many red-biased colors we find
        # Black pieces have many distinctive red-brown shades
        red_biased_count = 0
        for color in colors:
            r, g, b = int(color[0]), int(color[1]), int(color[2])
            
            # Skip very dark colors (noise)
            if r < 25 and g < 25 and b < 25:
                continue
            
            # Skip colors that are close to board wood colors
            # Wood is typically tan/brown with higher green component
            if g > 30 and b > 10 and abs(r - g * 1.7) < 15:
                continue
                
            # Black piece: red channel significantly higher than green/blue
            # Typical black piece color: [69, 8, 4], [85, 20, 8], [73, 12, 4]
            if r > 50 and g < r * 0.3 and b < r * 0.2:
                red_biased_count += 1
        
        # Need multiple red-biased colors to confirm it's a black piece
        # This filters out occasional noise/artifacts
        if red_biased_count >= 2:
            return BLACK
        
        return WHITE


# Keep old class name for backwards compatibility
GrandmasterChess = GrandmasterChessConnector