"""Original two-sided C64 release. Side A boots; retain Side B for disk menus.

The custom loader requires true 1541 emulation. Keep both disk images in the
session, without replacing the boot disk automatically during normal play.
"""

from pathlib import Path

from emulation.c64 import command
from emulation.media import download

TITLE = "The Chessmaster 2000 (Commodore 64)"
ITEM = "Chessmaster_2000_The_1986_Software_Toolworks_Side_A"


def prepare(destination: Path) -> list[str]:
    for side, checksum in (("A", "d0b1eda0872594da8bf0ad2285d29bf407bb6ea6"),
                           ("B", "b247df30d413c8cbd804aa7d5e189dcb0d54fdbf")):
        filename = f"Chessmaster_2000_The_1986_Software_Toolworks_Side_{side}.d64"
        download(f"https://archive.org/download/{ITEM}/{filename}", destination / f"side-{side.lower()}.d64", checksum)
    return command(destination, destination / "side-a.d64", accurate_drive=True)
