"""Profile validation and benchmark configuration are independent of emulators."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from emulation import difficulty
from emulation.participants import UciParticipant


def test_wrong_runtime_is_rejected_before_any_input(monkeypatch: pytest.MonkeyPatch) -> None:
    setter = Mock()
    module = SimpleNamespace(PROFILES=(('novice', 'Novice'),), set_difficulty=setter)
    monkeypatch.setattr(difficulty, 'game_module', lambda game: module)
    client = Mock()
    client.snapshot.return_value = {'game': 'other'}
    with pytest.raises(ValueError, match='Expected runtime'):
        difficulty.set_difficulty('grandmaster', 'novice', client)
    setter.assert_not_called()
    client.send.assert_not_called()


def test_unknown_profile_is_rejected_before_any_input(monkeypatch: pytest.MonkeyPatch) -> None:
    module = SimpleNamespace(PROFILES=(('novice', 'Novice'),))
    monkeypatch.setattr(difficulty, 'game_module', lambda game: module)
    client = Mock()
    with pytest.raises(ValueError, match='Unknown difficulty'):
        difficulty.set_difficulty('grandmaster', 'made-up', client)
    client.snapshot.assert_not_called()
    client.send.assert_not_called()


def test_program_without_presets_gets_one_default_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    original = difficulty.profiles
    monkeypatch.setattr(difficulty, 'profiles', lambda game: () if game == 'chess19xx' else original(game))
    entries = {name: definition for name, definition in difficulty.default_engines().items()
               if definition['game'] == 'chess19xx'}
    assert list(entries) == ['chess19xx']
    assert 'difficulty' not in entries['chess19xx']


def test_stockfish_is_configured_at_maximum_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = Mock()
    engine.options = {'Skill Level': SimpleNamespace(max=20), 'UCI_LimitStrength': object()}
    monkeypatch.setattr('chess.engine.SimpleEngine.popen_uci', lambda *args, **kwargs: engine)
    participant = UciParticipant('stockfish', 5, .3)
    engine.configure.assert_called_once_with({'Skill Level': 20, 'UCI_LimitStrength': False})
    participant.close()
    engine.close.assert_called_once()


def test_difficulty_is_verified_after_reset_before_white_search(monkeypatch: pytest.MonkeyPatch) -> None:
    import chess
    from emulation import participants
    events: list[str] = []
    connector = SimpleNamespace(
        human_color=chess.WHITE, reset=lambda: events.append('reset'),
        play_as=lambda color: events.append('start-white'),
    )
    monkeypatch.setattr(participants, 'create_connector', lambda game, client: connector)
    monkeypatch.setattr(participants, 'create_reader', lambda game: None)

    def confirm_reset(participant: participants.VintageParticipant) -> None:
        events.append('confirmed-reset')
        participant.session.ready = True
        participant.session.board = chess.Board()

    monkeypatch.setattr(participants.VintageParticipant, 'observe', confirm_reset)
    setter = Mock(side_effect=lambda *args, **kwargs: events.append('verified-difficulty'))
    monkeypatch.setattr(difficulty, 'set_difficulty', setter)
    client = Mock()
    participant = participants.VintageParticipant('grandmaster', client, chess.WHITE, 90,
                                                 difficulty='expert')
    assert events == ['reset', 'confirmed-reset', 'verified-difficulty', 'start-white']
    setter.assert_called_once_with('grandmaster', 'expert', client, timeout=90)
    assert participant.thinking_timeout is None


def test_vintage_reply_wait_has_no_default_outer_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    import chess
    from emulation import participants
    participant = participants.VintageParticipant.__new__(participants.VintageParticipant)
    participant.timeout = 1
    participant.thinking_timeout = None
    board = chess.Board()
    board.push_uci('e2e4')
    participant.session = SimpleNamespace(position_confirmed=False, board=board.copy())
    participant.submit_opponent = Mock()  # type: ignore[method-assign]
    clock = iter((0.0, 100000.0))
    monkeypatch.setattr(participants, 'monotonic', lambda: next(clock))

    def observe() -> None:
        assert participants.monotonic() == 100000.0
        participant.session.board.push_uci('e7e5')
        participant.session.position_confirmed = True

    participant.observe = observe  # type: ignore[method-assign]
    assert participant.choose(board).uci() == 'e7e5'
