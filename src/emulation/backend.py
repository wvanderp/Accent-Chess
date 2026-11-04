"""DOSBox display/input adapter. Coordinates always refer to the virtual display.

Capture is private to Xvfb, never the user's desktop. This initial adapter uses
X11 pixels; a future framebuffer adapter can replace it without changing clients.
"""

import io
import os
import subprocess
from typing import Protocol

from PIL import ImageGrab


class Backend(Protocol):
    def capture(self) -> bytes: ...
    def key(self, name: str) -> None: ...
    def click(self, x: int, y: int) -> None: ...


class X11Backend:
    def capture(self) -> bytes:
        image = ImageGrab.grab(xdisplay=os.environ.get("DISPLAY", ":99"))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def key(self, name: str) -> None:
        # A single keysym, not an arbitrary xdotool command or shell string.
        if not name or len(name) > 40 or not all(c.isalnum() or c == "_" for c in name):
            raise ValueError("Expected a single X11 keysym (e.g. Return or F1)")
        subprocess.run(["xdotool", "key", "--clearmodifiers", name], check=True, timeout=3)

    def click(self, x: int, y: int) -> None:
        if not (0 <= x < 640 and 0 <= y < 480):
            raise ValueError("Coordinates must be inside the 640x480 display")
        # --sync waits for actual pointer motion and stalls when already at x/y.
        # Commands in one xdotool invocation are ordered without that wait.
        subprocess.run(["xdotool", "mousemove", str(x), str(y), "click", "1"],
                       check=True, timeout=3)
