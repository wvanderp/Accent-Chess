"""Exercise real DOSBox display/input without requiring commercial game media."""

from io import BytesIO
import subprocess
from threading import Event
from time import monotonic

from PIL import Image

from emulation.backend import X11Backend


def main() -> None:
    process = subprocess.Popen(["dosbox", "-conf", "/app/docker/dosbox.conf"])
    backend = X11Backend()
    deadline = monotonic() + 15
    try:
        while monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("DOSBox exited before display became ready")
            image = Image.open(BytesIO(backend.capture())).convert("RGB")
            if image.getbbox() is not None:
                backend.key("Return")
                backend.click(320, 240)
                print(f"DOSBox display and input OK: {image.size}")
                return
            Event().wait(0.1)
        raise TimeoutError("DOSBox did not render a visible display")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
