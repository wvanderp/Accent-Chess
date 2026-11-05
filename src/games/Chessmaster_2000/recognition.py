"""Native VICE 2D board: gold human pieces, blue computer pieces.

The selected white king has a gold surround, so color is sampled from sprite
pixels rather than from the square background or cursor position.
"""

from pathlib import Path

import chess
import numpy as np
from PIL import Image, ImageFilter

from recognition.board import Profile


def piece_color(square: Image.Image, mask: np.ndarray) -> chess.Color:
    pixels = np.asarray(square.convert("RGB"), dtype=np.int16)
    gold = (pixels[:, :, 0] > 130) & (pixels[:, :, 0] - pixels[:, :, 2] > 60)
    return chess.WHITE if np.count_nonzero(gold) > 20 else chess.BLACK


def piece_shape(square: Image.Image, background: tuple[int, int, int], fill_scanlines: bool) -> np.ndarray:
    """Retain interior ink: filled silhouettes confuse this game's rook/bishop.

    Both colors use black line art, with blue or gold interiors. Reading the
    shared ink preserves the bishop's diagonal and the rook's crenellations.
    """
    pixels = np.asarray(square.convert("RGB"), dtype=np.int16)
    ink = (pixels[:, :, 1] < 65) & (pixels[:, :, 2] < 110)
    # A two-pixel fringe clips a moved queen's crown at some GTK phases.
    ink[:1] = ink[-1:] = False
    ink[:, :1] = ink[:, -1:] = False
    normalized = Image.fromarray(ink).resize((32, 32), Image.Resampling.NEAREST)
    return np.asarray(normalized.filter(ImageFilter.MaxFilter(3)))


PROFILE = Profile("chessmaster2000", Path(__file__).with_name("recognition.png"),
                  (202, 146, 243, 178), ((213, 213, 213), (62, 81, 240)),
                  piece_color, template_shift=2, shape_reader=piece_shape)
