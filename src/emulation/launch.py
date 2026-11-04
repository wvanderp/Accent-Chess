"""Container supervisor; DOSBox lifetime is independent of observers."""

import os
from pathlib import Path
import subprocess

from .backend import X11Backend
from .server import Session, make_server


def main() -> None:
    if game := os.environ.get("GAME_ID"):
        from games.catalog import prepare
        command = prepare(game, Path("/tmp/game"))
    else:
        command = local_command()
    print("Starting emulator…", flush=True)
    supervise(command)


def local_command() -> list[str]:
    executable = os.environ.get("GAME_EXECUTABLE", "")
    relative = Path(executable)
    if not executable or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Set GAME_EXECUTABLE to a relative DOS executable path")
    if not (Path("/game") / relative).is_file():
        raise ValueError("Game executable does not exist in /game")
    # Copy read-only supplied media into a disposable writable session directory.
    import shutil
    shutil.copytree("/game", "/tmp/game", dirs_exist_ok=True)
    return ["dosbox", "-conf", "/app/docker/dosbox.conf",
                                "-c", "mount c /tmp/game", "-c", "c:",
                                "-c", executable.replace("/", "\\")]


def supervise(command: list[str]) -> None:
    process = subprocess.Popen(command)
    try:
        with make_server(Session(X11Backend()), "0.0.0.0", 8765) as server:
            # A crashed emulator must not leave a healthy-looking service running.
            from threading import Thread

            def watch() -> None:
                process.wait()
                server.shutdown()

            Thread(target=watch, daemon=True).start()
            server.serve_forever()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
