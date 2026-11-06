"""Atari ST runtime, isolated from game-specific menus and board readers.

Use the freely distributed EmuTOS firmware; original TOS is not bundled.
Disable borders and scaling so frame and input coordinates stay reproducible.
"""

from pathlib import Path

from .media import download, extract

FIRMWARE_URL = "https://downloads.sourceforge.net/project/emutos/emutos/1.3/emutos-192k-1.3.zip"


def command(destination: Path, disk: Path) -> list[str]:
    firmware = destination / "firmware"
    extract(download(FIRMWARE_URL, destination / "emutos.zip",
                     "ada8bf61e31ce68962305f26b3c3f44d9950fe2f"), firmware)
    rom = next(firmware.rglob("etos192us.img"), None)
    if rom is None:
        raise ValueError("EmuTOS archive lacks the US 192K ROM")
    return ["hatari", "--tos", str(rom), "--machine", "st", "--memsize", "1",
            "--monitor", "rgb", "--borders", "off", "--zoom", "1",
            "--statusbar", "off", "--sound", "off", "--confirm-quit", "off",
            "--cmd-fifo", "/tmp/hatari-control.fifo", "--drive-led", "off",
            "--disk-a", str(disk)]
