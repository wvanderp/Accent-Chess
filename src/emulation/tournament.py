"""Persistent round robin with isolated runtimes and confirmed vintage moves.

Capabilities gate scheduling. Failures never count as completed games, and
the requested count means different completed pairings in this invocation.
"""
import argparse
from datetime import datetime, timezone
from contextlib import ExitStack
import json
import shutil
import sys
from pathlib import Path
import traceback
from uuid import uuid4

import chess
import chess.engine
import chess.pgn

from .client import RuntimeClient
from .play import GameResigned, supports_color
from .participants import Participant, UciParticipant, VintageParticipant
from .settings import load_stockfish_path
from .tournament_runtime import build_image, runtime
from .tournament_lock import ledger_lock
from .difficulty import default_engines


class Ledger:
    """Single-writer permanent JSON history; replacement prevents partial writes."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'state.json'
        self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {
            'version': 1, 'engines': {}, 'pairings': []}
        if self.state['version'] != 1:
            raise ValueError('Unsupported state version')
        defaults = default_engines()
        profiled_games = {definition['game'] for definition in defaults.values() if 'difficulty' in definition}
        for name, definition in self.state['engines'].items():
            if (definition['kind'] == 'vintage' and definition['game'] in profiled_games
                    and 'difficulty' not in definition):
                # Historical games have an unknown setting. Preserve their
                # identity/results rather than relabeling them as a new level.
                definition['retired'] = 'unrecorded native difficulty'
        for name, definition in defaults.items():
            existing = self.state['engines'].get(name)
            if existing is not None and any(existing.get(field) != definition.get(field)
                                            for field in ('kind', 'game', 'difficulty')):
                raise ValueError(f'Engine identity conflicts with native difficulty profile: {name}')
            self.state['engines'].setdefault(name, definition)
        known = {(p['white'], p['black']) for p in self.state['pairings']}
        for white in self.state['engines']:
            for black in self.state['engines']:
                if any('retired' in self.state['engines'][name] for name in (white, black)):
                    continue
                if white != black and (white, black) not in known:
                    self.state['pairings'].append({'white': white, 'black': black, 'attempts': []})
        self.save()

    def save(self) -> None:
        import os
        temporary = self.path.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(self.state, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.path)

    def pending(self, engines: dict[str, dict[str, str]]) -> list[tuple[str, str]]:
        return [(p['white'], p['black']) for p in self.state['pairings']
                if all('retired' not in engines[name] for name in (p['white'], p['black']))
                if not any(a['status'] == 'completed' for a in p['attempts'])]

    def recover_interrupted(self) -> None:
        """Called only after acquiring the process lock, before starting a run."""
        for pairing in self.state['pairings']:
            for attempt in pairing['attempts']:
                if attempt['status'] == 'running':
                    attempt.update(status='failed', error='Previous runner was interrupted', result=None)
        for path in self.root.glob('run-*.json'):
            report = json.loads(path.read_text(encoding='utf-8'))
            if report.get('status') == 'running':
                attempts = [attempt for pairing in self.state['pairings'] for attempt in pairing['attempts']
                            if attempt.get('run_id') == report.get('id')]
                report.update(status='failed', error='Previous runner was interrupted',
                              completed=sum(attempt['status'] == 'completed' for attempt in attempts),
                              failed=sum(attempt['status'] == 'failed' for attempt in attempts),
                              finished=datetime.now(timezone.utc).isoformat())
                temporary = path.with_suffix('.tmp')
                temporary.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
                temporary.replace(path)
        self.save()

    def start(self, white: str, black: str) -> Path:
        directory = self.root / uuid4().hex
        directory.mkdir()
        pairing = next(p for p in self.state['pairings'] if (p['white'], p['black']) == (white, black))
        pairing['attempts'].append({'id': directory.name, 'started': datetime.now(timezone.utc).isoformat(),
                                   'status': 'running', 'result': None, 'error': None})
        self.save()
        return directory

    def finish(self, directory: Path, result: str | None, error: str | None) -> None:
        if error is None and result not in {'1-0', '0-1', '1/2-1/2'}:
            raise ValueError('A completed game must have a chess result')
        attempt = next(a for p in self.state['pairings'] for a in p['attempts'] if a['id'] == directory.name)
        attempt.update(status='failed' if error else 'completed', result=result, error=error)
        self.save()

    def ranking(self, engines: dict[str, dict[str, str]]) -> list[dict[str, object]]:
        scores = {name: {'engine': name, 'played': 0, 'points': 0.0, 'wins': 0} for name in engines}
        for name, definition in engines.items():
            if 'retired' in definition:
                scores[name]['retired'] = definition['retired']
        for pairing in self.state['pairings']:
            for attempt in pairing['attempts']:
                if attempt['status'] != 'completed':
                    continue
                points = {'1-0': 1, '0-1': 0, '1/2-1/2': .5}[attempt['result']]
                for name, score in ((pairing['white'], points), (pairing['black'], 1 - points)):
                    scores[name]['played'] += 1
                    scores[name]['points'] += score
                    scores[name]['wins'] += int(score == 1)
        return sorted(scores.values(), key=lambda e: (-e['points'], -e['wins'], e['engine']))


def runnable(white: str, black: str, engines: dict[str, dict[str, str]]) -> bool:
    def supports(name: str, color: chess.Color) -> bool:
        definition = engines[name]
        if 'retired' in definition:
            return False
        return definition['kind'] == 'uci' or (
            definition['kind'] == 'vintage' and supports_color(definition['game'], color))
    return supports(white, chess.WHITE) and supports(black, chess.BLACK)


def run_match(ledger: Ledger, white: str, black: str, engines: dict[str, dict[str, str]],
              timeout: float, move_time: float, max_plies: int, *, managed: bool = True,
              run_id: str | None = None, thinking_timeout: float | None = None) -> bool:
    directory = ledger.start(white, black)
    attempt = next(a for p in ledger.state['pairings'] for a in p['attempts'] if a['id'] == directory.name)
    attempt['run_id'] = run_id
    attempt['settings'] = {'stockfish_move_time': move_time, 'startup_timeout': timeout,
                           'thinking_timeout': thinking_timeout, 'max_plies': max_plies}
    attempt['engines'] = {name: dict(engines[name]) for name in (white, black)}
    ledger.save()
    board = chess.Board()
    participants: dict[chess.Color, Participant] = {}
    clients: dict[str, RuntimeClient] = {}
    error: str | None = None
    result: str | None = None
    termination = 'unterminated'
    try:
        with ExitStack() as stack:
            for name, color in ((white, chess.WHITE), (black, chess.BLACK)):
                definition = engines[name]
                if definition['kind'] == 'uci':
                    participant: Participant = UciParticipant(definition['command'], timeout, move_time)
                else:
                    game = definition['game']
                    runtime_directory = directory / chess.COLOR_NAMES[color]
                    runtime_directory.mkdir()
                    client = (stack.enter_context(runtime(game, runtime_directory, timeout)) if managed
                              else RuntimeClient(definition['url']))
                    if (not managed and any(other.url == client.url for other in clients.values())):
                        raise ValueError('Each participant requires an independent runtime; duplicate external URL')
                    clients[name] = client
                    participant = VintageParticipant(game, client, color, timeout,
                        difficulty=definition.get('difficulty'), thinking_timeout=thinking_timeout)
                stack.callback(participant.close)
                participants[color] = participant
            with (directory / 'events.jsonl').open('a', encoding='utf-8') as log:
                while not board.is_game_over(claim_draw=True):
                    if board.ply() >= max_plies:
                        raise RuntimeError('Ply limit reached; result remains unadjudicated')
                    try:
                        move = participants[board.turn].choose(board.copy())
                    except GameResigned as resignation:
                        if resignation.color != board.turn:
                            raise ValueError('Resignation color differs from the active participant')
                        result = '0-1' if resignation.color == chess.WHITE else '1-0'
                        termination = 'resignation'
                        log.write(json.dumps({'termination': termination, 'color': chess.COLOR_NAMES[resignation.color],
                                              'fen': board.fen()}) + '\n')
                        log.flush()
                        break
                    if move not in board.legal_moves:
                        raise ValueError(f'Participant returned illegal move {move}')
                    san = board.san(move)
                    board.push(move)
                    log.write(json.dumps({'ply': board.ply(), 'move': move.uci(), 'fen': board.fen()}) + '\n')
                    log.flush()
                    print(f'{white} vs {black}: {board.ply()} {san} ({move.uci()})', flush=True)
                    pgn = chess.pgn.Game.from_board(board)
                    pgn.headers.update(White=white, Black=black, Result='*')
                    (directory / 'game.pgn').write_text(str(pgn) + '\n', encoding='utf-8')
                if result is None:
                    for color, participant in participants.items():
                        if isinstance(participant, VintageParticipant):
                            try:
                                participant.finish(board.copy())
                            except GameResigned as resignation:
                                if resignation.color != color:
                                    raise ValueError('Resignation color differs from participant')
                                result = '0-1' if color == chess.WHITE else '1-0'
                                termination = 'resignation'
                    if result is None:
                        result = board.result(claim_draw=True)
                        outcome = board.outcome(claim_draw=True)
                        assert outcome is not None
                        termination = outcome.termination.name
                for name, client in clients.items():
                    import base64
                    # Profile IDs contain ':'; Windows filenames cannot.
                    filename = name.replace(':', '--') + '-final.png'
                    (directory / filename).write_bytes(base64.b64decode(client.snapshot()['png']))
    except BaseException as exc:
        result = None
        error = str(exc) or type(exc).__name__
        (directory / 'failure.log').write_text(traceback.format_exc(), encoding='utf-8')
        for color, participant in participants.items():
            if isinstance(participant, VintageParticipant) and participant.last_png:
                (directory / f'{chess.COLOR_NAMES[color]}-failure.png').write_bytes(participant.last_png)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        pgn = chess.pgn.Game.from_board(board)
        pgn.headers.update(Event='Accent Chess round robin', White=white, Black=black,
                           Result=result or '*', Termination=termination if result else 'unterminated')
        attempt.update(termination=termination if result else None, plies=board.ply(), final_fen=board.fen())
        (directory / 'game.pgn').write_text(str(pgn) + '\n', encoding='utf-8')
        ledger.finish(directory, result, error)
    print(f'{white} vs {black}: {result or "FAILED: " + str(error)} [{directory}]', flush=True)
    return error is None


def configure_output() -> None:
    """Docker/package logs contain Unicode even with redirected Windows stdout.

    Python otherwise selects CP1252 for a pipe, and a package's symlink arrow
    can abort an uncached image build before any match starts. StringIO/test
    streams already support Unicode and do not need reconfiguration.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is not None:
            reconfigure(encoding='utf-8', errors='backslashreplace')


