"""Keep the ST runtime independent of DOS and verify media integrity wiring."""

from pathlib import Path
from unittest.mock import patch

from PIL import Image
import pytest

from emulation.atarist import command
from games.Battle_Chess import setup
from recognition.runtime import create_reader
from recognition.board import RecognitionError


def test_runtime_uses_extracted_firmware(tmp_path: Path) -> None:
    rom = tmp_path / "firmware" / "emutos-192k-1.3" / "etos192us.img"
    rom.parent.mkdir(parents=True)
    rom.write_bytes(b"firmware fixture")
    with patch("emulation.atarist.download", return_value=tmp_path / "emutos.zip") as fetch, \
            patch("emulation.atarist.extract"):
        arguments = command(tmp_path, tmp_path / "disk.st")
    assert arguments[0] == "hatari"
    assert arguments[arguments.index("--tos") + 1] == str(rom)
    assert arguments[arguments.index("--machine") + 1] == "st"
    assert fetch.call_args.args[2] == "ada8bf61e31ce68962305f26b3c3f44d9950fe2f"


def test_game_verifies_disk_and_autostarts_program(tmp_path: Path) -> None:
    with patch.object(setup, "download", return_value=tmp_path / "battlechess.st") as fetch, \
            patch.object(setup, "command", return_value=["hatari"]):
        arguments = setup.prepare(tmp_path)
    assert fetch.call_args.args[2] == "b8260f86f75ce9419d28c77c39b5886852e688f6"
    assert arguments == ["hatari", "--auto", "A:\\CHESS.PRG"]


@pytest.mark.parametrize("filename,placement", [
    ("battlechess-black-castled.png", "rnbq1rk1/ppp1b1pp/8/3p1p2/2PPn3/3B1N2/PP1N1PPP/R1BQK2R"),
    ("battlechess-both-castled.png", "r4rk1/ppp1b1pp/2n5/3b1p2/3Pn3/5N2/PP1N1PPP/R1BQ1RK1"),
    ("battlechess-before-mate.png", "r3rk2/ppp3pp/3b1n1N/5p2/3P4/5P2/QP1B2PP/1N2R1K1"),
])
def test_live_game_positions(filename: str, placement: str) -> None:
    with Image.open(Path(__file__).parent / "fixtures/recognition" / filename) as frame:
        assert create_reader("battlechess").read(frame).placement == placement


def test_checkmate_dialog_cannot_publish_a_guessed_board() -> None:
    with Image.open(Path(__file__).parents[1] / "docs/evidence/battlechess/checkmate.png") as frame:
        with pytest.raises(RecognitionError):
            create_reader("battlechess").read(frame)
