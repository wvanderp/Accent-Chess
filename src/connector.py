"""
Abstract base class for chess game connectors.

Each chess game implementation must extend GameConnector and implement
the abstract methods for each state. The UCIHandler manages state transitions
and calls these methods appropriately.
"""

from abc import ABC, abstractmethod
from typing import Optional
from chess import Board, Move, STARTING_FEN, WHITE, BLACK, Color
from playwright.sync_api import sync_playwright, Playwright, Browser, Page, BrowserContext, Frame, Locator

from state import GameState


class GameConnector(ABC):
    """
    Abstract base class that defines the interface for chess game connectors.
    
    Each game implementation must provide:
    - Game metadata (name, author, year)
    - State-specific behavior implementations
    - Board state reading capabilities
    - Move execution capabilities
    
    The connector acts as a bridge between the UCI protocol and a specific
    chess game emulator running in archive.org via Playwright.
    """
    
    def __init__(self, name: str, author: str, year: str) -> None:
        """
        Initialize the game connector.
        
        Args:
            name: Display name of the chess game
            author: Author/creator of the connector
            year: Year of the original game
        """
        self.name = name
        self.author = author
        self.year = year
        self._engine_color: Color = WHITE
        
        # Playwright browser instances
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        # Cached emulator canvas locator. Some archive.org emulators render the
        # DOS canvas inside nested iframes, so we resolve it dynamically.
        self._emulator_canvas: Optional[Locator] = None
    
    @property
    def engine_color(self) -> Color:
        """The color that the engine is playing as."""
        return self._engine_color
    
    @engine_color.setter
    def engine_color(self, color: Color) -> None:
        """Set the color that the engine is playing as."""
        self._engine_color = color
    
    @property
    @abstractmethod
    def archive_org_url(self) -> str:
        """
        The archive.org URL for this vintage chess game's emulator.
        
        Returns:
            The full URL to the archive.org page with the DOS emulator
        """
        pass
    
    @property
    def page(self) -> Optional[Page]:
        """Get the Playwright page instance."""
        return self._page
    
    # =========================================================================
    # Browser Management Methods
    # =========================================================================
    
    def launch_browser(self, headless: bool = False) -> bool:
        """
        Launch a Playwright browser instance and navigate to the archive.org emulator.
        
        Args:
            headless: Whether to run the browser in headless mode
            
        Returns:
            True if browser was launched successfully
        """
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=headless)
            self._context = self._browser.new_context()
            self._page = self._context.new_page()
            self._page.goto(self.archive_org_url, wait_until="domcontentloaded")
            self._emulator_canvas = None
            return True
        except Exception as e:
            import logging
            logging.error(f"Failed to launch browser: {e}")
            return False
    
    def close_browser(self) -> None:
        """Close the Playwright browser and release resources."""
        self._emulator_canvas = None
        if self._page:
            self._page.close()
            self._page = None
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    def get_emulator_canvas(self) -> Locator:
        """Return a Locator for the emulator's canvas element.

        Archive.org frequently embeds the emulator canvas inside an iframe.
        This method searches the main page and all frames for a visible canvas
        and caches the first match.
        """
        if self._emulator_canvas is not None:
            return self._emulator_canvas
        if not self._page:
            raise RuntimeError("Browser not launched")

        # Prefer a visible canvas on the top-level page.
        page_canvas = self._page.locator("canvas")
        try:
            if page_canvas.count() > 0 and page_canvas.first.is_visible():
                self._emulator_canvas = page_canvas.first
                return self._emulator_canvas
        except Exception:
            # Fall back to scanning frames.
            pass

        for frame in self._page.frames:
            try:
                canvas = frame.locator("canvas")
                if canvas.count() == 0:
                    continue
                if canvas.first.is_visible():
                    self._emulator_canvas = canvas.first
                    return self._emulator_canvas
            except Exception:
                continue

        # Cache nothing; callers can retry after navigation.
        raise RuntimeError("Could not locate emulator canvas (no visible <canvas> found)")

    def wait_for_emulator_canvas(self, timeout: float = 60.0) -> bool:
        """Wait until a visible emulator canvas can be located.

        Returns:
            True if found within the timeout, else False.
        """
        if not self._page:
            return False

        # Use Playwright-native waiting on the page, but also allow the canvas
        # to be inside iframes by periodically attempting resolution.
        deadline_ms = int(timeout * 1000)
        step_ms = 250
        waited_ms = 0
        while waited_ms < deadline_ms:
            try:
                _ = self.get_emulator_canvas()
                return True
            except Exception:
                pass

            try:
                self._page.wait_for_timeout(step_ms)
            except Exception:
                return False
            waited_ms += step_ms

        return False
    
    def take_screenshot(self, region: Optional[tuple[int, int, int, int]] = None) -> bytes:
        """
        Take a screenshot of the game board.
        
        Args:
            region: Optional tuple of (x, y, width, height) to capture a specific region.
                   If None, captures the full page.
        
        Returns:
            Screenshot as bytes (PNG format)
        """
        if not self._page:
            raise RuntimeError("Browser not launched")
        
        if region:
            x, y, width, height = region
            return self._page.screenshot(clip={"x": x, "y": y, "width": width, "height": height})
        return self._page.screenshot()
    
    def click_at(self, x: int, y: int) -> None:
        """
        Click at specific coordinates on the page.
        
        Args:
            x: X coordinate
            y: Y coordinate
        """
        if not self._page:
            raise RuntimeError("Browser not launched")
        self._page.mouse.click(x, y)
    
    def press_key(self, key: str) -> None:
        """
        Press a keyboard key.
        
        Args:
            key: Key to press (e.g., 'Enter', 'Escape', 'a', 'b', etc.)
        """
        if not self._page:
            raise RuntimeError("Browser not launched")
        self._page.keyboard.press(key)
    
    def type_text(self, text: str, delay: float = 50) -> None:
        """
        Type text character by character.
        
        Args:
            text: Text to type
            delay: Delay between key presses in milliseconds
        """
        if not self._page:
            raise RuntimeError("Browser not launched")
        self._page.keyboard.type(text, delay=delay)
    
    # =========================================================================
    # Initialization Methods
    # =========================================================================
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the connector and find the emulator.
        
        Called when transitioning from INITIALIZING to GAME_READY.
        Should locate the game window, set up any classifiers, etc.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def is_emulator_ready(self) -> bool:
        """
        Check if the emulator is found and ready.
        
        Returns:
            True if the emulator is detected and responsive
        """
        pass
    
    # =========================================================================
    # Game State Methods
    # =========================================================================
    
    @abstractmethod
    def get_board_state(self) -> Board:
        """
        Read and return the current board state from the emulator.
        
        Returns:
            A chess.Board object representing the current position
        """
        pass
    
    @abstractmethod
    def setup_new_game(self) -> bool:
        """
        Set up a new game in the emulator.
        
        Called during CONFIGURING state. Should:
        - Navigate menus if needed
        - Start a new game
        - Ensure board is in starting position
        
        Returns:
            True if setup was successful
        """
        pass
    
    @abstractmethod
    def setup_position(self, board: Board) -> bool:
        """
        Set up a specific position in the emulator.
        
        Args:
            board: The target position to set up
            
        Returns:
            True if the position was set up successfully
        """
        pass
    
    # =========================================================================
    # Move Execution Methods
    # =========================================================================
    
    @abstractmethod
    def execute_move(self, move: Move) -> bool:
        """
        Execute a move on the emulator.
        
        This is called when the engine needs to make a move (COMPUTING state)
        or when entering the opponent's move (OBSERVING -> COMPUTING transition).
        
        Args:
            move: The move to execute
            
        Returns:
            True if the move was executed successfully
        """
        pass
    
    @abstractmethod
    def wait_for_engine_move(self, expected_pre_state: Optional[Board] = None) -> Optional[Move]:
        """
        Wait for the emulator's engine to make its move.
        
        Called during COMPUTING state when the emulator is thinking.
        
        Args:
            expected_pre_state: The expected board state before the engine moves.
                               If provided, implementations should ensure the screen
                               stably matches this state before capturing the pre-move
                               position to avoid race conditions with fast engines.
        
        Returns:
            The move made by the emulator's engine, or None if interrupted
        """
        pass
    
    @abstractmethod
    def is_engine_thinking(self) -> bool:
        """
        Check if the emulator's engine is currently calculating.
        
        Returns:
            True if the engine is thinking
        """
        pass
    
    # =========================================================================
    # Pondering Methods (optional - default implementations provided)
    # =========================================================================
    
    def start_pondering(self, predicted_move: Move) -> bool:
        """
        Start pondering on a predicted opponent move.
        
        Override this if the game supports pondering.
        
        Args:
            predicted_move: The move predicted for the opponent
            
        Returns:
            True if pondering started successfully
        """
        return False  # Default: pondering not supported
    
    def stop_pondering(self) -> Optional[Move]:
        """
        Stop pondering and return any result.
        
        Returns:
            The best move found during pondering, or None
        """
        return None
    
    def supports_pondering(self) -> bool:
        """
        Check if this game connector supports pondering.
        
        Returns:
            True if pondering is supported
        """
        return False
    
    # =========================================================================
    # Control Methods
    # =========================================================================
    
    @abstractmethod
    def stop_calculation(self) -> bool:
        """
        Stop any ongoing calculation in the emulator.
        
        Returns:
            True if calculation was stopped successfully
        """
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """
        Gracefully shut down the emulator connection.
        
        Called during TERMINATING state. Should:
        - Save any necessary state
        - Close connections
        - Release resources
        """
        pass
    
    # =========================================================================
    # Error Recovery Methods
    # =========================================================================
    
    def attempt_recovery(self) -> bool:
        """
        Attempt to recover from an error state.
        
        Override this to provide game-specific error recovery.
        
        Returns:
            True if recovery was successful
        """
        return False
    
    def get_error_info(self) -> Optional[str]:
        """
        Get information about the current error.
        
        Returns:
            Error description string, or None if no error
        """
        return None
    
    # =========================================================================
    # Configuration Methods
    # =========================================================================
    
    def set_option(self, name: str, value: str) -> bool:
        """
        Set a game-specific option.
        
        Override to handle game-specific UCI options.
        
        Args:
            name: Option name
            value: Option value
            
        Returns:
            True if the option was set successfully
        """
        return False
    
    def get_options(self) -> dict[str, dict]:
        """
        Get available options for this game connector.
        
        Returns:
            Dictionary of option names to option definitions
        """
        return {}
