"""Atari ST native finite levels, selected and read back from the Level menu.

Hatari's relative cursor can retain an offset from host coordinates. Readback
detects this: adjust by the observed menu-row error rather than claiming that
an HTTP pointer command is an acknowledged selection.
"""
import base64
from io import BytesIO
from threading import Event
from time import monotonic
import sys

import numpy as np
from PIL import Image

from emulation.client import RuntimeClient

PROFILES = (("novice", "Novice"),) + tuple((f"level-{n}", f"Level {n}") for n in range(1, 10))


def read_difficulty(frame: Image.Image) -> str:
    """Recognize the selected '+' in the open native Level menu."""
    pixels = np.asarray(frame.convert("RGB"))
    yellow = (pixels[:, :, 0] > 200) & (pixels[:, :, 1] > 200) & (pixels[:, :, 2] < 80)
    # Header letters and menu right edge distinguish this from ordinary play.
    if np.count_nonzero(yellow[136:150, 440:536]) < 100:
        raise ValueError("Battle Chess Level menu is not open")
    if np.count_nonzero(yellow[296:310, 440:568]) < 180:
        raise ValueError("Battle Chess Level menu is still unfolding")
    rows = [np.count_nonzero(yellow[137+16*n:149+16*n, 425:439]) for n in range(10)]
    matches = [n for n, count in enumerate(rows) if count >= 15]
    if len(matches) != 1:
        raise ValueError("Battle Chess selected level is not recognized")
    return PROFILES[matches[0]][0]


def hovered_level(frame: Image.Image) -> int | None:
    """The native menu paints a black strip behind the hovered row."""
    pixels = np.asarray(frame.convert("RGB"))
    try:
        read_difficulty(frame)
    except ValueError:
        return None
    rows = [n for n in range(10)
            if np.all(pixels[140+16*n:147+16*n, 555:563] < 15)]
    return rows[0] if len(rows) == 1 else None


def set_difficulty(client: RuntimeClient, profile: str, timeout: float = 90) -> None:
    """Select a finite preset from an already booted, idle game; verify readback.

    This does not dismiss intros, start a game, or select a custom thinking time.
    Always release the right button, including after an unrecognized screen.
    """
    profiles = dict(PROFILES)
    if profile not in profiles:
        raise ValueError(f"Unknown Battle Chess difficulty: {profile}")
    if timeout <= 0:
        raise ValueError("Difficulty setup timeout must be positive")
    end = monotonic() + timeout
    poll = Event()

    def frame() -> Image.Image:
        snapshot = client.snapshot()
        if snapshot.get("game") != "battlechess":
            raise ValueError("Expected a Battle Chess runtime")
        with Image.open(BytesIO(base64.b64decode(snapshot["png"], validate=True))) as image:
            return image.convert("RGB")

    def observe() -> str | None:
        image = frame()
        try:
            return read_difficulty(image)
        except ValueError:
            return None

    def open_menu() -> str:
        client.send("mouse-button", {"button": 3, "pressed": True})
        client.send("pointer", {"x": 475, "y": 65})
        while monotonic() < end:
            if current := observe():
                return current
            poll.wait(.05)
        raise TimeoutError("Battle Chess Level menu did not open")

    target = [key for key, _ in PROFILES].index(profile)
    correction = 0
    frame()  # Validate the runtime before sending mouse input.
    try:
        current = open_menu()
        for attempt in range(4):
            if current == profile:
                return
            pointer_y = max(80, min(340, 143 + 16*target + correction))
            client.send("pointer", {"x": 490, "y": pointer_y})
            last_pointer = monotonic()
            # A pointer transport acknowledgement precedes the animated guest
            # cursor. Release only after the actual target row is highlighted.
            while monotonic() < end:
                hovered = hovered_level(frame())
                if hovered == target:
                    break
                if hovered is not None and monotonic() - last_pointer >= 1:
                    pointer_y = max(80, min(340, pointer_y + 16*(target-hovered)))
                    client.send("pointer", {"x": 490, "y": pointer_y})
                    last_pointer = monotonic()
                poll.wait(.05)
            else:
                raise TimeoutError("Battle Chess target level was not highlighted")
            client.send("mouse-button", {"button": 3, "pressed": False})
            # Require a closed menu before interpreting the next readback.
            while monotonic() < end and observe() is not None:
                poll.wait(.05)
            if monotonic() >= end:
                raise TimeoutError("Battle Chess Level menu did not close")
            current = open_menu()
            if current == profile:
                return
            selected = [key for key, _ in PROFILES].index(current)
            correction += 16 * (target - selected)
        raise RuntimeError(f"Battle Chess selected {current}, expected {profile}")
    finally:
        failed = sys.exc_info()[0] is not None
        # Releasing over the heading dismisses the menu without another choice.
        client.send("pointer", {"x": 475, "y": 65})
        while monotonic() < end and hovered_level(frame()) is not None:
            poll.wait(.05)
        client.send("mouse-button", {"button": 3, "pressed": False})
        while monotonic() < end:
            pixels = np.asarray(frame())
            if not np.array_equal(pixels[55, 300], (170, 204, 102)):
                break
            poll.wait(.05)
        else:
            if not failed:
                raise TimeoutError("Battle Chess menu dismissal was not acknowledged")
