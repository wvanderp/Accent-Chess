"""Native-display piece recognition using game-owned, labeled reference frames.

The reference position labels templates only; observations always start empty.
Background removal and enclosed-hole filling make shape matching independent of
square color (C64 pieces use outlines on some squares and solid fills on others).
No guessed turn, castling rights or en-passant state is inferred from pixels.
"""

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import chess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


class RecognitionError(ValueError):
    """The frame does not contain a confidently readable supported board."""


@dataclass(frozen=True)
class Profile:
    game: str
    reference: Path
    region: tuple[int, int, int, int]
    backgrounds: tuple[tuple[int, int, int], tuple[int, int, int]]
    color_reader: Callable[[Image.Image, np.ndarray], chess.Color]


@dataclass
class Observation:
    placement: str
    crop: Image.Image
    overlay: Image.Image
    squares: list[dict[str, object]]


def square_box(region: tuple[int, int, int, int], file: int, row: int) -> tuple[int, int, int, int]:
    x, y, width, height = region
    return (round(x + file * width / 8), round(y + row * height / 8),
            round(x + (file + 1) * width / 8), round(y + (row + 1) * height / 8))


def silhouette(square: Image.Image, background: tuple[int, int, int]) -> np.ndarray:
    pixels = np.asarray(square.convert("RGB"), dtype=np.int16)
    mask = np.max(np.abs(pixels - background), axis=2) > 55
    # VICE's GTK display resamples edges. Exclude the grid/border fringe.
    mask[:2] = mask[-2:] = False
    mask[:, :2] = mask[:, -2:] = False
    mask = np.asarray(Image.fromarray(mask).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3)))
    outside = np.zeros_like(mask)
    pending: deque[tuple[int, int]] = deque([(0, 0)])
    while pending:
        y, x = pending.popleft()
        if not (0 <= y < mask.shape[0] and 0 <= x < mask.shape[1]):
            continue
        if mask[y, x] or outside[y, x]:
            continue
        outside[y, x] = True
        pending.extend(((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)))
    filled = ~outside
    return np.asarray(Image.fromarray(filled).resize((32, 32), Image.Resampling.NEAREST))


class BoardReader:
    """Read the calibrated, white-at-bottom 2D board; reject other layouts."""

    def __init__(self, profile: Profile) -> None:
        self.profile = profile
        self.templates: list[tuple[int, np.ndarray]] = []
        with Image.open(profile.reference) as reference:
            for row in (0, 1, 6, 7):
                for file in range(8):
                    square = reference.crop(square_box(profile.region, file, row))
                    piece = chess.Board().piece_at(chess.square(file, 7 - row))
                    assert piece is not None
                    mask = silhouette(square, profile.backgrounds[(file + row) % 2])
                    self.templates.append((piece.piece_type, mask))

    def read(self, frame: Image.Image) -> Observation:
        if frame.size != (640, 480):
            raise RecognitionError(f"Expected 640x480 runtime frame, got {frame.size}")
        frame = frame.convert("RGB")
        board = chess.Board(None)
        overlay = frame.copy()
        draw = ImageDraw.Draw(overlay)
        details: list[dict[str, object]] = []
        for row in range(8):
            for file in range(8):
                box = square_box(self.profile.region, file, row)
                square = frame.crop(box)
                background = self.profile.backgrounds[(file + row) % 2]
                pixels = np.asarray(square, dtype=np.int16)
                # Every supported square exposes background, including occupied ones.
                background_fraction = float(np.mean(np.max(np.abs(pixels - background), axis=2) < 30))
                if background_fraction < 0.3:
                    raise RecognitionError(f"Board/background not visible at {chess.square_name(chess.square(file, 7-row))}")
                mask = silhouette(square, background)
                symbol = "."
                score = 0.0
                if np.mean(mask) > 0.025:
                    matches = [(float(np.count_nonzero(mask ^ template) / max(1, np.count_nonzero(mask | template))), kind)
                               for kind, template in self.templates]
                    score, kind = min(matches)
                    if score > 0.38:
                        raise RecognitionError(f"Unknown piece at {chess.square_name(chess.square(file, 7-row))} (distance {score:.3f})")
                    color = self.profile.color_reader(square, mask)
                    piece = chess.Piece(kind, color)
                    board.set_piece_at(chess.square(file, 7 - row), piece)
                    symbol = piece.symbol()
                name = chess.square_name(chess.square(file, 7 - row))
                details.append({"square": name, "piece": symbol, "distance": round(score, 4),
                                "background_fraction": round(background_fraction, 4), "box": box})
                draw.rectangle(box, outline="#00aa00")
                draw.text((box[0] + 2, box[1] + 2), f"{name}:{symbol}", fill="#ff0000", stroke_width=1, stroke_fill="white")
        if len(board.pieces(chess.KING, chess.WHITE)) != 1 or len(board.pieces(chess.KING, chess.BLACK)) != 1:
            raise RecognitionError("Expected exactly one king of each color")
        x, y, width, height = self.profile.region
        return Observation(board.board_fen(), frame.crop((x, y, x + width, y + height)), overlay, details)
