"""Native display fixtures, changed positions and frame-linked publications."""

from io import BytesIO
import json
from pathlib import Path
from threading import Thread
from tempfile import TemporaryDirectory
from typing import Iterator

import chess
import numpy as np
from PIL import Image
import pytest

from emulation.client import RuntimeClient
from emulation.server import Session, make_server
from recognition.board import RecognitionError, square_box
from recognition.runtime import FrameRecorder, RuntimeRecognizer, create_reader


@pytest.fixture
def evidence_directory() -> Iterator[Path]:
    with TemporaryDirectory() as directory:
        yield Path(directory)


def encoded(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize("game", ["grandmaster", "chess19xx"])
def test_native_starting_frames(game: str) -> None:
    reader = create_reader(game)
    with Image.open(reader.profile.reference) as frame:
        result = reader.read(frame)
    assert result.placement == chess.STARTING_BOARD_FEN
    assert len(result.squares) == 64


@pytest.mark.parametrize("game", ["grandmaster", "chess19xx"])
def test_empty_and_menu_frames_are_rejected(game: str) -> None:
    reader = create_reader(game)
    with pytest.raises(RecognitionError):
        reader.read(Image.new("RGB", (640, 480)))
    with pytest.raises(RecognitionError, match="640x480"):
        reader.read(Image.new("RGB", (320, 240)))
    empty = Image.new("RGB", (640, 480))
    for row in range(8):
        for file in range(8):
            empty.paste(reader.profile.backgrounds[(file + row) % 2], square_box(reader.profile.region, file, row))
    with pytest.raises(RecognitionError, match="king"):
        reader.read(empty)


def test_moved_piece_on_opposite_square_color() -> None:
    reader = create_reader("grandmaster")
    with Image.open(reader.profile.reference) as frame:
        frame = frame.convert("RGB")
    source = square_box(reader.profile.region, 4, 6)  # e2
    target = square_box(reader.profile.region, 4, 5)  # e3
    pixels = np.asarray(frame.crop(source)).copy()
    pixels[np.all(pixels == reader.profile.backgrounds[0], axis=2)] = reader.profile.backgrounds[1]
    frame.paste(reader.profile.backgrounds[0], source)
    frame.paste(Image.fromarray(pixels), target[:2])
    expected = chess.Board()
    expected.push_uci("e2e3")
    assert reader.read(frame).placement == expected.board_fen()


@pytest.mark.parametrize("fixture_name,moves", [
    ("grandmaster-e4-e5.png", ["e2e4", "e7e5"]),
    ("grandmaster-nf3-nc6.png", ["e2e4", "e7e5", "g1f3", "b8c6"]),
])
def test_live_grandmaster_move_and_reply(fixture_name: str, moves: list[str]) -> None:
    expected = chess.Board()
    for move in moves:
        expected.push_uci(move)
    fixture = Path(__file__).parent / "fixtures/recognition" / fixture_name
    with Image.open(fixture) as frame:
        assert create_reader("grandmaster").read(frame).placement == expected.board_fen()


def test_live_c64_knight_on_resampled_light_square() -> None:
    board = chess.Board()
    board.push_uci("a2a3")
    board.push_uci("b8c6")
    fixture = Path(__file__).parent / "fixtures/recognition/chess19xx-a3-nc6.png"
    with Image.open(fixture) as frame:
        assert create_reader("chess19xx").read(frame).placement == board.board_fen()


class ImageBackend:
    def __init__(self, png: bytes) -> None:
        self.png = png

    def capture(self) -> bytes:
        return self.png

    def key(self, name: str) -> None:
        pass

    def click(self, x: int, y: int) -> None:
        pass


def test_confirmation_publication_and_stale_frame(evidence_directory: Path) -> None:
    reader = create_reader("grandmaster")
    backend = ImageBackend(reader.profile.reference.read_bytes())
    session = Session(backend)
    server = make_server(session, "127.0.0.1", 0)
    thread = Thread(target=server.serve_forever)
    thread.start()
    try:
        client = RuntimeClient(f"http://127.0.0.1:{server.server_port}")
        recorder = FrameRecorder(evidence_directory, "grandmaster")
        recognizer = RuntimeRecognizer("grandmaster", client, recorder)
        snapshot = client.snapshot()
        assert "confirming" in recognizer.process(snapshot)
        assert session.board is None
        assert "Recognized piece" in recognizer.process(client.snapshot())
        assert session.board is not None
        assert session.board["kind"] == "placement"
        assert session.board["frame_id"] == snapshot["frame_id"]
        assert chess.Board(session.board["fen"]).board_fen() == chess.STARTING_BOARD_FEN
        backend.png = encoded(Image.new("RGB", (640, 480)))
        newer = client.snapshot()
        assert "advanced" in recognizer.process(snapshot)
        assert "Unrecognized" in recognizer.process(newer)
        assert session.board["frame_id"] != newer["frame_id"]
        assert len(list(recorder.directory.glob("*.json"))) == 2
        metadata = json.loads(next(recorder.directory.glob("00001*.json")).read_text())
        assert metadata["placement"] == chess.STARTING_BOARD_FEN
        assert len(metadata["squares"]) == 64
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_debug_limit_and_rejected_frame_evidence(evidence_directory: Path) -> None:
    recorder = FrameRecorder(evidence_directory, "chess19xx", limit=1)
    reader = create_reader("chess19xx")
    png = encoded(Image.new("RGB", (640, 480)))
    recorder.save(png, 1, reader, None, "menu visible")
    recorder.save(reader.profile.reference.read_bytes(), 2, reader, None, "other frame")
    assert len(list(recorder.directory.glob("*.png"))) == 3
    metadata = json.loads(next(recorder.directory.glob("*.json")).read_text())
    assert metadata["error"] == "menu visible"
    assert metadata["placement"] is None


def test_c64_open_outline_knight() -> None:
    fixture = Path(__file__).parent / "fixtures/recognition/chess19xx-outlined-knight-c6.png"
    with Image.open(fixture) as frame:
        result = create_reader("chess19xx").read(frame)
    assert result.placement == "1r3rk1/p1p2ppp/B1Nqp3/1P1p1b2/3P4/2b1P3/3K1PPP/R1R5"


def test_c64_moved_king_resampling() -> None:
    reader = create_reader("chess19xx")
    with Image.open(reader.profile.reference.with_name("recognition-king-a4.png")) as frame:
        result = reader.read(frame)
    assert result.placement == "4rrk1/pBpq1ppp/R1N1p3/1P1p1b2/K2P1P2/4P1P1/7P/2R5"
