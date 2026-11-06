"""Verified Swedish C64 strength presets; see docs/difficulty/chess19xx.md."""
import base64
from io import BytesIO
from pathlib import Path
from threading import Event
from time import monotonic

import numpy as np
from PIL import Image

from emulation.client import RuntimeClient

PROFILES = tuple((f"level-{n}", f"Level {n}") for n in range(1, 10))
BOX = (443, 235, 456, 244)


def read_difficulty(frame: Image.Image) -> str:
    """Read only the SPELSTYRKA digit, excluding clocks and move input."""
    with Image.open(Path(__file__).with_name("difficulty-label.png")) as label:
        expected = np.asarray(label)[:, :, 1] > 140
    actual_label = np.asarray(frame.convert("RGB").crop((425, 216, 479, 235)))[:, :, 1] > 140
    if np.mean(actual_label != expected) > .03:
        raise ValueError("Chess 19xx SPELSTYRKA label is not visible")
    actual = np.asarray(frame.convert("RGB").crop(BOX))[:, :, 1] > 140
    with Image.open(Path(__file__).with_name("difficulty-levels.png")) as strip:
        scores = [np.mean(actual != (np.asarray(strip.crop((13*n, 0, 13*n+13, 9)))[:, :, 1] > 140))
                  for n in range(9)]
    index = int(np.argmin(scores))
    if scores[index] > .08 or sorted(scores)[1] - scores[index] < .015:
        raise ValueError("Chess 19xx strength digit is not recognized")
    return f"level-{index+1}"


def set_difficulty(client: RuntimeClient, profile: str, timeout: float = 90) -> None:
    """Change strength with native <> controls and acknowledge each new digit.

    A missed C64 keyboard scan can be retried only while the old digit remains
    visible. No move is forced and no memory is changed.
    """
    if profile not in dict(PROFILES):
        raise ValueError(f"Unknown Chess 19xx difficulty: {profile}")
    if timeout <= 0:
        raise ValueError("Difficulty setup timeout must be positive")
    deadline = monotonic() + timeout
    previous: str | None = None
    sent_at = 0.0
    poll = Event()
    target = int(profile.split("-")[1])
    while monotonic() < deadline:
        snapshot = client.snapshot()
        if snapshot.get("game") != "chess19xx":
            raise ValueError("Expected a Chess 19xx runtime")
        with Image.open(BytesIO(base64.b64decode(snapshot["png"], validate=True))) as frame:
            try:
                current = read_difficulty(frame)
            except ValueError:
                poll.wait(.05)
                continue
        if current == profile:
            return
        if current != previous or monotonic() - sent_at >= 1:
            level = int(current.split("-")[1])
            client.send("key", {"name": "greater" if level < target else "less",
                                "delay_ms": 200, "window_title": "VICE (C64SC)"})
            previous = current
            sent_at = monotonic()
        poll.wait(.05)
    raise TimeoutError(f"Chess 19xx did not acknowledge {profile}")
