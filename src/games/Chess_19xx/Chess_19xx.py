"""
Chess 19xx Game Connector.

Connector for the Chess 19xx DOS game emulator.
URL: https://archive.org/details/Chess_19xx_-
"""

from typing import Optional
from sklearn.ensemble import GradientBoostingClassifier
from chess import Board, Piece, PieceType, Color, WHITE, BLACK, parse_square, Move
import cv2 as cv
import numpy as np
from PIL import Image
import pathlib
import time
import logging
import io

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
    Uses Playwright to control the archive.org DOS emulator.
    
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

    # Archive.org URL for the emulator
    ARCHIVE_ORG_URL = "https://archive.org/details/Chess_19xx_-"

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
        
        # Canvas element coordinates (relative to the iframe/canvas)
        self._canvas_offset: tuple[int, int] = (0, 0)
    
    @property
    def archive_org_url(self) -> str:
        """The archive.org URL for Chess 19xx."""
        return self.ARCHIVE_ORG_URL
    
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
    
    def _wait_for_emulator_ready(self, timeout: float = 60.0) -> bool:
        """
        Wait for the archive.org emulator to be ready.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if emulator is ready
        """
        if not self._page:
            return False
        
        try:
            # Wait for the canvas element to be visible (the DOS emulator renders to canvas)
            self._page.wait_for_selector("canvas", timeout=timeout * 1000)
            
            # Click on the emulator to start it if needed
            canvas = self._page.locator("canvas")
            if canvas.is_visible():
                canvas.click()
                time.sleep(2)  # Give emulator time to initialize
            
            return True
        except Exception as e:
            logging.error(f"Emulator not ready: {e}")
            return False
    
    def _get_canvas_bounds(self) -> Optional[dict]:
        """Get the bounding box of the emulator canvas."""
        if not self._page:
            return None
        
        try:
            canvas = self._page.locator("canvas")
            return canvas.bounding_box()
        except Exception:
            return None
    
    def _take_board_screenshot(self) -> Optional[Image.Image]:
        """Take a screenshot of the game board area."""
        if not self._page:
            return None
        
        canvas_bounds = self._get_canvas_bounds()
        if not canvas_bounds:
            return None
        
        # Take screenshot of the canvas area
        screenshot_bytes = self._page.locator("canvas").screenshot()
        screenshot = Image.open(io.BytesIO(screenshot_bytes))
        
        # Crop to the board region if known
        if self.board_region:
            x, y, w, h = self.board_region
            screenshot = screenshot.crop((x, y, x + w, y + h))
        
        return screenshot
    
    # =========================================================================
    # GameConnector Implementation
    # =========================================================================
    
    def initialize(self) -> bool:
        """Initialize the connector, launch browser, and find the emulator."""
        try:
            self._load_classifier()
            
            # Launch browser and navigate to archive.org
            if not self.launch_browser(headless=False):
                return False
            
            # Wait for the emulator to be ready
            if not self._wait_for_emulator_ready():
                return False
            
            # Set default board region (may need calibration for specific setup)
            # These values are approximate based on the original implementation
            self.board_region = (35, 3, 514, 385)
            
            self._initialized = True
            return True
        except Exception as e:
            logging.error(f"Failed to initialize Chess 19xx: {e}")
            return False
    
    def is_emulator_ready(self) -> bool:
        """Check if the emulator is found and ready."""
        if not self._initialized or not self._page:
            return False
        
        try:
            canvas = self._page.locator("canvas")
            return canvas.is_visible()
        except Exception:
            return False
    
    def get_board_state(self) -> Board:
        """Read and return the current board state from the emulator."""
        screenshot = self._take_board_screenshot()
        if screenshot is None:
            raise RuntimeError("Could not capture board screenshot")
        
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
        # TODO: Implement menu navigation to start new game via Playwright
        return True
    
    def setup_position(self, board: Board) -> bool:
        """Set up a specific position in the emulator."""
        # Chess 19xx may not support arbitrary positions
        # For now, just verify the board matches
        current = self.get_board_state()
        return current.fen() == board.fen()
    
    def execute_move(self, move: Move) -> bool:
        """Execute a move on the emulator."""
        if not self._page:
            return False
        
        canvas_bounds = self._get_canvas_bounds()
        if not canvas_bounds:
            return False
        
        # Click on the canvas to ensure focus
        canvas_x = canvas_bounds["x"]
        canvas_y = canvas_bounds["y"]
        
        # Click in the input area (relative to board position)
        if self.board_region:
            input_x = canvas_x + self.board_region[0] + 75
            input_y = canvas_y + self.board_region[1]
            self._page.mouse.click(input_x, input_y)
        
        # Type the move in UCI notation
        text = move.uci()
        self.type_text(text, delay=50)
        
        self.press_key("Enter")
        
        self.press_key("Escape")
        
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
        
        # Poll for board changes - wait until the board looks different
        timeout = 180.0
        start_time = time.time()
        pre_fen = pre_state.fen().split()[0]
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
        """Check if the emulator's engine is currently calculating.
        
        Compares two screenshots of the timer region to detect animation/changes.
        """
        if not self._page or not self.board_region:
            return False
        
        try:
            # Timer region coordinates (relative to canvas)
            timer_x = self.board_region[0] + 520
            timer_y = self.board_region[1] + 120
            timer_width = 120
            timer_height = 34
            
            canvas = self._page.locator("canvas")
            
            # Take two screenshots with a delay
            screenshot1_bytes = canvas.screenshot(clip={
                "x": timer_x,
                "y": timer_y,
                "width": timer_width,
                "height": timer_height
            })
            time.sleep(1.5)
            screenshot2_bytes = canvas.screenshot(clip={
                "x": timer_x,
                "y": timer_y,
                "width": timer_width,
                "height": timer_height
            })
            
            screenshot1 = np.array(Image.open(io.BytesIO(screenshot1_bytes)))
            screenshot2 = np.array(Image.open(io.BytesIO(screenshot2_bytes)))
            
            diff = cv.absdiff(screenshot1, screenshot2)
            
            # If timer is blinking/changing, engine is thinking
            return not (np.sum(diff) > 10)
        except Exception as e:
            logging.error(f"Error checking engine thinking: {e}")
            return False
    
    def stop_calculation(self) -> bool:
        """Stop any ongoing calculation in the emulator."""
        # Chess 19xx doesn't support stopping mid-calculation
        return False
    
    def shutdown(self) -> None:
        """Gracefully shut down the emulator connection and browser."""
        self._initialized = False
        self.board_region = None
        self.close_browser()
    
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