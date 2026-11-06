"""Verified DOS Playing Strength controls, independent of native time controls.

The 1993 media has five strength choices, a separate Playing Style dialog,
and a separate nine-choice Time Control dialog. Changing strength must not
silently change any of those other settings. See docs/difficulty/grandmaster.md.
"""

import base64
from hashlib import sha256
from io import BytesIO
from threading import Event
from time import monotonic
from typing import Callable

from PIL import Image

from emulation.client import RuntimeClient


PROFILES = (
    ("beginner", "Beginner"),
    ("novice", "Novice"),
    ("intermediate", "Intermediate"),
    ("expert", "Expert"),
    ("grandmaster", "Grandmaster"),
)

# Exact fixed-VGA title pixels, observed in the distributed DOS media. A
# title-specific match prevents a click on an unrelated modal or game board.
_TITLE_SHA256 = "20d07f34c902e83c1793eafbf988e7c205c235139baf3ee273b9ce27aa234712"
_GAME_MENU_SHA256 = "8561570555da35e7b84e37e6ba21464cf9f3ddbc052d08ac787f4465d62c261c"
_SELECTED = (97, 40, 69)


def _frame(client: RuntimeClient) -> Image.Image:
    snapshot = client.snapshot()
    if snapshot.get("game") != "grandmaster":
        raise ValueError("Grandmaster difficulty requires a Grandmaster runtime")
    with Image.open(BytesIO(base64.b64decode(snapshot["png"], validate=True))) as image:
        return image.convert("RGB")


def _is_dialog(frame: Image.Image) -> bool:
    return sha256(frame.crop((243, 163, 397, 182)).tobytes()).hexdigest() == _TITLE_SHA256


def _selection(frame: Image.Image) -> int | None:
    if not _is_dialog(frame):
        return None
    selected = [index for index in range(len(PROFILES))
                if frame.getpixel((259, 195 + 19 * index)) == _SELECTED]
    return selected[0] if len(selected) == 1 else None


def set_difficulty(client: RuntimeClient, profile: str, timeout: float = 90) -> None:
    """Set and reopen Playing Strength to verify its persisted radio selection.

    Invoke on an idle, initialized board before play_as starts White. Menus
    and radio state, rather than elapsed delays, acknowledge every action.
    Native clocks, style and pondering are deliberately left as configured.
    """
    identifiers = [identifier for identifier, _ in PROFILES]
    if profile not in identifiers:
        raise ValueError(f"Unknown Grandmaster difficulty: {profile}")
    if timeout <= 0:
        raise ValueError("Difficulty setup timeout must be positive")
    _frame(client)  # Reject the wrong runtime before sending any input.
    target = identifiers.index(profile)
    deadline = monotonic() + timeout
    poll = Event()

    def wait_for(predicate: Callable[[Image.Image], bool], description: str) -> Image.Image:
        while True:
            frame = _frame(client)
            if predicate(frame):
                return frame
            if monotonic() >= deadline:
                raise TimeoutError(f"Grandmaster difficulty: {description}")
            poll.wait(0.05)  # Capture pacing; only observed pixels acknowledge UI.

    def key(name: str) -> None:
        client.send("key", {"name": name, "delay_ms": 150})

    def open_dialog() -> None:
        key("F2")
        wait_for(lambda frame: sha256(frame.crop((120, 24, 260, 47)).tobytes()).hexdigest()
                 == _GAME_MENU_SHA256,
                 "Game menu did not open")
        for _ in range(4):
            key("Down")
        key("Return")
        wait_for(_is_dialog, "Playing Strength dialog did not open")

    open_dialog()
    # Tab order begins at OK, then Cancel, then the five individual radios.
    # Mouse clicks can be missed by DOSBox's relative mouse event scanner.
    for _ in range(2 + target):
        key("Tab")
    key("Return")
    wait_for(lambda frame: _selection(frame) == target, "strength selection was not acknowledged")
    for _ in range(5 - target):
        key("Tab")
    key("Return")
    wait_for(lambda frame: not _is_dialog(frame), "strength dialog did not close")
    open_dialog()
    wait_for(lambda frame: _selection(frame) == target, "strength readback did not match")
    key("Escape")
    wait_for(lambda frame: not _is_dialog(frame), "readback dialog did not close")
    client.send("pointer", {"x": 0, "y": 0})
