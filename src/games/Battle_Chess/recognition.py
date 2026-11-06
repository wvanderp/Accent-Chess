"""EmuTOS/Hatari 2D board. Red is white; blue is black.

Only saturated red/blue sprite pixels form silhouettes, excluding the green
board bevels. The 3D board and animated transition must be rejected.
"""

from pathlib import Path

import chess
import numpy as np
from PIL import Image

from recognition.board import Profile


def sprite(square: Image.Image, background: tuple[int, int, int], fill: bool) -> np.ndarray:
    pixels = np.asarray(square.convert("RGB"), dtype=np.int16)
    mask = ((pixels[:, :, 0] > pixels[:, :, 1] + 40) |
            (pixels[:, :, 2] > pixels[:, :, 1] + 40))
    return np.asarray(Image.fromarray(mask).resize((32, 32), Image.Resampling.NEAREST))


def piece_color(square: Image.Image, mask: np.ndarray) -> chess.Color:
    pixels = np.asarray(square.convert("RGB"), dtype=np.int16)
    red = (pixels[:, :, 0] > pixels[:, :, 1] + 40) & (pixels[:, :, 0] > pixels[:, :, 2] + 40)
    blue = (pixels[:, :, 2] > pixels[:, :, 1] + 40) & (pixels[:, :, 2] > pixels[:, :, 0] + 40)
    return bool(np.count_nonzero(red) > np.count_nonzero(blue))


PROFILE = Profile("battlechess", Path(__file__).with_name("recognition.png"),
                  (98, 48, 448, 384), ((171, 203, 99), (66, 66, 0)),
                  piece_color, shape_reader=sprite)
