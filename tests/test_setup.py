"""Downloaded ZIPs must remain inside the session directory."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from emulation.media import extract


class SetupTests(unittest.TestCase):
    def test_rejects_zip_traversal(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "media.zip"
            with ZipFile(archive, "w") as bundle:
                bundle.writestr("../outside.exe", b"bad")
            with self.assertRaises(ValueError):
                extract(archive, root / "game")
            self.assertFalse((root / "outside.exe").exists())

    def test_extracts_game_directory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "media.zip"
            with ZipFile(archive, "w") as bundle:
                bundle.writestr("grandchs/CHESS.BAT", "GMCHESS")
            extract(archive, root / "game")
            self.assertEqual((root / "game/grandchs/CHESS.BAT").read_text(), "GMCHESS")
