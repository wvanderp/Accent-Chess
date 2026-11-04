"""C64 Chess keyboard protocol, verified in VICE.

F1 clears the board, move counter and coordinate input (clocks are retained).
Moves use A2-A3 followed by Return. A 200ms X11 key sequence survives the C64
keyboard scan; the next character is gated on visible prompt growth rather
than sent in a burst. Engine completion is still determined by legal board
successors in PlaySession, never by the duration of a key press.
"""

from pathlib import Path

import chess
import numpy as np
from PIL import Image

from emulation.client import RuntimeClient

PROMPT = (428, 323, 478, 335)


def prompt_mask(frame: Image.Image) -> np.ndarray:
    """Gray text against purple; this crop excludes clocks and move counters."""
    return np.asarray(frame.convert("RGB").crop(PROMPT))[:, :, 1] > 140


class Connector:
    human_color = chess.WHITE

    def __init__(self, client: RuntimeClient) -> None:
        self.client = client
        self.keys_pending: list[str] = []
        self.before: np.ndarray | None = None
        self.awaiting_character = False
        self.current_key: str | None = None
        self.confirmations = 0
        self.unchanged = 0
        self.retries = 0
        self.observed: np.ndarray | None = None
        with Image.open(Path(__file__).with_name("recognition.png")) as image:
            self.reference = image.convert("RGB")

    def key(self, name: str) -> None:
        self.client.send("key", {"name": name, "delay_ms": 200, "window_title": "VICE (C64SC)"})

    def reset(self) -> None:
        self.keys_pending.clear()
        self.before = None
        self.awaiting_character = False
        self.current_key = None
        self.key("F1")

    def advance_reset(self, frame: Image.Image, placement: str | None) -> bool:
        if placement != chess.STARTING_BOARD_FEN or np.any(prompt_mask(frame)):
            return False
        # F1 also clears last move / move count. Requiring these markers avoids
        # accepting a starting-looking board during an incomplete reset redraw.
        for box in ((428, 144, 478, 162), (428, 263, 475, 277)):
            actual = np.asarray(frame.convert("RGB").crop(box), dtype=np.int16)
            expected = np.asarray(self.reference.crop(box), dtype=np.int16)
            if float(np.mean(np.abs(actual - expected))) > 3:
                return False
        return True

    def move(self, move: chess.Move) -> None:
        if move.promotion:
            raise ValueError("Chess 19xx promotion input has not yet been verified")
        text = chess.square_name(move.from_square) + "-" + chess.square_name(move.to_square)
        self.keys_pending = ["minus" if key == "-" else key for key in text] + ["Return"]
        self.before = None
        self.awaiting_character = False
        self.confirmations = self.unchanged = self.retries = 0
        self.observed = None

    def advance(self, frame: Image.Image) -> None:
        if not self.keys_pending:
            return
        current = prompt_mask(frame)
        if self.awaiting_character:
            assert self.before is not None
            # Each coordinate character adds text pixels. The game's input
            # routine can reposition the prefix, so pixel-for-pixel prefix
            # equality incorrectly stalled after A2-A in the live Tk test.
            # An unchanged prompt means a missed key: wait for the session's
            # deadline, rather than risk sending the remainder out of order.
            if np.count_nonzero(current) - np.count_nonzero(self.before) < 2:
                self.confirmations = 0
                if np.array_equal(current, self.before):
                    self.unchanged += 1
                    # A scan may still miss a physical key under host load.
                    # Retry only while the visible prefix remains unchanged,
                    # with a bound to avoid an unbounded stream of input.
                    if self.unchanged >= 4 and self.retries < 2 and self.current_key is not None:
                        self.key(self.current_key)
                        self.retries += 1
                        self.unchanged = 0
                return
            self.confirmations = self.confirmations + 1 if self.observed is not None and np.array_equal(current, self.observed) else 1
            self.observed = current
            if self.confirmations < 2:
                return
        elif np.any(current):
            raise ValueError("Chess 19xx coordinate input is not empty; press New game")
        self.before = current
        name = self.keys_pending.pop(0)
        self.key(name)
        self.current_key = name
        self.confirmations = self.unchanged = self.retries = 0
        self.observed = None
        self.awaiting_character = name != "Return"
