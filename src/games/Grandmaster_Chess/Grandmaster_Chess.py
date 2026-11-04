"""
Grandmaster Chess Game Connector.

Connector for the Grandmaster Chess 1993 DOS game emulator.
URL: https://archive.org/details/msdos_Grandmaster_Chess_1993
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
from hashlib import sha256
import io

import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.resolve()))

from archive_org_connector import ArchiveOrgConnector
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


class GrandmasterChessConnector(ArchiveOrgConnector):
    """
    Game connector for Grandmaster Chess 1993 DOS game.
    Uses Playwright to control the archive.org DOS emulator.
    """

    # Archive.org URL for the emulator
    ARCHIVE_ORG_URL = "https://archive.org/details/msdos_Grandmaster_Chess_1993"

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
        self._save_training_data = False  # Don't save screenshots during gameplay
        
        # Canvas element coordinates (relative to the iframe/canvas)
        self._canvas_offset: tuple[int, int] = (0, 0)
    
    @property
    def archive_org_url(self) -> str:
        """The archive.org URL for Grandmaster Chess 1993."""
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
            # The emulator canvas may be nested inside iframes on archive.org.
            if not self.wait_for_emulator_canvas(timeout=timeout):
                logging.error("Emulator not ready: canvas not found")
                return False

            # Click on the emulator to start it if needed (archive.org often requires a click to start).
            # Prefer Playwright-native waiting rather than fixed sleeps.
            canvas = self.get_emulator_canvas()
            if canvas.is_visible():
                canvas.click()
                self._page.wait_for_timeout(1500)

            return True
        except Exception as e:
            logging.error(f"Emulator not ready: {e}")
            return False
    
    def _get_canvas_bounds(self) -> Optional[dict]:
        """Get the bounding box of the emulator canvas."""
        if not self._page:
            return None
        
        try:
            canvas = self.get_emulator_canvas()
            return canvas.bounding_box()
        except Exception:
            return None
    
    def _take_board_screenshot(self) -> Optional[Image.Image]:
        """Take a screenshot of the game board area."""
        if not self._page:
            logging.error("Cannot take screenshot: page not available")
            return None
        
        try:
            canvas_bounds = self._get_canvas_bounds()
            if not canvas_bounds:
                logging.error("Cannot take screenshot: canvas bounds not available")
                return None
            
            logging.debug(f"Canvas bounds: {canvas_bounds}")
            
            # Take screenshot of the canvas area
            screenshot_bytes = self.get_emulator_canvas().screenshot()
            screenshot = Image.open(io.BytesIO(screenshot_bytes))
            
            logging.debug(f"Canvas screenshot size: {screenshot.size}")
            
            # Crop to the board region if known
            if self.board_region:
                x, y, w, h = self.board_region
                logging.debug(f"Cropping to board region: x={x}, y={y}, w={w}, h={h}")
                screenshot = screenshot.crop((x, y, x + w, y + h))
                logging.debug(f"Cropped board size: {screenshot.size}")
            
            return screenshot
        except Exception as e:
            logging.error(f"Failed to take board screenshot: {e}")
            return None
    
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
            # These values are approximate and may need adjustment
            self.board_region = (17, 60, 472, 440)
            
            self._initialized = True
            return True
        except Exception as e:
            logging.error(f"Failed to initialize Grandmaster Chess: {e}")
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
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                screenshot = self._take_board_screenshot()
                if screenshot is None:
                    raise RuntimeError("Could not capture board screenshot")
                
                # Save a debug screenshot on first attempt
                if attempt == 0:
                    debug_path = pathlib.Path(__file__).parent.resolve() / "debug_board.png"
                    screenshot.save(debug_path)
                    logging.debug(f"Saved debug board screenshot to {debug_path}")
                
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
                
                logging.debug(f"Successfully read board state (attempt {attempt + 1}/{max_retries})")
                return board
                
            except Exception as e:
                last_error = e
                logging.warning(f"Failed to read board state (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1 and self._page:
                    self._page.wait_for_timeout(500)  # Wait before retry
        
        raise RuntimeError(f"Failed to read board state after {max_retries} attempts: {last_error}")
    
    def setup_new_game(self) -> bool:
        """Set up a new game in the emulator."""
        # For now, assume the game is already set up
        # TODO: Implement menu navigation to start new game via Playwright clicks
        return True
    
    def setup_position(self, board: Board) -> bool:
        """Set up a specific position in the emulator."""
        # Grandmaster Chess may not support arbitrary positions
        # For now, just verify the board matches
        current = self.get_board_state()
        return current.fen() == board.fen()
    
    def execute_move(self, move: Move) -> bool:
        """Execute a move on the emulator."""
        if not self._page:
            logging.error("Cannot execute move: page not available")
            return False
        
        try:
            canvas_bounds = self._get_canvas_bounds()
            if not canvas_bounds:
                logging.error("Cannot execute move: canvas bounds not available")
                return False
            
            # Click on the canvas to ensure focus
            canvas_x = canvas_bounds["x"]
            canvas_y = canvas_bounds["y"]
            
            # Click in the input area (relative to board position)
            if self.board_region:
                input_x = canvas_x + self.board_region[0] + 150
                input_y = canvas_y + self.board_region[1] + 40
                self._page.mouse.click(input_x, input_y)
                self._page.wait_for_timeout(200)
            
            # Type the move in UCI notation
            text = move.uci()
            logging.info(f"Executing move: {text}")
            self.type_text(text, delay=50)
            
            self._page.wait_for_timeout(100)
            self.press_key("Enter")
            
            # Wait for the move to be processed before pressing ESC
            self._page.wait_for_timeout(500)
            
            self.press_key("Escape")
            
            logging.debug(f"Successfully sent move {text} to emulator")
            return True
            
        except Exception as e:
            logging.error(f"Failed to execute move {move.uci()}: {e}")
            return False
    
    def wait_for_engine_move(self, expected_pre_state: Optional[Board] = None, timeout: float = 180.0) -> Optional[Move]:
        """Wait for the emulator's engine to make its move.
        
        Args:
            expected_pre_state: The expected board state before the engine moves.
                               If provided, we wait until the screen matches this state
                               before capturing pre_state.
            timeout: Maximum time to wait for the engine to move (seconds)
        """
        from utils.moveFromFens import moveFromFens
        
        logging.info("Waiting for engine to make a move...")
        
        # If we have an expected pre-state, wait until the screen stably matches it
        # This prevents race conditions where the engine moves too quickly
        if expected_pre_state is not None:
            expected_fen = expected_pre_state.fen().split()[0]  # Just piece placement
            max_wait = 10  # seconds
            start = time.time()
            stable_samples = 0
            required_stable_samples = 2  # Must match for at least 2 consecutive reads
            
            logging.debug(f"Waiting for screen to match expected pre-state: {expected_fen}")
            
            while time.time() - start < max_wait:
                try:
                    current = self.get_board_state()
                    current_fen = current.fen().split()[0]
                    if current_fen == expected_fen:
                        stable_samples += 1
                        if stable_samples >= required_stable_samples:
                            # Confirmed stable match
                            logging.debug("Pre-state confirmed stable")
                            break
                    else:
                        # Reset if we see a different state
                        stable_samples = 0
                except Exception as e:
                    logging.debug(f"Error reading board state while waiting for pre-state: {e}")
                    stable_samples = 0
                
                if self._page is not None:
                    self._page.wait_for_timeout(300)
                else:
                    time.sleep(0.3)
            else:
                logging.warning("Screen didn't stably match expected state, proceeding anyway")
        
        # Capture the current state as pre-state after confirming stability
        try:
            pre_state = self.get_board_state()
            if expected_pre_state is not None:
                _copy_position_metadata(source=expected_pre_state, target=pre_state)
            pre_fen = pre_state.fen().split()[0]
            logging.debug(f"Pre-state for engine move: {pre_state.fen()}")
        except Exception as e:
            logging.error(f"Failed to capture pre-state: {e}")
            return None
        
        # Poll for board changes - wait until the board looks different
        start_time = time.time()
        stable_count = 0
        last_fen = None
        poll_count = 0
        
        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time
            
            # Use longer poll interval to reduce screenshot frequency
            poll_interval = 800  # milliseconds
            if self._page is not None:
                self._page.wait_for_timeout(poll_interval)
            else:
                time.sleep(poll_interval / 1000.0)
            
            poll_count += 1
            
            # Log progress every 10 seconds
            if poll_count % 12 == 0:  # 12 * 800ms ≈ 10s
                logging.info(f"Still waiting for engine move... ({elapsed:.1f}s elapsed)")
            
            try:
                current = self.get_board_state()
                current_fen = current.fen().split()[0]
            except Exception as e:
                logging.debug(f"Failed to read board state while waiting for engine move: {e}")
                continue
            
            # Check if board changed from pre-state
            if current_fen != pre_fen:
                # Board changed! Now wait for it to stabilize
                if current_fen == last_fen:
                    stable_count += 1
                    logging.debug(f"Board change detected, stability count: {stable_count}/3")
                    if stable_count >= 3:  # Stable for ~2.4 seconds
                        post_state = current
                        # Copy metadata from pre_state, then flip the turn since a move was made
                        if expected_pre_state is not None:
                            _copy_position_metadata(source=pre_state, target=post_state)
                            post_state.turn = not pre_state.turn
                        logging.info(f"Engine move detected! Post-state: {post_state.fen()}")
                        
                        try:
                            move = moveFromFens(pre_state, post_state)
                            logging.info(f"Detected engine move: {move.uci()}")
                            return move
                        except Exception as e:
                            logging.error(f"Failed to parse engine move from FEN change: {e}")
                            logging.error(f"Pre:  {pre_state.fen()}")
                            logging.error(f"Post: {post_state.fen()}")
                            return None
                else:
                    stable_count = 1
                    last_fen = current_fen
                    logging.debug(f"Board change detected (FEN: {current_fen[:20]}...)")
            else:
                stable_count = 0
                last_fen = current_fen
        
        logging.error(f"Timeout waiting for engine move after {timeout}s")
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
            
            canvas = self.get_emulator_canvas()
            
            # Take two screenshots with a delay
            screenshot1_bytes = canvas.screenshot(clip={
                "x": timer_x,
                "y": timer_y,
                "width": timer_width,
                "height": timer_height
            })
            self._page.wait_for_timeout(1500)
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
        # Grandmaster Chess doesn't support stopping mid-calculation
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
        
        # Save for training data collection (using hash to avoid duplicates)
        # Only save during training/debugging, not during normal gameplay
        if self._save_training_data:
            try:
                path = pathlib.Path(__file__).parent.resolve() / "squares" / str(piece_name[0])
                path.mkdir(parents=True, exist_ok=True)
                square.save(path / (sha256(square.tobytes()).hexdigest() + '.png'))
            except Exception as e:
                logging.debug(f"Failed to save training image: {e}")
        
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
