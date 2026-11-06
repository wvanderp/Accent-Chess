"""Native C64 levels, with observed menu acknowledgement and exact readback.

The original disk calls level 00 with Easy Mode ON ``NEWCOMER ON``. It is the
same Ctrl+E toggle, not a second personality. Keep Easy Mode OFF; Coffeehouse
introduces weaker moves and therefore has distinct ranking profiles.
Level entry accepts two digits without Return: Return starts a computer move!
The reference atlas was captured by selecting every finite native level on the
SHA-1-verified disk, using the runtime's standard 640x480 display.
"""

import base64
from io import BytesIO
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Callable

import numpy as np
from PIL import Image

from emulation.client import RuntimeClient
from .play import Connector


PROFILES = (tuple((f'level-{level:02}', f'Level {level:02}') for level in range(19))
            + tuple((f'coffeehouse-level-{level:02}', f'Coffeehouse, Level {level:02}')
                    for level in range(19)))
LEVEL_BOX = (429, 294, 445, 302)


def matches(actual: Image.Image, expected: Image.Image) -> bool:
    """Allow fractional GTK antialiasing, while retaining complete glyphs."""
    a = np.asarray(actual.convert('RGB'), dtype=np.int16)
    b = np.asarray(expected.convert('RGB'), dtype=np.int16)
    return a.shape == b.shape and float(np.mean(np.abs(a - b))) < 4


def read_level(frame: Image.Image) -> int | None:
    """Read only a unique finite native level; an unknown glyph fails closed."""
    with Image.open(Path(__file__).with_name('difficulty-levels.png')) as atlas:
        choices = [level for level in range(19)
                   if matches(frame.crop(LEVEL_BOX), atlas.crop((0, level * 8, 16, (level + 1) * 8)))]
    return choices[0] if len(choices) == 1 else None


def set_difficulty(client: RuntimeClient, profile: str, timeout: float = 90) -> None:
    """Set and read back a finite level, leaving the ready board visible.

    This is a menu-navigation deadline only. No move or search is started,
    interrupted, or timed by this function. Call between reset and side choice.
    """
    if profile not in dict(PROFILES):
        raise ValueError(f'Unknown Chessmaster 2000 difficulty: {profile}')
    if timeout <= 0:
        raise ValueError('Menu navigation timeout must be positive')
    level = int(profile.rsplit('-', 1)[1])
    coffeehouse = profile.startswith('coffeehouse-')
    connector = Connector(client)
    deadline = monotonic() + timeout
    poll = Event()
    with Image.open(Path(__file__).with_name('difficulty-settings.png')) as source:
        reference = source.convert('RGB')
    with Image.open(Path(__file__).with_name('difficulty-newcomer.png')) as source:
        newcomer = source.convert('RGB')
    with Image.open(Path(__file__).with_name('difficulty-coffeehouse.png')) as source:
        enabled = source.convert('RGB')

    def frame() -> Image.Image:
        snapshot = client.snapshot()
        if snapshot.get('game') != 'chessmaster2000':
            raise ValueError(f'Expected runtime chessmaster2000, got {snapshot.get("game")}')
        with Image.open(BytesIO(base64.b64decode(snapshot['png'], validate=True))) as image:
            return image.convert('RGB')

    def wait(predicate: Callable[[Image.Image], bool], description: str) -> Image.Image:
        while monotonic() < deadline:
            image = frame()
            if predicate(image):
                return image
            # Transport/frame pacing; elapsed time never acknowledges a menu.
            poll.wait(0.05)
        raise TimeoutError(f'Chessmaster 2000 difficulty: {description}')

    def playing(image: Image.Image) -> bool:
        return connector.matches(image, 'playing', (171, 260, 290, 320))

    def setting(image: Image.Image, box: tuple[int, int, int, int], template: Image.Image = reference) -> bool:
        left, top, right, bottom = box
        return matches(image.crop(box), template.crop((left - 300, top - 275, right - 300, bottom - 275)))

    image = wait(lambda f: playing(f)
                 or connector.matches(f, 'menu', (320, 148, 460, 159))
                 or connector.matches(f, 'recognition', (202, 136, 446, 145)), 'ready menu or board')
    if not playing(image):
        if connector.matches(image, 'recognition', (202, 136, 446, 145)):
            connector.key('F1')
            wait(lambda f: connector.matches(f, 'menu', (320, 148, 460, 159)), 'text view')
        connector.key('ctrl+a')

        def entered_playing(candidate: Image.Image) -> bool:
            if playing(candidate):
                return True
            # The boot menu may clear CHOICES before entering its keyboard
            # loop. Ctrl+A is idempotent here, including on that blank panel.
            # Reuse the connector's bounded, unchanged-frame retry gate.
            connector.retry_menu(candidate, 'ctrl+a')
            return False

        image = wait(entered_playing, 'Playing menu')
    coffee_reference = enabled if coffeehouse else reference
    if not setting(image, (421, 286, 445, 294), coffee_reference):
        opposite = reference if coffeehouse else enabled
        if not setting(image, (421, 286, 445, 294), opposite):
            raise ValueError('Unrecognized Chessmaster Coffeehouse setting')
        connector.key('ctrl+c')
        image = wait(lambda f: playing(f) and setting(f, (421, 286, 445, 294), coffee_reference),
                     f'Coffeehouse {"ON" if coffeehouse else "OFF"}')
    if not setting(image, (309, 302, 445, 310)):
        if not (setting(image, (309, 302, 445, 310), newcomer)
                or setting(image, (309, 302, 445, 310), enabled)):
            raise ValueError('Unrecognized Chessmaster Easy Mode setting')
        connector.key('ctrl+e')
        image = wait(lambda f: playing(f) and setting(f, (309, 302, 445, 310)), 'Easy Mode OFF')
    if read_level(image) != level:
        connector.key('ctrl+d')
        wait(lambda f: playing(f) and not setting(f, (309, 294, 392, 302)), 'level input selection')
        connector.key(str(level // 10))
        wait(lambda f: playing(f) and read_level(f) == (level // 10) * 10, 'first level digit')
        connector.key(str(level % 10))
        image = wait(lambda f: playing(f) and read_level(f) == level, 'selected level readback')
    if not (read_level(image) == level
            and setting(image, (421, 286, 445, 294), coffee_reference)
            and setting(image, (309, 302, 445, 310))):
        raise ValueError('Chessmaster difficulty readback did not match requested settings')
    connector.key('F1')
    wait(lambda f: connector.matches(f, 'recognition', (202, 136, 446, 145)), 'return to board')
