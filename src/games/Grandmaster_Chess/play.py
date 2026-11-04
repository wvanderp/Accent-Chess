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


class Connector:
    human_color = chess.WHITE

    def __init__(self, client: RuntimeClient) -> None:
        self.client = client
        self.stage = "boot"
        self.previous: bytes | None = None
        self.skipped: set[bytes] = set()
        self.references: dict[str, Image.Image] = {}
        for name in ("game-menu", "new-game-confirm", "recognition"):
            with Image.open(Path(__file__).with_name(name + ".png")) as image:
                self.references[name] = image.convert("RGB")

    def keys(self, *names: str) -> None:
        for name in names:
            self.client.send("key", {"name": name})

    def reset(self) -> None:
        self.stage = "boot"
        self.previous = None
        self.skipped.clear()
        # The DOS software hand cursor is part of captured pixels. Parking it
        # outside the board prevents it being classified as an unknown piece.
        self.client.send("pointer", {"x": 630, "y": 470})
        self.keys("Escape")

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
        self.keys(*move.uci(), "Return")

    def advance(self, frame: Image.Image) -> None:
        """Grandmaster accepts the entire move in one input operation."""
