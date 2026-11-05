"""VICE launch configuration shared by C64 games.

Some commercial loaders speak directly to the 1541. Virtual device traps alone
cannot run Chessmaster 2000; it requires a drive ROM and true drive emulation.
"""

from pathlib import Path

from .media import download

ROM_BASE = "https://raw.githubusercontent.com/VICE-Team/svn-mirror/main/vice/data/"
ROM_SHA1 = {
    "kernal": "1d503e56df85a62fee696e7618dc5b4e781df1bb",
    "basic": "79015323128650c742a3694c9429aa91f355905e",
    "chargen": "adc7c31e18c7c7413d54802ef2f4193da14711aa",
}


def command(destination: Path, disk: Path, *, accurate_drive: bool = False) -> list[str]:
    roms = {
        kind: download(ROM_BASE + "C64/" + filename, destination / filename, ROM_SHA1[kind])
        for kind, filename in {
            "kernal": "kernal-901227-03.bin", "basic": "basic-901226-01.bin",
            "chargen": "chargen-901225-01.bin",
        }.items()
    }
    result = ["x64sc", "-default", "+sound", "-VICIIfull", "+VICIIdsize", "-VICIIfilter", "0"]
    for kind, path in roms.items():
        result.extend(["-" + kind, str(path)])
    if accurate_drive:
        rom = download(ROM_BASE + "DRIVES/dos1541-325302-01+901229-05.bin", destination / "dos1541.bin",
                       "ab16f56989b27d89babe5f89c5a8cb3da71a82f0")
        result.extend(["-drive8truedrive", "-drive8type", "1541", "-dos1541", str(rom),
                       "-autostart-handle-tde", "-autostart-warp"])
    else:
        result.extend(["+drive8truedrive", "-virtualdev8", "-drive8type", "0", "+autostart-handle-tde"])
    return result + ["-autostart", str(disk)]
