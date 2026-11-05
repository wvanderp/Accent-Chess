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


class Connector:
    human_color = chess.WHITE
    reset_timeout = 240
    move_timeout = 180

    def __init__(self, client: RuntimeClient) -> None:
        self.client = client
        self.stage = "boot"
        self.input_stage = "idle"
        self.keys_pending: list[str] = []
        self.before: np.ndarray | None = None
        self.observed: bytes | None = None
        self.confirmations = 0
        self.reply_before: bytes | None = None
        self.view_retries = 0
        self.view_previous: bytes | None = None
        self.position = chess.Board()
        self.terminal_pending = False
        self.references: dict[str, Image.Image] = {}
        for name in ("menu", "playing", "new-game-confirm", "checkmate", "recognition"):
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

    def terminal_message(self, frame: Image.Image) -> bool:
        """CHECKMATE and STALEMATE share their final four character cells.

        The move list scrolls after eight rows. Search each vertical pixel
        phase for that suffix, rather than assuming the result is on row 24.
        """
        expected = np.asarray(self.references["checkmate"].crop((444, 222, 476, 229)))[:, :, 0] < 100
        pixels = np.asarray(frame.convert("RGB"))[:, :, 0] < 100
        return any(float(np.mean(pixels[y:y + 7, x:x + 32] != expected)) < 0.13
                   for x in (383, 444) for y in range(163, 227))

    def input_cursor(self, frame: Image.Image, *, black: bool = False) -> bool:
        """A blank move entry with its block cursor proves keyboard readiness."""
        pixels = np.asarray(frame.convert("RGB"))[:, :, 0] < 100
        offset = 61 if black else 0
        return any(np.count_nonzero(pixels[y:y + 7, 346 + offset:355 + offset]) > 40
                   and np.count_nonzero(pixels[y:y + 7, 355 + offset:400 + offset]) < 3
                   for y in range(163, 227))

    def set_position(self, board: chess.Board) -> None:
        self.position = board.copy()

    def show_board(self, frame: Image.Image) -> bool:
        if self.matches(frame, "recognition", (202, 136, 446, 145)):
            self.view_previous = None
            return True
        # At normal C64 speed F1 can leave the text view with CHOICES cleared.
        # Retry only after observing that the ready text view has not changed.
        if self.input_cursor(frame) or self.terminal_message(frame):
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
            self.stage = "confirm"
        elif self.stage == "confirm" and self.matches(frame, "new-game-confirm", (314, 325, 412, 338)):
            self.key("y")
            self.stage = "reset"
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
        self.before = None
        self.observed = None
        self.confirmations = 0
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
        if self.input_stage == "menu":
            if (not text_view or not self.matches(frame, "menu", (329, 236, 430, 247))
                    or not self.input_cursor(frame)):
                return
            self.input_stage = "typing"
            self.reply_before = frame.crop((405, 163, 461, 233)).tobytes()
        if self.input_stage == "typing":
            current = np.asarray(frame.convert("RGB").crop((343, 163, 404, 233)))[:, :, 0] < 100
            if self.before is not None:
                if np.count_nonzero(current) <= np.count_nonzero(self.before) + 1:
                    return
                pixels = current.tobytes()
                self.confirmations = self.confirmations + 1 if pixels == self.observed else 1
                self.observed = pixels
                if self.confirmations < 2:
                    return
            name = self.keys_pending.pop(0)
            self.before = current
            self.observed = None
            self.confirmations = 0
            self.key(name)
            if not self.keys_pending:
                self.input_stage = "hide"
        elif (self.input_stage == "hide" and text_view
              and ((frame.crop((405, 163, 461, 233)).tobytes() != self.reply_before
                    and self.input_cursor(frame))
                   or self.terminal_message(frame)
                   or (self.terminal_pending and self.input_cursor(frame, black=True)))):
            # F1 is ignored during search. Wait for the explicit prompt before
            # leaving text view, otherwise recognition would remain on a menu.
            self.key("F1")
            self.view_retries = 0
            self.view_previous = None
            self.input_stage = "show_board"
        elif self.input_stage == "show_board" and self.show_board(frame):
            self.input_stage = "idle"
