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


def ready_session(move_timeout: float | None = None) -> PlaySession:
    session = PlaySession(FakeConnector(), move_timeout=move_timeout)
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
    session = ready_session(move_timeout=20)
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


def test_recovery_from_transient_unrelated_placement_keeps_unlimited_wait() -> None:
    session = ready_session()
    unrelated = chess.Board()
    unrelated.push_uci("d2d4")
    session.observe(FRAME, unrelated.board_fen())
    assert session.deadline == 0.0 and not session.ready
    session.observe(FRAME, chess.STARTING_BOARD_FEN)
    assert session.ready and session.deadline == 0.0


def test_native_search_can_exceed_old_three_minute_deadline() -> None:
    session = ready_session()
    session.submit('e2e4')
    board = chess.Board()
    board.push_uci('e2e4')
    session.observe(FRAME, board.board_fen())
    assert session.deadline == 0.0
    with patch('emulation.play.monotonic', return_value=10**12):
        session.observe(FRAME, board.board_fen())
        assert session.board is not None and not session.ready
        board.push_uci('e7e5')
        session.observe(FRAME, board.board_fen())
    assert session.ready and session.board is not None
    assert session.board.move_stack == board.move_stack


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
    assert client.events[-2:] == [("key", {"name": "Down", "delay_ms": 150}),
                                 ("key", {"name": "Return", "delay_ms": 150})]
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


def test_grandmaster_resignation_requires_the_explicit_dialog() -> None:
    from emulation.play import GameResigned
    connector = Connector(RecordingClient())  # type: ignore[arg-type]
    connector.advance(connector.references['new-game-confirm'])
    with pytest.raises(GameResigned) as caught:
        connector.advance(connector.references['resignation'])
    assert caught.value.color == chess.BLACK
    connector.human_color = chess.BLACK
    with pytest.raises(GameResigned) as caught:
        connector.advance(connector.references['resignation'])
    assert caught.value.color == chess.WHITE


def test_mate_forecast_is_acknowledged_but_is_not_a_result() -> None:
    client = RecordingClient()
    connector = Connector(client)  # type: ignore[arg-type]
    session = ready_session()
    session.connector = connector
    notice = connector.references['mate-announcement']
    session.observe(notice, None)
    assert session.resigned is None
    assert session.board is not None and not session.board.is_game_over()
    assert client.events == [('key', {'name': 'Return', 'delay_ms': 150})]
    connector.advance(notice)
    assert len(client.events) == 1
    connector.advance(connector.references['recognition'])
    assert client.events[-2:] == [('pointer', {'x': 630, 'y': 470}), ('pointer', {'x': 0, 'y': 0})]
    assert not connector.announcement_pending


def test_information_notice_does_not_acknowledge_two_button_decisions() -> None:
    connector = Connector(RecordingClient())  # type: ignore[arg-type]
    notice = connector.references['mate-announcement'].copy()
    notice.paste(notice.crop((250, 225, 390, 244)), (246, 225))
    assert connector.information_dialog(notice)
    assert not connector.information_dialog(connector.references['resignation'])
    assert not connector.information_dialog(connector.references['new-game-confirm'])


def test_game_completed_notice_is_dismissed_before_board_decides_the_result() -> None:
    client = RecordingClient()
    connector = Connector(client)  # type: ignore[arg-type]
    session = ready_session()
    session.connector = connector
    session.observe(connector.references['game-completed'], None)
    assert client.events == [('key', {'name': 'Return', 'delay_ms': 150})]
    assert session.resigned is None
    assert session.board is not None and not session.board.is_game_over()


def test_post_game_rating_and_new_game_are_declined_to_preserve_terminal_board() -> None:
    client = RecordingClient()
    connector = Connector(client)  # type: ignore[arg-type]
    connector.advance(connector.references['game-completed'])
    connector.advance(connector.references['rating-calculation'])
    connector.advance(connector.references['new-game-confirm'])
    assert [data['name'] for kind, data in client.events if kind == 'key'] == ['Return', 'Escape', 'Escape']
    connector.advance(connector.references['recognition'])
    assert not connector.announcement_pending
    connector.reset()
    assert not connector.completed_notice_seen


