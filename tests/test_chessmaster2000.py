"""Regressions from original C64 media and its menu/input protocol."""

from pathlib import Path
from unittest.mock import patch

import chess
import pytest
from PIL import Image

from emulation.backend import X11Backend
from games.Chessmaster_2000 import setup
from games.Chessmaster_2000.play import Connector
from recognition.runtime import create_reader


@pytest.mark.parametrize("filename,placement", [
    ("recognition.png", chess.STARTING_BOARD_FEN),
    ("../../../tests/fixtures/recognition/chessmaster2000-rook-e1.png",
     "r3k2r/p1p3pp/2p2p2/3pn3/1P5P/3B4/PP5P/RNBKR3"),
    ("../../../tests/fixtures/recognition/chessmaster2000-bishop-a4-exchange.png",
     "r1bqkb1r/2pp1ppp/p7/1p2n3/B2Pn3/8/PPP1QPPP/RNB1K2R"),
    ("../../../tests/fixtures/recognition/chessmaster2000-bishop-a4.png",
     "r1bqk2r/2pp1ppp/p7/1p2n3/Bb1PQ3/8/PPP2PPP/RNB1K2R"),
    ("../../../tests/fixtures/recognition/chessmaster2000-queen-d5.png",
     "r1b2rk1/2p2ppp/p7/1p1qP3/B7/2N5/PP3PPP/R1B1K2R"),
    ("../../../tests/fixtures/recognition/chessmaster2000-nf3-nc6.png",
     "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R"),
    ("../../../tests/fixtures/recognition/chessmaster2000-captures.png",
     "r3k2r/p1pn1ppp/2p5/3pP3/1P5P/3B4/PP5P/RNBbK2R"),
    ("../../../tests/fixtures/recognition/chessmaster2000-checkmate.png",
     "3rr3/p1p4p/Pkp3p1/3p4/NP2p2P/8/1P2B2P/R2KR3"),
    ("../../../tests/fixtures/recognition/chessmaster2000-final-checkmate.png",
     "4R2k/5ppp/p7/8/p7/4B3/Pr3PPP/2R3K1"),
    ("../../../tests/fixtures/recognition/chessmaster2000-knight-promotion.png",
     "N6k/8/8/8/8/8/8/4K3"),
])
def test_native_positions(filename: str, placement: str) -> None:
    reader = create_reader("chessmaster2000")
    path = reader.profile.reference.parent / filename
    with Image.open(path) as frame:
        assert reader.read(frame).placement == placement


class InputClient:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def send(self, action: str, data: dict[str, object]) -> None:
        assert action == "key"
        self.keys.append(str(data["name"]))


def test_reset_requires_confirmation_and_actual_board() -> None:
    client = InputClient()
    connector = Connector(client)  # type: ignore[arg-type]
    connector.reset()
    root = create_reader("chessmaster2000").profile.reference.parent
    with Image.open(root / "menu.png") as menu, Image.open(root / "playing.png") as playing, \
            Image.open(root / "new-game-confirm.png") as confirm, Image.open(root / "recognition.png") as board:
        assert not connector.advance_reset(menu, None)
        assert client.keys == ["ctrl+a"]
        # A stale menu must not trigger the next shortcut.
        assert not connector.advance_reset(menu, None)
        assert client.keys == ["ctrl+a"]
        assert not connector.advance_reset(playing, None)
        assert not connector.advance_reset(confirm, None)
        assert not connector.advance_reset(menu, None)
        assert not connector.advance_reset(menu, chess.STARTING_BOARD_FEN)
        assert connector.advance_reset(board, chess.STARTING_BOARD_FEN)
        assert client.keys == ["ctrl+a", "ctrl+b", "y", "F1"]


def test_move_waits_for_menu_and_visible_character_growth() -> None:
    client = InputClient()
    connector = Connector(client)  # type: ignore[arg-type]
    reader = create_reader("chessmaster2000")
    connector.move(chess.Move.from_uci("e2e4"))
    with Image.open(reader.profile.reference) as board, \
            Image.open(reader.profile.reference.with_name("menu.png")) as menu:
        connector.advance(board)
        assert client.keys == ["F1"]
        connector.advance(menu)
        assert client.keys == ["F1", "e"]
        for _ in range(5):
            connector.advance(menu)
        assert client.keys == ["F1", "e"]


@pytest.mark.parametrize("suffix", ["q", "r", "b", "n"])
def test_promotion_keeps_the_fifth_input_character(suffix: str) -> None:
    connector = Connector(InputClient())  # type: ignore[arg-type]
    connector.move(chess.Move.from_uci("a7a8" + suffix))
    assert connector.keys_pending == list("a7a8" + suffix)


def test_terminal_message_in_either_move_column() -> None:
    connector = Connector(InputClient())  # type: ignore[arg-type]
    root = create_reader("chessmaster2000").profile.reference.parent
    with Image.open(root / "checkmate.png") as mate, Image.open(root / "menu.png") as menu:
        assert connector.terminal_message(mate)
        assert not connector.terminal_message(menu)
        other_column = menu.convert("RGB")
        other_column.paste(mate.crop((405, 222, 479, 229)), (344, 222))
        assert connector.terminal_message(other_column)


def test_promotion_draw_does_not_wait_for_an_impossible_engine_reply() -> None:
    client = InputClient()
    connector = Connector(client)  # type: ignore[arg-type]
    connector.set_position(chess.Board("7k/P7/8/8/8/8/8/4K3 w - - 0 1"))
    connector.move(chess.Move.from_uci("a7a8n"))
    assert connector.terminal_pending
    connector.input_stage = "hide"
    path = Path(__file__).parent / "fixtures/recognition/chessmaster2000-promotion-draw-menu.png"
    with Image.open(path) as frame:
        connector.reply_before = frame.crop((405, 163, 461, 233)).tobytes()
        connector.advance(frame)
    assert client.keys == ["F1", "F1"]
    assert connector.input_stage == "show_board"


def test_f1_recovery_requires_an_unchanged_ready_text_view() -> None:
    client = InputClient()
    connector = Connector(client)  # type: ignore[arg-type]
    root = create_reader("chessmaster2000").profile.reference.parent
    with Image.open(root / "menu.png") as menu, Image.open(root / "recognition.png") as board:
        assert not connector.show_board(menu)
        assert client.keys == []
        assert not connector.show_board(menu)
        assert client.keys == ["F1"]
        assert connector.show_board(board)


def test_setup_downloads_both_verified_sides_and_uses_real_drive(tmp_path: Path) -> None:
    with patch("games.Chessmaster_2000.setup.download", side_effect=lambda url, path, sha1: path) as media, \
            patch("emulation.c64.download", side_effect=lambda url, path, sha1: path):
        command = setup.prepare(tmp_path)
    assert media.call_count == 2
    assert all(len(call.args[2]) == 40 for call in media.call_args_list)
    assert "-drive8truedrive" in command
    assert "-dos1541" in command
    assert command[-2:] == ["-autostart", str(tmp_path / "side-a.d64")]


def test_shortcut_validation_keeps_xdotool_commands_out() -> None:
    with patch("emulation.backend.subprocess.run") as run:
        X11Backend().key("ctrl+a")
        assert run.call_args.args[0][-1] == "ctrl+a"
    for name in ("ctrl+", "a+b", "ctrl+a key Return", "--help", "ctrl+a;quit"):
        with patch("emulation.backend.subprocess.run") as run, pytest.raises(ValueError):
            X11Backend().key(name)
        run.assert_not_called()
