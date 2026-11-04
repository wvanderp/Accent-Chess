"""Play state must follow emulator evidence, never input timing."""

from unittest.mock import patch

import chess
from PIL import Image
import pytest

from emulation.play import PlaySession
from games.Grandmaster_Chess.play import Connector
from games.Chess_19xx.play import Connector as C64Connector


class FakeConnector:
    human_color = chess.WHITE

    def __init__(self) -> None:
        self.moves: list[chess.Move] = []

    def reset(self) -> None:
        pass

    def advance_reset(self, frame: Image.Image, placement: str | None) -> bool:
        return placement == chess.STARTING_BOARD_FEN

    def move(self, move: chess.Move) -> None:
        self.moves.append(move)

    def advance(self, frame: Image.Image) -> None:
        pass


FRAME = Image.new("RGB", (640, 480))


def ready_session() -> PlaySession:
    session = PlaySession(FakeConnector())
    session.new_game()
    assert not session.ready
    session.observe(FRAME, None)
    assert session.board is None
    session.observe(FRAME, chess.STARTING_BOARD_FEN)
    assert session.ready
    return session


def test_move_acknowledgement_and_engine_turn() -> None:
    session = ready_session()
    session.submit("e2e4")
    assert session.board is not None and session.board.turn == chess.WHITE
    session.observe(FRAME, chess.STARTING_BOARD_FEN)
    assert not session.ready
    board = chess.Board()
    board.push_uci("e2e4")
    session.observe(FRAME, board.board_fen())
    assert session.board is not None and session.board.turn == chess.BLACK
    with pytest.raises(ValueError):
        session.submit("g1f3")
    board.push_uci("e7e5")
    session.observe(FRAME, board.board_fen())
    assert session.ready
    assert session.board.fen() == board.fen()


def test_fast_reply_and_move_history() -> None:
    session = ready_session()
    expected = chess.Board()
    for human, engine in [("e2e4", "e7e5"), ("g1f3", "b8c6"), ("f1c4", "g8f6"), ("e1g1", "f8c5")]:
        session.submit(human)
        expected.push_uci(human)
        expected.push_uci(engine)
        session.observe(FRAME, expected.board_fen())
        assert session.ready
        assert session.board is not None and session.board.fen() == expected.fen()
    assert not session.board.has_kingside_castling_rights(chess.WHITE)


def test_unrelated_positions_and_missing_frames_disable_input() -> None:
    session = ready_session()
    session.observe(FRAME, None)
    assert not session.ready
    with pytest.raises(ValueError):
        session.submit("e2e4")
    unrelated = chess.Board()
    unrelated.push_uci("d2d4")
    session.observe(FRAME, unrelated.board_fen())
    assert not session.ready
    assert session.board is not None and session.board.board_fen() == chess.STARTING_BOARD_FEN


def test_illegal_move_timeout_and_reset() -> None:
    session = ready_session()
    with pytest.raises(ValueError):
        session.submit("e2e5")
    assert session.ready
    session.submit("e2e4")
    with patch("emulation.play.monotonic", return_value=session.deadline + 1):
        session.observe(FRAME, chess.STARTING_BOARD_FEN)
    assert session.board is None and not session.ready
    session.new_game()
    session.observe(FRAME, chess.STARTING_BOARD_FEN)
    assert session.ready
    assert session.board is not None and not session.board.move_stack


def test_recovery_from_transient_unrelated_placement_clears_deadline() -> None:
    session = ready_session()
    unrelated = chess.Board()
    unrelated.push_uci("d2d4")
    session.observe(FRAME, unrelated.board_fen())
    assert session.deadline and not session.ready
    session.observe(FRAME, chess.STARTING_BOARD_FEN)
    assert session.ready and session.deadline == 0.0


class RecordingClient:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def send(self, action: str, data: dict[str, object]) -> None:
        self.events.append((action, data))


def test_grandmaster_reset_is_gated_by_menu_and_dialog_pixels() -> None:
    client = RecordingClient()
    connector = Connector(client)  # type: ignore[arg-type]
    connector.reset()
    reference = connector.references["recognition"]
    assert not connector.advance_reset(reference, chess.STARTING_BOARD_FEN)
    before = len(client.events)
    assert not connector.advance_reset(reference, chess.STARTING_BOARD_FEN)
    assert len(client.events) == before
    connector.advance_reset(connector.references["game-menu"], None)
    assert client.events[-2:] == [("key", {"name": "Down"}), ("key", {"name": "Return"})]
    connector.advance_reset(connector.references["new-game-confirm"], None)
    before = len(client.events)
    connector.advance_reset(connector.references["new-game-confirm"], None)
    assert len(client.events) == before
    connector.advance_reset(reference, None)
    assert client.events[-1] == ("pointer", {"x": 0, "y": 0})
    assert connector.advance_reset(reference, chess.STARTING_BOARD_FEN)


