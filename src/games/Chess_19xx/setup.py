"""Chess 19xx is C64, not DOS. VICE autostart loads its D64 program.

Debian omits copyrighted C64 ROMs. Fetch the ROM data supplied by the upstream
VICE source tree explicitly rather than assuming the package contains them.
"""

from pathlib import Path
from emulation.media import download
from emulation.c64 import command

TITLE = "Chess 19xx (Commodore 64)"


def prepare(destination: Path) -> list[str]:
    disk = download("https://archive.org/download/Chess_19xx_-/Chess_19xx_-.d64",
                    destination / "chess.d64", "64f581bf98bcdf31372c6006016f55f9e1bc81f0")
    return command(destination, disk)
