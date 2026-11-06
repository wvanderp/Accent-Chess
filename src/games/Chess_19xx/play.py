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
from .text import prefix_complete

PROMPT = (428, 323, 478, 335)


def prompt_mask(frame: Image.Image) -> np.ndarray:
    """Gray text against purple; this crop excludes clocks and move counters."""
    return np.asarray(frame.convert("RGB").crop(PROMPT))[:, :, 1] > 140


class Connector:
    human_color = chess.WHITE
    requires_board_before_reset = True
    move_timeout = 180

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
        self.submit_clock: bytes | None = None
        self.typed_prefix = ''
        self.previous_prefix = ''
        with Image.open(Path(__file__).with_name("recognition.png")) as image:
            self.reference = image.convert("RGB")

    def key(self, name: str) -> None:
        self.client.send("key", {"name": name, "delay_ms": 200, "window_title": "VICE (C64SC)"})

    def reset(self) -> None:
        self.keys_pending.clear()
        self.before = None
        self.awaiting_character = False
        self.current_key = None
        self.submit_clock = None
        self.typed_prefix = self.previous_prefix = ''
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
        if move.promotion and move.promotion != chess.QUEEN:
            raise ValueError("Chess 19xx underpromotion input has not yet been verified")
        # Queen promotion uses the normal coordinate request. PlaySession must
        # observe that exact promoted queen (and any legal reply); sending the
        # coordinates alone never acknowledges or completes a promotion.
        text = chess.square_name(move.from_square) + "-" + chess.square_name(move.to_square)
        self.keys_pending = ["minus" if key == "-" else key for key in text] + ["Return"]
        self.before = None
        self.awaiting_character = False
        self.confirmations = self.unchanged = self.retries = 0
        self.observed = None
        self.submit_clock = None
        self.typed_prefix = self.previous_prefix = ''

    def prefix_visible(self, frame: Image.Image, prefix: str) -> bool:
        return prefix_complete(frame, len(prefix))

    def diagnostics(self) -> str:
        return f'expected prefix={self.typed_prefix!r}, last key={self.current_key!r}, retries={self.retries}'

    def advance(self, frame: Image.Image) -> None:
        if not self.keys_pending:
            if self.current_key == 'Return' and self.before is not None:
                current = prompt_mask(frame)
                clock = self.clock_samples(frame)[0]
                # A retained full coordinate plus an advancing HUMAN clock
                # proves Return was missed. During engine search that clock
                # stops; never interrupt thinking based on elapsed time.
                if (np.any(current) and np.array_equal(current, self.before)
                        and self.submit_clock is not None and clock != self.submit_clock
                        and self.retries < 2):
                    self.key('Return')
                    self.retries += 1
                self.submit_clock = clock
            return
        current = prompt_mask(frame)
        if self.awaiting_character:
            if not self.prefix_visible(frame, self.typed_prefix):
                self.confirmations = 0
                if self.prefix_visible(frame, self.previous_prefix):
                    self.unchanged += 1
                    # The complete prior prefix proves the last key is absent.
                    # Cursor/redraw ink growth cannot acknowledge another key.
                    if self.unchanged >= 4 and self.retries < 2 and self.current_key is not None:
                        self.key(self.current_key)
                        self.retries += 1
                        self.unchanged = 0
                return
            self.confirmations += 1
            if self.confirmations < 2:
                return
        elif np.any(current):
            raise ValueError("Chess 19xx coordinate input is not empty; press New game")
        self.before = current
        name = self.keys_pending.pop(0)
        self.key(name)
        self.current_key = name
        if name != 'Return':
            self.previous_prefix = self.typed_prefix
            self.typed_prefix += '-' if name == 'minus' else name.upper()
        self.confirmations = self.unchanged = self.retries = 0
        self.observed = None
        self.awaiting_character = name != "Return"
        if name == 'Return':
            self.submit_clock = self.clock_samples(frame)[0]

    def clock_samples(self, frame: Image.Image) -> tuple[bytes, bytes]:
        """Isolate white/black clock digits, excluding names and move text.

        A changing crop on an unchanged confirmed board establishes the active
        side without a reset or assuming an engine search duration.
        """
        boxes = ((423, 201, 477, 212), (423, 185, 477, 196))
        return (frame.convert("RGB").crop(boxes[0]).tobytes(),
                frame.convert("RGB").crop(boxes[1]).tobytes())
