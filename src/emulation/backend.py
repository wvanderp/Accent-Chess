"""DOSBox display/input adapter. Coordinates always refer to the virtual display.

Capture is private to Xvfb, never the user's desktop. This initial adapter uses
X11 pixels; a future framebuffer adapter can replace it without changing clients.
"""

import io
import os
import re
import subprocess
from typing import Protocol

from PIL import ImageGrab


class Backend(Protocol):
    def capture(self) -> bytes: ...
    def key(self, name: str, delay_ms: int = 12, window_title: str | None = None) -> None: ...
    def click(self, x: int, y: int) -> None: ...
    def move_pointer(self, x: int, y: int) -> None: ...


class X11Backend:
    def move_pointer(self, x: int, y: int) -> None:
        if not (0 <= x < 640 and 0 <= y < 480):
            raise ValueError("Coordinates must be inside the 640x480 display")
        subprocess.run(["xdotool", "mousemove", str(x), str(y)], check=True, timeout=3)

    def capture(self) -> bytes:
        image = ImageGrab.grab(xdisplay=os.environ.get("DISPLAY", ":99"))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def key(self, name: str, delay_ms: int = 12, window_title: str | None = None) -> None:
        # One keysym, optionally prefixed by explicit modifiers. This enables
        # C64 Ctrl menu shortcuts without accepting xdotool command sequences.
        if not isinstance(name, str) or not name or len(name) > 40:
            raise ValueError("Expected an X11 keysym or modifier chord")
        parts = name.split("+")
        if (len(parts) > 3 or any(part not in {"ctrl", "alt", "shift"} for part in parts[:-1])
                or not parts[-1] or not all(c.isalnum() or c == "_" for c in parts[-1])):
            raise ValueError("Expected an X11 keysym or modifier chord")
        if type(delay_ms) is not int or not 12 <= delay_ms <= 1000:
            raise ValueError("Key delay must be an integer between 12 and 1000 milliseconds")
        if window_title is not None:
            if not isinstance(window_title, str) or not 1 <= len(window_title) <= 128:
                raise ValueError("Expected an emulator window title")
            # Xvfb has no window manager. GTK can leave keyboard focus at the
            # root window; pointer location is not sufficient to deliver keys.
            subprocess.run(["xdotool", "search", "--onlyvisible", "--name",
                            "^" + re.escape(window_title) + "$", "windowfocus", "--sync"],
                           check=True, timeout=3)
        # Electrical key duration, not an engine-completion wait. VICE's C64
        # keyboard scan can miss the default 12ms X11 press/release sequence.
        subprocess.run(["xdotool", "key", "--clearmodifiers", "--delay", str(delay_ms), name],
                       check=True, timeout=3)

    def click(self, x: int, y: int) -> None:
        if not (0 <= x < 640 and 0 <= y < 480):
            raise ValueError("Coordinates must be inside the 640x480 display")
        # --sync waits for actual pointer motion and stalls when already at x/y.
        # Commands in one xdotool invocation are ordered without that wait.
        subprocess.run(["xdotool", "mousemove", str(x), str(y), "click", "1"],
                       check=True, timeout=3)
