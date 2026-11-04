"""
Abstract base class for Archive.org emulator browser automation.

This class extends GameConnector and handles all Playwright browser management
and Archive.org specific functionality for interacting with DOS emulators.
"""

from abc import abstractmethod
from typing import Optional
from playwright.sync_api import sync_playwright, Playwright, Browser, Page, BrowserContext, Locator
from chess import Color, WHITE
import logging

from GameConnector import GameConnector


class ArchiveOrgConnector(GameConnector):
    """
    Abstract base class for chess game connectors that use Archive.org emulators.
    
    This class extends GameConnector and provides:
    - Playwright browser lifecycle management
    - Archive.org emulator canvas detection
    - Screenshot and interaction utilities
    
    Subclasses must implement the archive_org_url property to specify
    which emulator to connect to, plus all abstract methods from GameConnector.
    """
    
    def __init__(self, name: str, author: str, year: str) -> None:
        """
        Initialize the Archive.org connector.
        
        Args:
            name: Display name of the chess game
            author: Author/creator of the connector
            year: Year of the original game
        """
        super().__init__(name, author, year)
        
        # Playwright browser instances
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        # Cached emulator canvas locator. Some archive.org emulators render the
        # DOS canvas inside nested iframes, so we resolve it dynamically.
        self._emulator_canvas: Optional[Locator] = None
    
    @property
    @abstractmethod
    def archive_org_url(self) -> str:
        """
        The archive.org URL for this emulator.
        
        Returns:
            The full URL to the archive.org page with the DOS emulator
        """
        pass
    
    @property
    def page(self) -> Optional[Page]:
        """Get the Playwright page instance."""
        return self._page
    
    # =========================================================================
    # Browser Lifecycle Methods
    # =========================================================================
    
    def launch_browser(self, headless: bool = False) -> bool:
        """
        Launch a Playwright browser instance and navigate to the archive.org emulator.
        
        This method launches the browser, navigates to the site, and then waits for the
        user to manually set up the emulator (e.g., clicking start button, navigating
        through menus, etc.). Once the user is ready, they should press Enter in the
        console to continue.
        
        Args:
            headless: Whether to run the browser in headless mode (Note: manual setup
                     requires headed mode, this parameter will be ignored)
            
        Returns:
            True if browser was launched successfully
        """
        try:
            # Always launch in headed mode for manual setup
            logging.info("Launching browser in headed mode for manual setup...")
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=False)
            self._context = self._browser.new_context()
            self._page = self._context.new_page()
            
            logging.info(f"Navigating to {self.archive_org_url}...")
            self._page.goto(self.archive_org_url, wait_until="domcontentloaded")
            logging.info("Page loaded.")
            
            # Wait for user to set up the site manually
            print("\n" + "="*80)
            print("MANUAL SETUP REQUIRED")
            print("="*80)
            print(f"The browser has navigated to: {self.archive_org_url}")
            print("\nPlease complete the following steps:")
            print("  1. Click the start button on the archive.org page")
            print("  2. Wait for the emulator to load")
            print("  3. Navigate through any initial menus in the game")
            print("  4. Set up the game to the point where it's ready to play")
            print("\nOnce you're ready, press ENTER in this console to continue...")
            print("="*80 + "\n")
            
            input()  # Wait for user to press Enter
            
            logging.info("User confirmed setup is complete, continuing...")
            
            # Give the page a moment to stabilize after user interaction
            self._page.wait_for_timeout(1000)

            self._emulator_canvas = None
            return True
        except Exception as e:
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

    # =========================================================================
    # Emulator Canvas Methods
    # =========================================================================

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

        logging.debug("Searching for emulator canvas...")

        # Prefer a visible canvas on the top-level page.
        page_canvas = self._page.locator("canvas")
        try:
            canvas_count = page_canvas.count()
            logging.debug(f"Found {canvas_count} canvas element(s) on main page")
            if canvas_count > 0:
                first_canvas = page_canvas.first
                is_visible = first_canvas.is_visible()
                bounding = first_canvas.bounding_box() if is_visible else None
                logging.debug(f"Main page canvas visible={is_visible}, bounding_box={bounding}")
                if is_visible and bounding and bounding.get("width", 0) > 50:
                    logging.info("Found visible canvas on main page")
                    self._emulator_canvas = first_canvas
                    return self._emulator_canvas
        except Exception as e:
            logging.debug(f"Error checking main page canvas: {e}")
            # Fall back to scanning frames.
            pass

        logging.debug(f"Scanning {len(self._page.frames)} frames for canvas...")
        for i, frame in enumerate(self._page.frames):
            try:
                frame_url = frame.url if frame.url else "about:blank"
                canvas = frame.locator("canvas")
                canvas_count = canvas.count()
                logging.debug(f"Frame {i} ({frame_url[:80]}): {canvas_count} canvas element(s)")
                if canvas_count == 0:
                    continue
                    
                first_canvas = canvas.first
                is_visible = first_canvas.is_visible()
                bounding = first_canvas.bounding_box() if is_visible else None
                logging.debug(f"Frame {i} canvas visible={is_visible}, bounding_box={bounding}")
                
                if is_visible and bounding and bounding.get("width", 0) > 50:
                    logging.info(f"Found visible canvas in frame {i}")
                    self._emulator_canvas = canvas.first
                    return self._emulator_canvas
            except Exception as e:
                logging.debug(f"Error checking frame {i}: {e}")
                continue

        # Cache nothing; callers can retry after navigation.
        logging.error("Could not locate emulator canvas (no visible <canvas> found in any frame)")
        raise RuntimeError("Could not locate emulator canvas (no visible <canvas> found)")

    def wait_for_emulator_canvas(self, timeout: float = 60.0) -> bool:
        """Wait until a visible emulator canvas can be located.

        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if found within the timeout, else False.
        """
        if not self._page:
            logging.error("Cannot wait for canvas: page not available")
            return False

        logging.info(f"Waiting for emulator canvas (timeout={timeout}s)...")

        # Use Playwright-native waiting on the page, but also allow the canvas
        # to be inside iframes by periodically attempting resolution.
        deadline_ms = int(timeout * 1000)
        step_ms = 500
        waited_ms = 0
        while waited_ms < deadline_ms:
            try:
                _ = self.get_emulator_canvas()
                logging.info(f"Canvas found after {waited_ms / 1000:.1f}s")
                return True
            except Exception as e:
                if waited_ms % 5000 == 0:  # Log every 5 seconds
                    logging.debug(f"Still waiting for canvas... ({waited_ms / 1000:.1f}s elapsed)")

            try:
                self._page.wait_for_timeout(step_ms)
            except Exception as e:
                logging.error(f"Page wait interrupted: {e}")
                return False
            waited_ms += step_ms

        logging.error(f"Canvas not found within {timeout}s timeout")
        return False

    # =========================================================================
    # Screenshot and Interaction Methods
    # =========================================================================
    
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