def main() -> None:
    configure_output()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run', 'pending', 'ranking', 'history'])
    parser.add_argument('--data', type=Path, default=Path('tournament-data'))
    parser.add_argument('--count', type=int, default=6, help='Number of different completed pairings required')
    parser.add_argument('--timeout', type=float, default=300, help='Startup/input/menu timeout; does not limit native searches')
    parser.add_argument('--thinking-timeout', type=float, default=None,
                        help='Optional vintage search watchdog; default waits for the full native search')
    parser.add_argument('--move-time', type=float, default=0.3, help='Stockfish benchmark search budget only')
    parser.add_argument('--max-plies', type=int, default=600)
    parser.add_argument('--stockfish', help='Register Stockfish; defaults to the saved viewer executable')
    parser.add_argument('--external-runtimes', action='store_true', help='Use ledger URLs instead of starting isolated Docker runtimes')
    args = parser.parse_args()
    if args.count < 1 or args.timeout <= 0 or args.move_time <= 0 or args.max_plies < 1:
        parser.error('Counts, timeouts, move time and ply limits must be positive')
    if args.thinking_timeout is not None and args.thinking_timeout <= 0:
        parser.error('--thinking-timeout must be positive')
    with ledger_lock(args.data):
        execute(args)


def execute(args: argparse.Namespace) -> None:
    ledger = Ledger(args.data)
    if args.action == 'run':
        ledger.recover_interrupted()
        command = args.stockfish or load_stockfish_path() or shutil.which('stockfish')
        if command:
            with chess.engine.SimpleEngine.popen_uci(command, timeout=args.timeout):
                pass
            ledger.state['engines']['stockfish'] = {'kind': 'uci', 'command': command}
            ledger.save()
            ledger = Ledger(args.data)  # Extend ordered pairings after registration.
    engines = ledger.state['engines']
    if args.action == 'ranking':
        print(json.dumps(ledger.ranking(engines), indent=2))
    elif args.action == 'history':
        print(json.dumps(ledger.state['pairings'], indent=2))
    else:
        pending = ledger.pending(engines)
        supported = [(w, b) for w, b in pending if runnable(w, b, engines)]
        if args.action == 'pending':
            print(json.dumps([{'white': w, 'black': b, 'runnable': (w, b) in supported} for w, b in pending], indent=2))
            return
        if len(supported) < args.count:
            raise SystemExit(f'Requested {args.count} different matches, but only {len(supported)} pending pairings are runnable. '
                             'Use --stockfish PATH to include a UCI opponent, or inspect pending.')
        run_id = uuid4().hex
        report = {'id': run_id, 'started': datetime.now(timezone.utc).isoformat(),
                  'requested': args.count, 'completed': 0, 'failed': 0, 'status': 'running',
                  'engines': engines, 'pairings': supported}
        report_path = args.data / f'run-{run_id}.json'
        def save_report() -> None:
            temporary = report_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            temporary.replace(report_path)
        save_report()
        try:
            if not args.external_runtimes and any(engines[n]['kind'] == 'vintage' for pair in supported for n in pair):
                build_image()
            # Strong UCI opponents first give quick independent end-to-end checks;
            # every pairing is still played by its actual registered programs.
            supported.sort(key=lambda pair: (
                not any(engines[name]['kind'] == 'uci' for name in pair),
                engines[pair[0]]['kind'] != 'uci', pair))
            for white, black in supported:
                print(f'Playing {white} vs {black} ({report["completed"]}/{args.count} completed)', flush=True)
                completed = run_match(ledger, white, black, engines, args.timeout, args.move_time,
                                      args.max_plies, managed=not args.external_runtimes, run_id=run_id,
                                      thinking_timeout=args.thinking_timeout)
                report['completed' if completed else 'failed'] += 1
                save_report()
                if report['completed'] >= args.count:
                    break
            if report['completed'] < args.count:
                raise RuntimeError(f'Only {report["completed"]}/{args.count} matches completed; failed pairings remain pending')
            report['status'] = 'completed'
        except BaseException:
            report['status'] = 'failed'
            raise
        finally:
            report['finished'] = datetime.now(timezone.utc).isoformat()
            save_report()
        print(f'Completed {report["completed"]} different matches in one invocation: {report_path}', flush=True)
        print(json.dumps(ledger.ranking(engines), indent=2))


if __name__ == '__main__':
    main()
