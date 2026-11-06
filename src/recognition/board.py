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
    template_shift: int = 0
    fill_scanlines: bool = False
    extra_templates: tuple[tuple[Path, str, int], ...] = ()
    shape_reader: Callable[[Image.Image, tuple[int, int, int], bool], np.ndarray] | None = None
    min_background_fraction: float = 0.3


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


def silhouette(square: Image.Image, background: tuple[int, int, int], fill_scanlines: bool = False) -> np.ndarray:
    pixels = np.asarray(square.convert("RGB"), dtype=np.int16)
    mask = np.max(np.abs(pixels - background), axis=2) > 55
    # VICE's GTK display resamples edges. Exclude the grid/border fringe.
    mask[:2] = mask[-2:] = False
    mask[:, :2] = mask[:, -2:] = False
    mask = np.asarray(Image.fromarray(mask).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3)))
    # Rasterized outlined sprites can have open diagonal seams after resampling.
    # Fill each occupied scanline between its outer edges before hole filling.
    mask = mask.copy()
    for line in mask if fill_scanlines else ():
        occupied = np.flatnonzero(line)
        if occupied.size:
            line[occupied[0]:occupied[-1] + 1] = True
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
        self.shape_reader = profile.shape_reader or silhouette
        self.templates: list[tuple[int, np.ndarray]] = []
        with Image.open(profile.reference) as reference:
            for row in (0, 1, 6, 7):
                for file in range(8):
                    square = reference.crop(square_box(profile.region, file, row))
                    piece = chess.Board().piece_at(chess.square(file, 7 - row))
                    assert piece is not None
                    mask = self.shape_reader(square, profile.backgrounds[(file + row) % 2], profile.fill_scanlines)
                    self.templates.append((piece.piece_type, mask))
        for path, name, kind in profile.extra_templates:
            position = chess.parse_square(name)
            file, row = chess.square_file(position), 7 - chess.square_rank(position)
            with Image.open(path) as reference:
                square = reference.crop(square_box(profile.region, file, row))
                mask = self.shape_reader(square, profile.backgrounds[(file + row) % 2], profile.fill_scanlines)
                self.templates.append((kind, mask))
        # GTK resamples C64 squares at fractional boundaries. Their silhouettes
        # can shift by 1-2 normalized pixels; without alignment a moved knight
        # on c6 was closer to the bishop template than to the knight template.
        variants = [(kind, np.roll(mask, (dy, dx), (0, 1)))
                    for kind, mask in self.templates
                    for dy in range(-profile.template_shift, profile.template_shift + 1)
                    for dx in range(-profile.template_shift, profile.template_shift + 1)]
        self.kinds = [kind for kind, _ in variants]
        self.masks = np.stack([mask for _, mask in variants])

    def read(self, frame: Image.Image, *, flipped: bool = False) -> Observation:
        if frame.size != (640, 480):
            raise RecognitionError(f"Expected 640x480 runtime frame, got {frame.size}")
        frame = frame.convert("RGB")
        board = chess.Board(None)
        overlay = frame.copy()
        draw = ImageDraw.Draw(overlay)
        details: list[dict[str, object]] = []
        for row in range(8):
            for file in range(8):
                # A game may exchange board ends while keeping sprites upright.
                # Remap squares, rather than rotating pixels/template shapes.
                position = chess.square(7 - file, row) if flipped else chess.square(file, 7 - row)
                box = square_box(self.profile.region, file, row)
                square = frame.crop(box)
                background = self.profile.backgrounds[(file + row) % 2]
                pixels = np.asarray(square, dtype=np.int16)
                # Every supported square exposes background, including occupied ones.
                background_fraction = float(np.mean(np.max(np.abs(pixels - background), axis=2) < 30))
                if background_fraction < self.profile.min_background_fraction:
                    raise RecognitionError(f"Board/background not visible at {chess.square_name(chess.square(file, 7-row))}")
                mask = self.shape_reader(square, background, self.profile.fill_scanlines)
                symbol = "."
                score = 0.0
                if np.mean(mask) > 0.025:
                    distances = (np.count_nonzero(mask ^ self.masks, axis=(1, 2)) /
                                 np.maximum(1, np.count_nonzero(mask | self.masks, axis=(1, 2))))
                    best = int(np.argmin(distances))
                    score, kind = float(distances[best]), self.kinds[best]
                    if score > 0.38:
                        raise RecognitionError(f"Unknown piece at {chess.square_name(chess.square(file, 7-row))} (distance {score:.3f})")
                    color = self.profile.color_reader(square, mask)
                    piece = chess.Piece(kind, color)
                    board.set_piece_at(position, piece)
                    symbol = piece.symbol()
                name = chess.square_name(position)
                details.append({"square": name, "piece": symbol, "distance": round(score, 4),
                                "background_fraction": round(background_fraction, 4), "box": box})
                draw.rectangle(box, outline="#00aa00")
                draw.text((box[0] + 2, box[1] + 2), f"{name}:{symbol}", fill="#ff0000", stroke_width=1, stroke_fill="white")
        if len(board.pieces(chess.KING, chess.WHITE)) != 1 or len(board.pieces(chess.KING, chess.BLACK)) != 1:
            raise RecognitionError(
                f"Expected exactly one king of each color; found "
                f"white={len(board.pieces(chess.KING, chess.WHITE))}, "
                f"black={len(board.pieces(chess.KING, chess.BLACK))}")
        x, y, width, height = self.profile.region
        return Observation(board.board_fen(), frame.crop((x, y, x + width, y + height)), overlay, details)
