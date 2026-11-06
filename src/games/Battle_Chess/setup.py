"""The Archive release is an ST floppy, not the similarly named DOS game."""

from pathlib import Path

from emulation.atarist import command
from emulation.media import download

TITLE = "Battle Chess (Atari ST, 1989)"
MEDIA_URL = ("https://archive.org/download/Battle_Chess_1989_Interplay_cr_MCA_m_EMT/"
             "Battle_Chess_1989_Interplay_cr_MCA_m_EMT.st")


def prepare(destination: Path) -> list[str]:
    disk = download(MEDIA_URL, destination / "battlechess.st",
                    "b8260f86f75ce9419d28c77c39b5886852e688f6")
    return command(destination, disk) + ["--auto", "A:\\CHESS.PRG"]