def test_grandmaster_coordinate_move_input() -> None:
    client = RecordingClient()
    connector = Connector(client)  # type: ignore[arg-type]
    connector.move(chess.Move.from_uci("e2e4"))
    assert [data["name"] for _, data in client.events] == ["e", "2", "e", "4", "Return"]


def test_c64_types_hyphenated_move_only_after_prompt_acknowledgements() -> None:
    client = RecordingClient()
    connector = C64Connector(client)  # type: ignore[arg-type]
    connector.move(chess.Move.from_uci("a2a3"))
    frame = connector.reference.copy()
    connector.advance(frame)
    assert client.events == [("key", {"name": "a", "delay_ms": 200, "window_title": "VICE (C64SC)"})]
    connector.advance(frame)
    assert len(client.events) == 1  # A missed key cannot advance the sequence.
    for index in range(5):
        frame.paste((213, 213, 213), (430 + index * 7, 326, 433 + index * 7, 330))
        connector.advance(frame)
        connector.advance(frame)
    assert [data["name"] for _, data in client.events] == ["a", "2", "minus", "a", "3", "Return"]
    assert all(data["delay_ms"] == 200 for _, data in client.events)
    connector.advance(frame)
    assert len(client.events) == 6


def test_c64_reset_requires_clean_starting_board_and_input() -> None:
    client = RecordingClient()
    connector = C64Connector(client)  # type: ignore[arg-type]
    connector.reset()
    assert client.events == [("key", {"name": "F1", "delay_ms": 200, "window_title": "VICE (C64SC)"})]
    frame = connector.reference.copy()
    assert not connector.advance_reset(frame, None)
    assert connector.advance_reset(frame, chess.STARTING_BOARD_FEN)
    frame.paste((213, 213, 213), (430, 326, 433, 330))
    assert not connector.advance_reset(frame, chess.STARTING_BOARD_FEN)


def test_c64_retries_only_the_unacknowledged_key_with_a_bound() -> None:
    client = RecordingClient()
    connector = C64Connector(client)  # type: ignore[arg-type]
    connector.move(chess.Move.from_uci("a2a3"))
    frame = connector.reference.copy()
    connector.advance(frame)
    for _ in range(20):
        connector.advance(frame)
    assert [data["name"] for _, data in client.events] == ["a", "a", "a"]
    assert connector.keys_pending == ["2", "minus", "a", "3", "Return"]


def test_c64_rejects_unverified_promotion_without_sending_keys() -> None:
    client = RecordingClient()
    connector = C64Connector(client)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="promotion"):
        connector.move(chess.Move.from_uci("a7a8q"))
    assert not client.events


def test_attach_from_active_clock_without_reset() -> None:
    class ClockConnector(FakeConnector):
        def clock_samples(self, frame: Image.Image) -> tuple[bytes, bytes]:
            return frame.crop((0, 0, 1, 1)).tobytes(), b"black"

    session = PlaySession(ClockConnector())
    session.observe(FRAME, chess.STARTING_BOARD_FEN)
    session.observe(FRAME, chess.STARTING_BOARD_FEN)
    assert session.board is None
    changed = FRAME.copy()
    changed.putpixel((0, 0), (255, 255, 255))
    session.observe(changed, chess.STARTING_BOARD_FEN)
    assert session.ready
    assert session.board is not None and session.board.turn == chess.WHITE
    assert not session.board.castling_rights


def test_analysis_available_on_confirmed_computer_turn() -> None:
    session = ready_session()
    session.submit("e2e4")
    assert not session.state()["analyzable"]
    board = chess.Board()
    board.push_uci("e2e4")
    session.observe(FRAME, board.board_fen())
    assert session.state()["turn"] == "black"
    assert session.state()["analyzable"]
    assert not session.ready
    session.observe(FRAME, None)
    assert session.state()["turn"] is None
    assert not session.state()["analyzable"]


def test_c64_lower_clock_is_white() -> None:
    connector = C64Connector(None)
    baseline = connector.clock_samples(FRAME)
    changed = FRAME.copy()
    changed.putpixel((450, 205), (255, 255, 255))
    samples = connector.clock_samples(changed)
    assert samples[0] != baseline[0]
    assert samples[1] == baseline[1]
