"""Archive metadata specifies grandchs/CHESS.BAT; run in its working directory."""

from pathlib import Path
from emulation.media import download, extract

TITLE = "Grandmaster Chess (DOS)"


def prepare(destination: Path) -> list[str]:
    archive = download(
        "https://archive.org/download/msdos_Grandmaster_Chess_1993/Grandmaster_Chess_1993.zip",
        destination / "game.zip", "30a361e0b3db038f8c53146942bd07f4411d203b")
    extract(archive, destination)
    return ["dosbox", "-conf", "/app/docker/dosbox.conf", "-c",
            f"mount c {destination}", "-c", "c:", "-c", "cd grandchs", "-c", "CHESS.BAT"]
