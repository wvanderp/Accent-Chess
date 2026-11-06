"""DOSBox 640x480, default 2D board. Other themes/3D require new calibration."""

from pathlib import Path
import chess
import numpy as np
from PIL import Image
from recognition.board import Profile


def piece_color(square: Image.Image, mask: np.ndarray) -> chess.Color:
    # White sprites and both square backgrounds are neutral gray. Gold sprite
    # interiors remain saturated even when the king's red shadows disappear
    # on a light square (observed live at g6). Dark-red pixel counting mistook
    # that black king for a second white king and stalled the match.
    pixels = np.asarray(square.convert('RGB'), dtype=np.int16)
    gold = (pixels[:, :, 0] - pixels[:, :, 1] > 25) & (pixels[:, :, 0] - pixels[:, :, 2] > 40)
    return chess.BLACK if np.count_nonzero(gold) > 20 else chess.WHITE


PROFILE = Profile("grandmaster", Path(__file__).with_name("recognition.png"),
                  (16, 24, 472, 440), ((255, 255, 255), (81, 85, 93)), piece_color,
                  # White queen shadows blend into a dark square; its initial
                  # light-square template otherwise favors the king silhouette.
                  extra_templates=((Path(__file__).with_name('recognition-queen-f4.png'),
                                    'f4', chess.QUEEN),))