def test_c64_missed_return_requires_advancing_human_clock() -> None:
    from games.Chess_19xx.play import prompt_mask
    client = RecordingClient()
    connector = C64Connector(client)  # type: ignore[arg-type]
    frame = connector.reference.copy()
    from PIL import ImageDraw
    ImageDraw.Draw(frame).rectangle((430, 325, 434, 330), fill=(200, 200, 200))
    connector.current_key = 'Return'
    connector.before = prompt_mask(frame)
    connector.advance(frame)
    connector.advance(frame)
    assert client.events == []
    ImageDraw.Draw(frame).rectangle((425, 203, 430, 207), fill=(0, 0, 0))
    connector.advance(frame)
    assert len(client.events) == 1
    assert client.events[0][1]['name'] == 'Return'
    connector.advance(frame)
    assert len(client.events) == 1


def test_session_reports_resignation_as_game_over_without_a_transport_error() -> None:
    from emulation.play import GameResigned

    class ResigningConnector(FakeConnector):
        def advance(self, frame: Image.Image) -> None:
            raise GameResigned(chess.BLACK)

    session = PlaySession(ResigningConnector())
    session.new_game()
    session.observe(FRAME, chess.STARTING_BOARD_FEN)
    assert session.resigned == chess.BLACK
    assert not session.ready
    assert session.deadline == 0
    assert session.message == 'Game over: 1-0 (black resigned)'
    session.observe(FRAME, None)
    session.invalidate('reset')
    assert session.resigned is None


def test_c64_types_hyphenated_move_only_after_prompt_acknowledgements(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RecordingClient()
    connector = C64Connector(client)  # type: ignore[arg-type]
    connector.move(chess.Move.from_uci("a2a3"))
    frame = connector.reference.copy()
    entered = ''

    def observed_prefix(frame: Image.Image, prefix: str) -> bool:
        return prefix == entered

    monkeypatch.setattr(connector, 'prefix_visible', observed_prefix)
    connector.advance(frame)
    assert client.events == [("key", {"name": "a", "delay_ms": 200, "window_title": "VICE (C64SC)"})]
    connector.advance(frame)
    assert len(client.events) == 1  # A missed key cannot advance the sequence.
    for entered in ['A', 'A2', 'A2-', 'A2-A', 'A2-A3']:
        connector.advance(frame)
        connector.advance(frame)
    assert [data["name"] for _, data in client.events] == ["a", "2", "minus", "a", "3", "Return"]
    assert all(data["delay_ms"] == 200 for _, data in client.events)
    connector.advance(frame)
    assert len(client.events) == 6


def test_c64_retries_missing_destination_file_without_advancing_to_rank() -> None:
    from pathlib import Path
    from games.Chess_19xx.text import prefix_complete
    client = RecordingClient()
    connector = C64Connector(client)  # type: ignore[arg-type]
    connector.typed_prefix = 'H4-F'
    connector.previous_prefix = 'H4-'
    connector.current_key = 'f'
    connector.awaiting_character = True
    connector.keys_pending = ['3', 'Return']
    path = Path(__file__).parent / 'fixtures/recognition/chess19xx-input-h4-prefix.png'
    with Image.open(path) as frame:
        assert prefix_complete(frame, 3)
        assert not prefix_complete(frame, 4)
        for _ in range(4):
            connector.advance(frame)
    assert [data['name'] for _, data in client.events] == ['f']
    assert connector.keys_pending == ['3', 'Return']


def test_c64_coordinate_echo_requires_the_complete_prefix_and_blank_tail() -> None:
    from pathlib import Path
    from games.Chess_19xx.text import prefix_complete
    path = Path(__file__).parent / 'fixtures/recognition/chess19xx-input-e2e4.png'
    with Image.open(path) as frame:
        assert prefix_complete(frame, 5)
        assert not prefix_complete(frame, 4)
        assert not prefix_complete(frame, 6)


def test_c64_faint_last_digit_is_an_occupied_cell_without_font_guessing() -> None:
    from pathlib import Path
    from games.Chess_19xx.text import prefix_complete
    path = Path(__file__).parent / 'fixtures/recognition/chess19xx-input-c4d5.png'
    with Image.open(path) as frame:
        assert prefix_complete(frame, 5)
        assert not prefix_complete(frame, 4)


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
        connector.move(chess.Move.from_uci("a7a8n"))
    assert not client.events


def test_c64_queen_promotion_uses_coordinates_and_still_requires_observation() -> None:
    client = RecordingClient()
    connector = C64Connector(client)  # type: ignore[arg-type]
    connector.move(chess.Move.from_uci('a7a8q'))
    assert connector.keys_pending == ['a', '7', 'minus', 'a', '8', 'Return']
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
