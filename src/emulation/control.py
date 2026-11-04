"""Host-side Docker lifecycle. No Docker socket is exposed inside the game."""

from pathlib import Path
import subprocess
from typing import Callable

IMAGE = "accent-chess-runtime"
CONTAINER = "accent-chess-game"


class DockerControl:
    def __init__(self, log: Callable[[str], None]) -> None:
        self.log = log

    def run(self, arguments: list[str]) -> str:
        with subprocess.Popen(["docker", *arguments], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                              errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
            assert process.stdout is not None
            lines = []
            for line in process.stdout:
                lines.append(line)
                self.log(line.rstrip())
            if process.wait() != 0:
                raise RuntimeError("Docker command failed; see progress log")
            return "".join(lines)

    def start(self, game: str) -> None:
        from games.catalog import GAMES
        if game not in GAMES:
            raise ValueError("Unknown game")
        root = Path(__file__).resolve().parents[2]
        self.log("Building emulator image…")
        self.run(["build", "-f", str(root / "docker/Dockerfile"), "-t", IMAGE, str(root)])
        existing = self.run(["ps", "-a", "--filter", f"name=^/{CONTAINER}$", "--format", "{{.Names}}"])
        if CONTAINER in existing.splitlines():
            self.log("Removing previous Accent Chess session…")
            self.run(["rm", "-f", CONTAINER])
        self.run(["run", "-d", "--init", "--name", CONTAINER,
                  "--label", "accent-chess.managed=true", "-p", "127.0.0.1:8765:8765",
                  "-e", f"GAME_ID={game}", IMAGE])
        self.log("Container started; downloading and preparing game…")

    def stop(self) -> None:
        self.run(["stop", CONTAINER])

    def logs(self) -> None:
        self.run(["logs", "--follow", CONTAINER])
