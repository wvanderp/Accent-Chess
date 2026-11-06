"""Read the exact coordinate prefix beside Chessmaster's block input cursor.

The C64 character ROM's uppercase glyphs (SHA-1 verified by emulation.c64)
survive GTK scaling. Pixel-count growth alone acknowledged cursor redraws as
typed characters, allowing later keys to overtake the game's input routine.
These small glyph templates verify the expected prefix before every next key.
"""
from functools import lru_cache

import numpy as np
from PIL import Image

ROWS = {
    'A': (24, 60, 102, 126, 102, 102, 102, 0),
    'B': (124, 102, 102, 124, 102, 102, 124, 0),
    'C': (60, 102, 96, 96, 96, 102, 60, 0),
    'D': (120, 108, 102, 102, 102, 108, 120, 0),
    'E': (126, 96, 96, 120, 96, 96, 126, 0),
    'F': (126, 96, 96, 120, 96, 96, 96, 0),
    'G': (60, 102, 96, 110, 102, 102, 60, 0),
    'H': (102, 102, 102, 126, 102, 102, 102, 0),
    '1': (24, 24, 56, 24, 24, 24, 126, 0),
    '2': (60, 102, 6, 12, 48, 96, 126, 0),
    '3': (60, 102, 6, 28, 6, 102, 60, 0),
    '4': (6, 14, 30, 102, 127, 6, 6, 0),
    '5': (126, 96, 124, 6, 6, 102, 60, 0),
    '6': (60, 102, 96, 124, 102, 102, 60, 0),
    '7': (126, 102, 12, 24, 24, 24, 24, 0),
    '8': (60, 102, 102, 60, 102, 102, 60, 0),
    'Q': (60, 102, 102, 102, 102, 60, 14, 0),
    'R': (124, 102, 102, 124, 120, 108, 102, 0),
    'N': (102, 118, 126, 126, 110, 102, 102, 0),
    '-': (0, 0, 0, 126, 0, 0, 0, 0),
}


def normalized(mask: np.ndarray) -> np.ndarray:
    ys, xs = np.where(mask)
    if not len(xs):
        return np.zeros((32, 32), dtype=bool)
    ink = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return np.asarray(Image.fromarray(ink).resize((32, 32), Image.Resampling.NEAREST))


@lru_cache(maxsize=None)
def glyph(character: str) -> np.ndarray:
    return normalized(np.array([[bool(row & (128 >> x)) for x in range(8)] for row in ROWS[character]]))


def cell(pixels: np.ndarray, index: int, row: int, black: bool) -> np.ndarray:
    # Fractional GTK character pitch; sprites/text are upright for both sides.
    origin = 406.6 if black else 345.6
    return pixels[row:row + 7, round(origin + index * 7.6):round(origin + (index + 1) * 7.6)]


def entry_matches(frame: Image.Image, prefix: str, row: int, *, black: bool) -> bool:
    """Require the expected letters/digits and a full block cursor immediately after."""
    intensity = np.asarray(frame.convert('RGB'))[:, :, 0]
    # Thin glyph strokes become gray under GTK's fractional resampling. The
    # filled cursor remains black, so it uses a separate, stricter threshold.
    pixels = intensity < 160
    for index, character in enumerate(prefix.upper()):
        actual = cell(pixels, index, row, black)
        if character == ' ':
            if float(np.mean(actual)) > 0.15:
                return False
            continue
        if not 0.05 < float(np.mean(actual)) < 0.9:
            return False
        actual = normalized(actual)
        expected = glyph(character)
        distance = np.count_nonzero(actual ^ expected) / max(1, np.count_nonzero(actual | expected))
        if distance > 0.36:
            return False
    origin = 406.6 if black else 345.6
    start = round(origin + len(prefix) * 7.6)
    # The filled block crosses GTK's intensity threshold at a different phase
    # from thin glyph strokes. Locate a real solid block around the nominal
    # cell, independently of the glyph baseline; never count mere ink growth.
    cursor_pixels = intensity < 100
    return any(float(np.mean(cursor_pixels[y:y + 7, x:x + 7])) > 0.9
               for y in range(row - 1, row + 3) for x in range(start - 1, start + 2))
