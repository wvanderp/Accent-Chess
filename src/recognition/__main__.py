"""Read runtime frames or replay a saved PNG without running an emulator."""

import argparse
from pathlib import Path
from threading import Event

from PIL import Image

from emulation.client import RuntimeClient
from .runtime import FrameRecorder, MODULES, RuntimeRecognizer, create_reader


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, choices=MODULES)
    parser.add_argument("--runtime", default="http://127.0.0.1:8765")
    parser.add_argument("--debug-frames", type=Path)
    parser.add_argument("--max-debug-frames", type=int, default=500)
    parser.add_argument("--image", type=Path, help="Offline recognition of one saved full-display PNG")
    parser.add_argument("--once", action="store_true", help="Read twice to confirm, then exit")
    args = parser.parse_args()
    if args.max_debug_frames < 1:
        parser.error("--max-debug-frames must be positive")
    if args.image:
        with Image.open(args.image) as frame:
            print(create_reader(args.game).read(frame).placement)
        return
    client = RuntimeClient(args.runtime)
    recorder = FrameRecorder(args.debug_frames, args.game, args.max_debug_frames) if args.debug_frames else None
    recognizer = RuntimeRecognizer(args.game, client, recorder)
    if recorder:
        print(f"Saving evidence to {recorder.directory}")
    stop = Event()
    previous = ""
    try:
        while not stop.is_set():
            status = recognizer.process(client.snapshot())
            if args.once:
                status = recognizer.process(client.snapshot())
            if status != previous:
                print(status, flush=True)
                previous = status
            if args.once:
                return
            stop.wait(0.25)  # Capture pacing only; agreement decides readiness.
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
