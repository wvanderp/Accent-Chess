"""VICE's default local GTK window, native size with CRT filtering disabled.

GTK still resamples the C64 image: square boundaries use fractional widths.
These coordinates refer to the full Xvfb display, not a browser canvas.
"""

from pathlib import Path
import chess
import numpy as np
from PIL import Image
from recognition.board import Profile


def piece_color(square: Image.Image, mask: np.ndarray) -> chess.Color:
    # All six C64 sprites share this interior base patch. Fill stays blue for
    # black and gray for white, including outlined sprites. Median sampling
    # tolerates GTK's fractional resampling of the sprite's vertical lines.
    pixels = np.asarray(square.resize((32, 32)), dtype=np.int16)
    base = np.median(pixels[21:26, 14:18], axis=(0, 1))
    return chess.BLACK if base[2] - base[0] > 85 else chess.WHITE


PROFILE = Profile("chess19xx", Path(__file__).with_name("recognition.png"),
                  (180, 138, 242, 193), ((213, 213, 213), (62, 81, 240)), piece_color,
                  template_shift=2, fill_scanlines=True,
                  # A moved king has a distinct resampled outline at this pixel phase.
                  extra_templates=((Path(__file__).with_name("recognition-king-a4.png"),
                                    "a4", chess.KING),
                                   # The live D8-F6 reply confirmed this queen;
                                   # its resampled crown resembled the rook template.
                                   (Path(__file__).with_name("recognition-queen-f6.png"),
                                    "f6", chess.QUEEN),
                                   # The displayed E5-F5 king reply to Nd7+
                                   # lost its crown at this GTK sampling phase.
                                   (Path(__file__).with_name("recognition-king-f5.png"),
                                    "f5", chess.KING)))
