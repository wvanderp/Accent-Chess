"""Grandmaster's local keyboard protocol, verified against DOSBox media.

F2 opens Game; Down selects its first entry, Start new Game. Return opens
the confirmation and a second Return accepts. Menu/dialog pixels gate each
step, so an input is never sent merely because a delay expired. Escape skips
boot screens. Coordinate notation (e2e4, Return) plays a move without mouse
scaling or pointer timing dependencies. Default mode is computer plays black.
"""

from pathlib import Path

import chess
import numpy as np
from PIL import Image

from emulation.client import RuntimeClient
from emulation.play import GameResigned


class Connector:
    human_color = chess.WHITE
    computer_colors = (chess.WHITE, chess.BLACK)

    def __init__(self, client: RuntimeClient) -> None:
        self.client = client
        self.stage = "boot"
        self.flipped = False
        self.input_clock: bytes | None = None
        self.announcement_pending = False
        self.announcement_observations = 0
        self.announcement_retries = 0
        self.announcement_kind = ''
        self.completed_notice_seen = False
        self.previous: bytes | None = None
        self.skipped: set[bytes] = set()
        self.references: dict[str, Image.Image] = {}
        for name in ("game-menu", "new-game-confirm", "recognition", "resignation", "mate-announcement", "game-completed", "rating-calculation"):
            with Image.open(Path(__file__).with_name(name + ".png")) as image:
                self.references[name] = image.convert("RGB")

    def keys(self, *names: str) -> None:
        for name in names:
            # At 12ms DOSBox can lose coordinate characters under host load.
            # This is key duration, never a substitute for UI acknowledgement.
            self.client.send("key", {"name": name, "delay_ms": 150})

    def reset(self) -> None:
        self.stage = "boot"
        self.previous = None
        self.skipped.clear()
        self.announcement_pending = False
        self.announcement_observations = self.announcement_retries = 0
        self.announcement_kind = ''
        self.completed_notice_seen = False
        # The DOS software hand cursor is part of captured pixels. Parking it
        # outside the board prevents it being classified as an unknown piece.
        self.client.send("pointer", {"x": 630, "y": 470})
        self.keys("Escape")

    def play_as(self, color: chess.Color) -> None:
        """Switching at the initial position starts White and reverses the ends.

        Verified against the DOS release: piece sprites stay upright, the
        human clock stays in the lower panel, and coordinate input stays in
        absolute algebraic notation. A display rotation alone is insufficient.
        """
        if color == chess.WHITE:
            self.keys("F2", "Down", "Down", "Return")
            self.client.send("pointer", {"x": 630, "y": 470})
            self.client.send("pointer", {"x": 0, "y": 0})
            self.human_color = chess.BLACK
            self.flipped = True

    def input_ready(self, frame: Image.Image, board: chess.Board) -> bool:
        """An advancing human clock gates input after the engine's redraw.

        Before the first move the clocks are stopped, so the confirmed reset
        supplies readiness. Later a legal board can precede keyboard readiness.
        """
        if board.ply() == 0:
            return True
        clock = frame.crop((530, 166, 600, 181)).tobytes()
        previous = self.input_clock
        self.input_clock = clock
        return previous is not None and clock != previous

    def matches(self, frame: Image.Image, name: str, box: tuple[int, int, int, int]) -> bool:
        actual = np.asarray(frame.convert("RGB").crop(box), dtype=np.int16)
        expected = np.asarray(self.references[name].crop(box), dtype=np.int16)
        return float(np.mean(np.abs(actual - expected))) < 3

    def advance_reset(self, frame: Image.Image, placement: str | None) -> bool:
        if self.stage == "boot":
            if placement is not None:
                self.keys("F2")
                self.stage = "menu"
            else:
                pixels = frame.tobytes()
                if pixels == self.previous and pixels not in self.skipped:
                    self.skipped.add(pixels)
                    self.keys("Escape")
                self.previous = pixels
        elif self.stage == "menu" and self.matches(frame, "game-menu", (120, 24, 260, 47)):
            self.keys("Down", "Return")
            self.stage = "confirm"
        elif self.stage == "confirm" and self.matches(frame, "new-game-confirm", (225, 197, 414, 281)):
            self.keys("Return")
            self.stage = "park"
        elif self.stage == "park" and not self.matches(frame, "new-game-confirm", (225, 197, 414, 281)):
            # The modal warps the DOS cursor independently of X11. Moving from
            # the far corner to the origin clamps the relative cursor outside
            # the board. Do this after the modal disappears, not after a delay.
            self.client.send("pointer", {"x": 0, "y": 0})
            self.stage = "board"
        elif self.stage == "board" and placement == chess.STARTING_BOARD_FEN:
            # Reject a retained placement while a modal is still covering the board.
            if not self.matches(frame, "new-game-confirm", (225, 197, 414, 281)):
                player_box = (510, 147, 620, 162)
                player = np.asarray(self.references["recognition"].crop(player_box), dtype=np.int16)
                upper = np.asarray(frame.convert("RGB").crop((510, 35, 620, 50)), dtype=np.int16)
                if not self.matches(frame, "recognition", player_box) or float(np.mean(np.abs(upper - player))) < 3:
                    raise ValueError("Set Game > Set Players to Computer plays BLACK, then press New game")
                self.stage = "ready"
                return True
        return False

    def move(self, move: chess.Move) -> None:
        self.input_clock = None
        self.keys(*move.uci(), "Return")

    def advance(self, frame: Image.Image) -> None:
        """A search forecast is an informational modal, never a game result."""
        completed = self.matches(frame, 'game-completed', (225, 197, 414, 224))
        self.completed_notice_seen |= completed
        notice: tuple[str, str] | None = None
        if self.rating_prompt(frame):
            notice = ('rating', 'Escape')
        elif self.completed_notice_seen and self.matches(frame, 'new-game-confirm', (225, 197, 414, 281)):
            notice = ('new-game', 'Escape')
        elif self.information_dialog(frame):
            notice = ('completed' if completed else 'information', 'Return')
        if notice is not None:
            kind, key = notice
            if not self.announcement_pending or kind != self.announcement_kind:
                self.keys(key)
                self.announcement_pending = True
                self.announcement_kind = kind
                self.announcement_observations = self.announcement_retries = 0
            else:
                self.announcement_observations += 1
                if self.announcement_observations >= 6 and self.announcement_retries < 2:
                    self.keys(key)
                    self.announcement_retries += 1
                    self.announcement_observations = 0
            return
        if self.announcement_pending:
            self.client.send('pointer', {'x': 630, 'y': 470})
            self.client.send('pointer', {'x': 0, 'y': 0})
            self.announcement_pending = False
            self.announcement_kind = ''
        if self.matches(frame, 'resignation', (225, 197, 414, 281)):
            raise GameResigned(not self.human_color)

    def information_dialog(self, frame: Image.Image) -> bool:
        """Acknowledge a GAME notification with a single centered OK button.

        The live White engine displayed 'Mate in 3 !' after Bd7, obscuring an
        otherwise legal board. Acknowledging it reveals the played move and
        lets normal legal-position tracking continue to actual checkmate.
        Text/depth is deliberately not interpreted as a result. Two-button
        decisions (new game/resignation) do not match this notification chrome.
        """
        return (any(self.matches(frame, name, (225, 197, 414, 224))
                    for name in ('mate-announcement', 'game-completed'))
                and self.matches(frame, 'mate-announcement', (285, 252, 352, 279)))

    def rating_prompt(self, frame: Image.Image) -> bool:
        """Decline native player-rating updates; tournament scores live outside DOS.

        GAME COMPLETED is followed by this optional CHESS RATING prompt. It
        must be cancelled before the final board can be recognized. No score
        is inferred from either dialog; normal legal-board validation remains.
        """
        return (self.matches(frame, 'rating-calculation', (157, 197, 483, 224))
                and self.matches(frame, 'rating-calculation', (166, 225, 474, 244)))

    def clock_samples(self, frame: Image.Image) -> tuple[bytes, bytes]:
        """Isolate white/black clock digits, excluding names and move text.

        A changing crop on an unchanged confirmed board establishes the active
        side without a reset or assuming an engine search duration.
        """
        boxes = ((530, 166, 600, 181), (530, 54, 600, 69))
        return (frame.convert("RGB").crop(boxes[0]).tobytes(),
                frame.convert("RGB").crop(boxes[1]).tobytes())
