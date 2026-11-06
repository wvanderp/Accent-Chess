from pathlib import Path
import json

import chess
import pytest

from emulation import tournament
from emulation.tournament import Ledger, runnable, run_match
from emulation.tournament_lock import ledger_lock
from emulation.play import GameResigned


def test_redirected_windows_output_accepts_unicode_build_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    from io import BytesIO, TextIOWrapper
    import sys
    output = BytesIO()
    redirected = TextIOWrapper(output, encoding='cp1252')
    monkeypatch.setattr(sys, 'stdout', redirected)
    monkeypatch.setattr(sys, 'stderr', TextIOWrapper(BytesIO(), encoding='cp1252'))
    tournament.configure_output()
    print('Created symlink source → destination')
    redirected.flush()
    assert output.getvalue().decode('utf-8').splitlines() == ['Created symlink source → destination']


def test_history_survives_restart(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    engines = ledger.state['engines']
    white, black = ledger.pending(engines)[0]
    directory = ledger.start(white, black)
    ledger.finish(directory, None, 'timeout')
    ledger = Ledger(tmp_path)
    assert (white, black) in ledger.pending(engines)
    directory = ledger.start(white, black)
    ledger.finish(directory, '1-0', None)
    ledger = Ledger(tmp_path)
    assert (white, black) not in ledger.pending(engines)
    assert ledger.ranking(engines)[0]['engine'] == white
    assert ledger.ranking(engines)[0]['points'] == 1
    assert len(ledger.state['pairings'][0]['attempts']) == 2


def test_capabilities_preserve_unsupported_pairings(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    engines = {game: {'kind': 'vintage', 'game': game}
               for game in ('grandmaster', 'chess19xx', 'chessmaster2000', 'battlechess')}
    engines['uci'] = {'kind': 'uci', 'command': 'unused'}
    assert runnable('grandmaster', 'chess19xx', engines)
    assert runnable('uci', 'chessmaster2000', engines)
    assert runnable('grandmaster', 'uci', engines)
    assert not runnable('chess19xx', 'grandmaster', engines)
    assert not runnable('uci', 'battlechess', engines)


def test_default_difficulties_have_separate_ranking_identities(tmp_path: Path) -> None:
    from emulation.difficulty import default_engines
    ledger = Ledger(tmp_path)
    assert ledger.state['engines'] == default_engines()
    for name, definition in ledger.state['engines'].items():
        assert name == (f"{definition['game']}:{definition['difficulty']}"
                        if 'difficulty' in definition else definition['game'])
    assert len(ledger.ranking(ledger.state['engines'])) == len(default_engines())


def test_unknown_historical_difficulty_is_preserved_but_retired(tmp_path: Path) -> None:
    state = {'version': 1, 'engines': {
        'grandmaster': {'kind': 'vintage', 'game': 'grandmaster', 'url': 'old'},
        'stockfish': {'kind': 'uci', 'command': 'old'}},
        'pairings': [{'white': 'grandmaster', 'black': 'stockfish', 'attempts': [
            {'status': 'completed', 'result': '1-0'}]}]}
    (tmp_path / 'state.json').write_text(json.dumps(state), encoding='utf-8')
    ledger = Ledger(tmp_path)
    assert ledger.state['pairings'][0] == state['pairings'][0]
    assert ledger.state['engines']['grandmaster']['retired']
    assert all('grandmaster' not in pair for pair in ledger.pending(ledger.state['engines']))
    assert not runnable('grandmaster', 'stockfish', ledger.state['engines'])
    rows = {row['engine']: row for row in ledger.ranking(ledger.state['engines'])}
    assert rows['grandmaster']['points'] == 1
    assert all(row['played'] == 0 for name, row in rows.items() if ':' in name)


def test_existing_profile_cannot_silently_change_its_ranking_identity(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    ledger.state['engines']['grandmaster:beginner']['difficulty'] = 'expert'
    ledger.save()
    with pytest.raises(ValueError, match='identity conflicts'):
        Ledger(tmp_path)


def test_interrupted_attempt_stays_pending(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    white, black = ledger.pending(ledger.state['engines'])[0]
    ledger.start(white, black)
    ledger.recover_interrupted()
    assert (white, black) in ledger.pending(ledger.state['engines'])
    assert ledger.state['pairings'][0]['attempts'][0]['status'] == 'failed'


def test_recovery_reconciles_run_manifest_after_a_crash(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    first, second = ledger.pending(ledger.state['engines'])[:2]
    directory = ledger.start(*first)
    ledger.state['pairings'][0]['attempts'][0]['run_id'] = 'crash-test'
    ledger.finish(directory, '1-0', None)
    ledger.start(*second)
    ledger.state['pairings'][1]['attempts'][0]['run_id'] = 'crash-test'
    path = tmp_path / 'run-crash-test.json'
    path.write_text(json.dumps({'id': 'crash-test', 'status': 'running', 'completed': 0, 'failed': 0}))
    ledger.recover_interrupted()
    report = json.loads(path.read_text())
    assert report['status'] == 'failed'
    assert report['completed'] == 1
    assert report['failed'] == 1
    assert first not in ledger.pending(ledger.state['engines'])
    assert second in ledger.pending(ledger.state['engines'])


def test_rejects_unfinished_result(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    white, black = ledger.pending(ledger.state['engines'])[0]
    with pytest.raises(ValueError, match='chess result'):
        ledger.finish(ledger.start(white, black), None, None)


def test_second_process_cannot_own_ledger(tmp_path: Path) -> None:
    with ledger_lock(tmp_path):
        with pytest.raises(RuntimeError, match='Another tournament'):
            with ledger_lock(tmp_path):
                pytest.fail('Acquired an already owned ledger')


class ScriptedUci:
    """Protocol test double; the live acceptance games use actual programs."""
    closed = 0

    def __init__(self, command: str, timeout: float, move_time: float) -> None:
        pass

    def choose(self, board: chess.Board) -> chess.Move:
        return chess.Move.from_uci(('f2f3', 'e7e5', 'g2g4', 'd8h4')[board.ply()])

    def close(self) -> None:
        ScriptedUci.closed += 1


def test_match_records_terminal_legal_game_and_closes_engines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = Ledger(tmp_path)
    white, black = ledger.pending(ledger.state['engines'])[0]
    engines = {name: {'kind': 'uci', 'command': 'test-double'} for name in (white, black)}
    monkeypatch.setattr(tournament, 'UciParticipant', ScriptedUci)
    ScriptedUci.closed = 0
    assert run_match(ledger, white, black, engines, 1, .01, 10, run_id='test')
    assert ScriptedUci.closed == 2
    assert ledger.ranking(ledger.state['engines'])[0]['engine'] == black
    attempt = ledger.state['pairings'][0]['attempts'][0]
    assert attempt['run_id'] == 'test'
    directory = tmp_path / attempt['id']
    events = [json.loads(line) for line in (directory / 'events.jsonl').read_text().splitlines()]
    assert len(events) == 4
    assert chess.Board(events[-1]['fen']).is_checkmate()


def test_ply_limit_is_failure_not_draw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = Ledger(tmp_path)
    white, black = ledger.pending(ledger.state['engines'])[0]
    engines = {name: {'kind': 'uci', 'command': 'test-double'} for name in (white, black)}
    monkeypatch.setattr(tournament, 'UciParticipant', ScriptedUci)
    assert not run_match(ledger, white, black, engines, 1, .01, 2)
    assert (white, black) in ledger.pending(ledger.state['engines'])
    assert all(row['played'] == 0 for row in ledger.ranking(ledger.state['engines']))


def test_explicit_resignation_is_a_result_without_inventing_checkmate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class ResigningUci(ScriptedUci):
        def choose(self, board: chess.Board) -> chess.Move:
            if board.turn == chess.BLACK:
                raise GameResigned(chess.BLACK)
            return super().choose(board)

    ledger = Ledger(tmp_path)
    white, black = ledger.pending(ledger.state['engines'])[0]
    engines = {name: {'kind': 'uci', 'command': 'test-double'} for name in (white, black)}
    monkeypatch.setattr(tournament, 'UciParticipant', ResigningUci)
    assert run_match(ledger, white, black, engines, 1, .01, 10)
    attempt = ledger.state['pairings'][0]['attempts'][0]
    assert attempt['result'] == '1-0'
    assert attempt['termination'] == 'resignation'
    assert not chess.Board(attempt['final_fen']).is_game_over()


def test_same_program_difficulties_use_independent_runtimes_and_record_profiles(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager
    from typing import Iterator
    from unittest.mock import Mock

    ledger = Ledger(tmp_path)
    names = ('grandmaster:beginner', 'grandmaster:grandmaster')
    definitions = {name: ledger.state['engines'][name] for name in names}
    launched: list[Path] = []
    configured: list[str | None] = []

    @contextmanager
    def runtime(game: str, directory: Path, timeout: float) -> Iterator[Mock]:
        launched.append(directory)
        client = Mock()
        client.snapshot.return_value = {'png': ''}
        yield client

    class Vintage(ScriptedUci):
        def __init__(self, game: str, client: Mock, color: chess.Color, timeout: float,
                     *, difficulty: str | None, thinking_timeout: float | None) -> None:
            configured.append(difficulty)
            assert thinking_timeout is None

        def finish(self, board: chess.Board) -> None:
            assert board.is_checkmate()

    monkeypatch.setattr(tournament, 'runtime', runtime)
    monkeypatch.setattr(tournament, 'VintageParticipant', Vintage)
    assert run_match(ledger, *names, definitions, 90, .3, 10)
    assert configured == ['beginner', 'grandmaster']
    assert len(launched) == 2 and launched[0] != launched[1]
    assert {directory.name for directory in launched} == {'white', 'black'}
    pairing = next(pair for pair in ledger.state['pairings']
                   if (pair['white'], pair['black']) == names)
    attempt = pairing['attempts'][0]
    assert attempt['engines'] == definitions
    assert (tmp_path / attempt['id'] / 'grandmaster--beginner-final.png').exists()
