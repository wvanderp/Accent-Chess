"""Frame-gated menus and coordinate input for the C64 Chessmaster 2000.

F1 toggles the board/menu. From CHOICES, Ctrl+A opens PLAYING, Ctrl+B
requests NEW GAME and Y confirms it. Ctrl shortcuts are ignored in board view.
Move input is e2e4 (no hyphen or Return). Key duration serves the C64 keyboard
scanner only; PlaySession acknowledges moves through unique legal placements.
"""

from pathlib import Path

import chess
import numpy as np
from PIL import Image

from emulation.client import RuntimeClient
from .text import entry_matches


class Connector:
    human_color = chess.WHITE
    computer_colors = (chess.WHITE, chess.BLACK)
    reset_timeout = 240

    def __init__(self, client: RuntimeClient) -> None:
        self.client = client
        self.stage = "boot"
        self.input_stage = "idle"
        self.keys_pending: list[str] = []
        self.confirmations = 0
        self.reply_before: bytes | None = None
        self.view_retries = 0
        self.view_previous: bytes | None = None
        self.position = chess.Board()
        self.terminal_pending = False
        self.reset_previous: bytes | None = None
        self.reset_retries = 0
        self.reset_stable = 0
        self.input_row = 0
        self.typed_prefix = ''
        self.previous_prefix = ''
        self.input_unchanged = 0
        self.input_retries = 0
        self.references: dict[str, Image.Image] = {}
        for name in ("menu", "playing", "new-game-confirm", "checkmate", "recognition", "black-to-move"):
            with Image.open(Path(__file__).with_name(name + ".png")) as image:
                self.references[name] = image.convert("RGB")

    def key(self, name: str) -> None:
        self.client.send("key", {"name": name, "delay_ms": 200, "window_title": "VICE (C64SC)"})

    def matches(self, frame: Image.Image, name: str, box: tuple[int, int, int, int]) -> bool:
        actual = np.asarray(frame.convert("RGB").crop(box), dtype=np.int16)
        expected = np.asarray(self.references[name].crop(box), dtype=np.int16)
        return float(np.mean(np.abs(actual - expected))) < 3

    def reset(self) -> None:
        self.stage = "boot"
        self.input_stage = "idle"
        self.keys_pending.clear()
        self.reset_previous = None
        self.reset_retries = 0
        self.reset_stable = 0

    def retry_menu(self, frame: Image.Image, key: str) -> None:
        """The boot menu may be drawn before its keyboard loop is active.

        Retry only on an unchanged menu, with a finite bound. Merely seeing
        CHOICES once was insufficient in fresh, unattended container boots.
        """
        pixels = frame.crop((170, 148, 478, 338)).tobytes()
        self.reset_stable = self.reset_stable + 1 if pixels == self.reset_previous else 0
        if self.reset_stable >= 6 and self.reset_retries < 6:
            self.key(key)
            self.reset_retries += 1
            self.reset_previous = None
            self.reset_stable = 0
        else:
            self.reset_previous = pixels

    def terminal_message(self, frame: Image.Image) -> bool:
        """CHECKMATE and STALEMATE share their final four character cells.

        The move list scrolls after eight rows. Search each vertical pixel
        phase for that suffix, rather than assuming the result is on row 24.
        """
        expected = np.asarray(self.references["checkmate"].crop((444, 222, 476, 229)))[:, :, 0] < 100
        pixels = np.asarray(frame.convert("RGB"))[:, :, 0] < 100
        return any(float(np.mean(pixels[y:y + 7, x:x + 32] != expected)) < 0.13
                   # The left column's fractional GTK phase can move the
                   # suffix one pixel right, observed when Black delivered mate.
                   for x in (383, 384, 444, 445) for y in range(163, 227))

    def input_cursor(self, frame: Image.Image, *, black: bool = False) -> bool:
        """A blank move entry with its block cursor proves keyboard readiness."""
        return self.input_cursor_row(frame, black=black) is not None

    def input_cursor_row(self, frame: Image.Image, *, black: bool = False) -> int | None:
        pixels = np.asarray(frame.convert("RGB"))[:, :, 0] < 100
        offset = 61 if black else 0
        candidates = [(int(np.count_nonzero(pixels[y:y + 7, 346 + offset:355 + offset])), y)
                      for y in range(163, 227)
                      if np.count_nonzero(pixels[y:y + 7, 355 + offset:400 + offset]) < 3]
        count, row = max(candidates, key=lambda item: (item[0], -item[1]), default=(0, 0))
        return row if count > 40 else None

    def prefix_visible(self, frame: Image.Image, prefix: str) -> bool:
        variants = [prefix]
        if len(prefix) >= 2:
            # The input cursor skips a separator cell after the source square;
            # the hyphen may be blank until the destination is complete.
            variants.append(prefix[:2] + ' ' + prefix[2:])
            variants.append(prefix[:2] + '-' + prefix[2:])
        # The filled cursor and thinner glyphs cross GTK's intensity threshold
        # on different scanlines. At the seventh input row the glyph baseline
        # was one pixel below the cursor's first full row (live C2-C3 case).
        return any(entry_matches(frame, text, row, black=self.human_color == chess.BLACK)
                   for text in variants for row in (self.input_row - 1, self.input_row, self.input_row + 1))

    def diagnostics(self) -> str:
        return f'input={self.input_stage}, expected prefix={self.typed_prefix!r}, retries={self.input_retries}'

    def set_position(self, board: chess.Board) -> None:
        self.position = board.copy()

    def play_as(self, color: chess.Color) -> None:
        """Return at an empty input cursor swaps sides, without rotating pieces.

        Verified with the original C64 media and documented in its manual.
        F1 is ignored during thinking, so the black input cursor gates the
        return to board view after White's opening move.
        """
        if color == chess.WHITE:
            self.human_color = chess.BLACK
            self.input_stage = "switch_menu"
            self.reset_previous = None
            self.reset_retries = self.reset_stable = 0
            self.key("F1")

    def show_board(self, frame: Image.Image) -> bool:
        if self.matches(frame, "recognition", (202, 136, 446, 145)):
            self.view_previous = None
            return True
        # At normal C64 speed F1 can leave the text view with CHOICES cleared.
        # Retry only after observing that the ready text view has not changed.
        if self.input_cursor(frame, black=self.human_color == chess.BLACK) or self.terminal_message(frame):
            pixels = frame.crop((300, 148, 479, 248)).tobytes()
            if pixels == self.view_previous and self.view_retries < 3:
                self.key("F1")
                self.view_retries += 1
                self.view_previous = None
            else:
                self.view_previous = pixels
        return False

    def advance_reset(self, frame: Image.Image, placement: str | None) -> bool:
        text_view = self.matches(frame, "menu", (320, 148, 460, 159))
        if self.stage == "boot":
            if text_view:
                self.key("ctrl+a")
                self.stage = "playing"
            elif placement is not None:
                self.key("F1")
                self.stage = "menu"
        elif self.stage == "menu" and text_view:
            self.key("ctrl+a")
            self.stage = "playing"
        elif self.stage == "playing" and self.matches(frame, "playing", (171, 260, 290, 320)):
            if not self.matches(frame, "playing", (306, 310, 465, 319)):
                raise ValueError("Set Playing > Who plays to YOU vs. CHESSMASTER before New game")
            self.key("ctrl+b")
            self.reset_previous = None
            self.reset_retries = 0
            self.stage = "confirm"
        elif self.stage == "playing" and text_view:
            self.retry_menu(frame, "ctrl+a")
        elif self.stage == "confirm" and self.matches(frame, "new-game-confirm", (314, 325, 412, 338)):
            self.key("y")
            self.stage = "reset"
        elif self.stage == "confirm" and text_view:
            self.retry_menu(frame, "ctrl+b")
        elif (self.stage == "reset" and text_view
              and not self.matches(frame, "new-game-confirm", (314, 325, 412, 338))
              and self.matches(frame, "menu", (320, 163, 460, 190))):
            self.key("F1")
            self.view_retries = 0
            self.view_previous = None
            self.stage = "board"
        elif self.stage == "board":
            if self.show_board(frame) and placement == chess.STARTING_BOARD_FEN:
                self.stage = "ready"
                return True
        return False

    def move(self, move: chess.Move) -> None:
        # Promotion stays at the input cursor after four coordinates. Its fifth
        # letter (Q/R/B/N) submits the move; ordinary moves submit after four.
        self.keys_pending = list(move.uci())
        pending = self.position.copy()
        pending.push(move)
        self.terminal_pending = pending.is_game_over()
        self.confirmations = 0
        self.typed_prefix = ''
        self.previous_prefix = ''
        self.input_unchanged = self.input_retries = 0
        self.reset_previous = None
        self.reset_retries = self.reset_stable = 0
        self.input_stage = "menu"
        self.key("F1")

    def advance(self, frame: Image.Image) -> None:
        """The reply board may finish drawing before the keyboard is ready.

        Enter moves in the text view, gated on WHITE TO MOVE and visible input
        growth. Return to board view only after the move was submitted.
        """
        if self.input_stage == "idle":
            return
        text_view = self.matches(frame, "menu", (320, 148, 460, 159))
        human_black = self.human_color == chess.BLACK
        offset = 61 if human_black else 0
        if self.input_stage == "switch_menu":
            if text_view and self.input_cursor(frame):
                self.key("Return")
                self.input_stage = "switch_wait"
            elif self.matches(frame, "recognition", (202, 136, 446, 145)):
                self.retry_menu(frame, "F1")
            return
        if self.input_stage == "switch_wait":
            if self.input_cursor(frame, black=True):
                self.key("F1")
                self.view_retries = 0
                self.view_previous = None
                self.input_stage = "show_board"
            return
        if self.input_stage == "menu":
            turn_reference = "black-to-move" if human_black else "menu"
            if not text_view and self.matches(frame, "recognition", (202, 136, 446, 145)):
                # The board can finish drawing just before the F1 handler
                # resumes. Retry only while that same board remains visible.
                self.retry_menu(frame, "F1")
            if (not text_view or not self.matches(frame, turn_reference, (329, 236, 430, 247))
                    or not self.input_cursor(frame, black=human_black)):
                return
            self.input_stage = "typing"
            row = self.input_cursor_row(frame, black=human_black)
            assert row is not None
            self.input_row = row
            self.reply_before = frame.crop((405 - offset, 163, 461 - offset, 233)).tobytes()
        if self.input_stage == "typing":
            if self.typed_prefix:
                if not self.prefix_visible(frame, self.typed_prefix):
                    self.confirmations = 0
                    # Retry only if the exact prior prefix plus its cursor
                    # proves the last character was missed. A cursor redraw
                    # alone cannot acknowledge a key or advance the queue.
                    if self.prefix_visible(frame, self.previous_prefix):
                        self.input_unchanged += 1
                        if self.input_unchanged >= 6 and self.input_retries < 2:
                            self.key(self.typed_prefix[-1].lower())
                            self.input_retries += 1
                            self.input_unchanged = 0
                    return
                self.confirmations += 1
                if self.confirmations < 2:
                    return
            name = self.keys_pending.pop(0)
            self.previous_prefix = self.typed_prefix
            self.typed_prefix += name.upper()
            self.input_unchanged = self.input_retries = 0
            self.confirmations = 0
            self.key(name)
            if not self.keys_pending:
                self.input_stage = "hide"
        elif (self.input_stage == "hide" and text_view
              and ((frame.crop((405 - offset, 163, 461 - offset, 233)).tobytes() != self.reply_before
                    and self.input_cursor(frame, black=human_black))
                   or self.terminal_message(frame)
                   or (self.terminal_pending and self.input_cursor(frame, black=not human_black)))):
            # F1 is ignored during search. Wait for the explicit prompt before
            # leaving text view, otherwise recognition would remain on a menu.
            self.key("F1")
            self.view_retries = 0
            self.view_previous = None
            self.input_stage = "show_board"
        elif self.input_stage == "show_board" and self.show_board(frame):
            self.input_stage = "idle"
