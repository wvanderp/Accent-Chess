"""DOSBox 640x480, default 2D board. Other themes/3D require new calibration."""

from pathlib import Path
import chess
import numpy as np
from PIL import Image
from recognition.board import Profile


def piece_color(square: Image.Image, mask: np.ndarray) -> chess.Color:
    pixels = np.asarray(square.resize((32, 32)), dtype=np.int16)
    red = (pixels[:, :, 0] > pixels[:, :, 1] * 1.5) & (pixels[:, :, 1] < 80)
    return chess.BLACK if np.count_nonzero(red & mask) > 10 else chess.WHITE


PROFILE = Profile("grandmaster", Path(__file__).with_name("recognition.png"),
                  (16, 24, 472, 440), ((255, 255, 255), (81, 85, 93)), piece_color)
