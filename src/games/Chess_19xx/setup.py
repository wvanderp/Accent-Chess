"""Chess 19xx is C64, not DOS. VICE autostart loads its D64 program.

Debian omits copyrighted C64 ROMs. Fetch the ROM data supplied by the upstream
VICE source tree explicitly rather than assuming the package contains them.
"""

from pathlib import Path
from emulation.media import download

TITLE = "Chess 19xx (Commodore 64)"


def prepare(destination: Path) -> list[str]:
    disk = download("https://archive.org/download/Chess_19xx_-/Chess_19xx_-.d64",
                    destination / "chess.d64", "64f581bf98bcdf31372c6006016f55f9e1bc81f0")
    roms = {}
    for kind, filename in {"kernal": "kernal-901227-03.bin", "basic": "basic-901226-01.bin",
                           "chargen": "chargen-901225-01.bin"}.items():
        roms[kind] = download("https://raw.githubusercontent.com/VICE-Team/svn-mirror/main/vice/data/C64/" + filename,
                              destination / filename)
    return ["x64sc", "-default", "+sound", "+drive8truedrive", "-virtualdev8", "-drive8type", "0",
            "+autostart-handle-tde", "-VICIIfull", "+VICIIdsize", "-VICIIfilter", "0",
            "-kernal", str(roms["kernal"]), "-basic", str(roms["basic"]),
            "-chargen", str(roms["chargen"]), "-autostart", str(disk)]
