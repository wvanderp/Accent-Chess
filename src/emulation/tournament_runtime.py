"""Disposable tournament runtimes, isolated from the viewer and other matches."""
from contextlib import contextmanager
from pathlib import Path
import subprocess
from threading import Event
from time import monotonic
from typing import Iterator
from urllib.error import URLError
from uuid import uuid4

from .client import RuntimeClient
from .control import DockerControl, IMAGE


def build_image() -> None:
    root = Path(__file__).resolve().parents[2]
    DockerControl(print).run(['build', '-f', str(root / 'docker/Dockerfile'), '-t', IMAGE, str(root)])


@contextmanager
def runtime(game: str, directory: Path, timeout: float) -> Iterator[RuntimeClient]:
    """Docker chooses an unused loopback port; remove only our unique container."""
    name = 'accent-chess-tournament-' + uuid4().hex[:12]
    control = DockerControl(print)
    control.run(['run', '-d', '--init', '--name', name, '--label', 'accent-chess.tournament=true',
                 '-p', '127.0.0.1::8765', '-e', f'GAME_ID={game}', IMAGE])
    try:
        binding = control.run(['port', name, '8765/tcp']).strip()
        client = RuntimeClient('http://' + binding)
        deadline = monotonic() + timeout
        wake = Event()
        while True:
            try:
                if client.snapshot().get('game') == game:
                    break
            except (URLError, OSError):
                pass
            if monotonic() >= deadline:
                raise TimeoutError(f'{game}: runtime did not start')
            # Transport retry pacing only; board/UI observations decide play.
            wake.wait(0.2)
        try:
            yield client
        except BaseException:
            # Adapter initialization can fail before a participant is returned.
            # Capture while the owned runtime still exists, before cleanup.
            try:
                import base64
                (directory / f'{game}-failure.png').write_bytes(base64.b64decode(client.snapshot()['png']))
            except (URLError, OSError):
                pass
            raise
    finally:
        with (directory / f'{game}-runtime.log').open('w', encoding='utf-8') as log:
            subprocess.run(['docker', 'logs', name], stdout=log, stderr=subprocess.STDOUT, check=False)
        control.run(['rm', '-f', name])
