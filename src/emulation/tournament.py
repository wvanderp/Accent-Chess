"""Persistent tournament ledger and frame-driven vintage/UCI match runner.

Vintage connectors currently expose computer-as-black only. Pairings retain
colors explicitly so adding white-side support does not invalidate history.
Failures never count as results or remove a pairing from the pending queue.
"""
import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from time import monotonic
import traceback
from uuid import uuid4

import chess
import chess.engine
import chess.pgn
from PIL import Image

from .client import RuntimeClient
from .play import PlaySession, create_connector
from recognition.runtime import RuntimeRecognizer


class Ledger:
    """Single-writer permanent JSON history; replacement prevents partial writes."""

    def __init__(self, root: Path) -> None:
        from games.catalog import GAMES
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'state.json'
        self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {
            'version': 1, 'engines': {}, 'pairings': []}
        if self.state['version'] != 1:
            raise ValueError('Unsupported state version')
        for index, game in enumerate(GAMES):
            self.state['engines'].setdefault(game, {'kind': 'vintage', 'game': game,
                'url': f'http://127.0.0.1:{8765 + index}'})
        known = {(p['white'], p['black']) for p in self.state['pairings']}
        for white in self.state['engines']:
            for black in self.state['engines']:
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
                if not any(a['status'] == 'completed' for a in p['attempts'])]

    def start(self, white: str, black: str) -> Path:
        directory = self.root / uuid4().hex
        directory.mkdir()
        pairing = next(p for p in self.state['pairings'] if (p['white'], p['black']) == (white, black))
        pairing['attempts'].append({'id': directory.name, 'started': datetime.now(timezone.utc).isoformat(),
                                   'status': 'running', 'result': None, 'error': None})
        self.save()
        return directory

    def finish(self, directory: Path, result: str | None, error: str | None) -> None:
        attempt = next(a for p in self.state['pairings'] for a in p['attempts'] if a['id'] == directory.name)
        attempt.update(status='failed' if error else 'completed', result=result, error=error)
        self.save()

    def ranking(self, engines: dict[str, dict[str, str]]) -> list[dict[str, object]]:
        scores = {name: {'engine': name, 'played': 0, 'points': 0.0, 'wins': 0} for name in engines}
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


def run_match(ledger: Ledger, white: str, black: str, engines: dict[str, dict[str, str]],
              timeout: float, move_time: float, max_plies: int) -> bool:
    directory = ledger.start(white, black)
    board = chess.Board()
    engine: chess.engine.SimpleEngine | None = None
    recognizer: RuntimeRecognizer | None = None
    error: str | None = None
    result: str | None = None
    try:
        client = RuntimeClient(engines[black]['url'])
        game = engines[black]['game']
        if client.snapshot().get('game') != game:
            raise ValueError('Runtime game does not match configured engine')
        recognizer = RuntimeRecognizer(game, client)
        session = PlaySession(create_connector(game, client))
        engine = chess.engine.SimpleEngine.popen_uci(engines[white]['command'])
        engine.timeout = timeout
        session.new_game()
        deadline = monotonic() + timeout
        with (directory / 'events.jsonl').open('a', encoding='utf-8') as log:
            while not board.is_game_over():
                if monotonic() > deadline:
                    raise TimeoutError('No confirmed move before deadline')
                snapshot = client.snapshot()
                if snapshot.get('game') != game:
                    raise ValueError('Runtime changed game during match')
                recognizer.process(snapshot)
                with Image.open(BytesIO(recognizer.last_png)) as frame:
                    session.observe(frame, recognizer.confirmed_placement)
                if session.board is None and not session.resetting:
                    raise RuntimeError(session.message)
                if session.position_confirmed and session.board is not None:
                    observed = session.board
                    if observed.board_fen() != board.board_fen():
                        if observed.move_stack[:len(board.move_stack)] != board.move_stack:
                            raise ValueError('Runtime history diverged from recorded game')
                        for move in observed.move_stack[len(board.move_stack):]:
                            board.push(move)
                            log.write(json.dumps({'ply': board.ply(), 'move': move.uci(), 'fen': board.fen()}) + '\n')
                            log.flush()
                        deadline = monotonic() + timeout
                    if board.is_game_over():
                        break
                    if board.ply() >= max_plies:
                        raise RuntimeError('Ply limit reached; result remains unadjudicated')
                    if session.ready and board.turn == chess.WHITE:
                        choice = engine.play(board, chess.engine.Limit(time=move_time))
                        if choice.move is None:
                            raise RuntimeError('UCI engine returned no move')
                        session.submit(choice.move.uci())
            result = board.result()
    except BaseException as exc:
        error = str(exc) or type(exc).__name__
        (directory / 'failure.log').write_text(traceback.format_exc(), encoding='utf-8')
        if recognizer and recognizer.last_png:
            (directory / 'failure.png').write_bytes(recognizer.last_png)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        pgn = chess.pgn.Game.from_board(board)
        pgn.headers.update(White=white, Black=black, Result=result or '*')
        (directory / 'game.pgn').write_text(str(pgn) + '\n', encoding='utf-8')
        ledger.finish(directory, result, error)
        if engine:
            engine.close()
    return error is None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run', 'pending', 'ranking', 'history'])
    parser.add_argument('--data', type=Path, default=Path('tournament-data'))
    parser.add_argument('--count', type=int, default=1)
    parser.add_argument('--timeout', type=float, default=240)
    parser.add_argument('--move-time', type=float, default=1)
    parser.add_argument('--max-plies', type=int, default=600)
    args = parser.parse_args()
    ledger = Ledger(args.data)
    engines = ledger.state['engines']
    try:
        if args.action == 'ranking':
            print(json.dumps(ledger.ranking(engines), indent=2))
        elif args.action == 'history':
            print(json.dumps(ledger.state['pairings'], indent=2))
        else:
            pending = ledger.pending(engines)
            supported = [(w, b) for w, b in pending if engines[w]['kind'] == 'uci' and engines[b]['kind'] == 'vintage']
            if args.action == 'pending':
                print(json.dumps([{'white': w, 'black': b, 'runnable': (w, b) in supported} for w, b in pending], indent=2))
            else:
                for white, black in supported[:args.count]:
                    print(f'Playing {white} vs {black}', flush=True)
                    if not run_match(ledger, white, black, engines, args.timeout, args.move_time, args.max_plies):
                        raise SystemExit('Match failed; see tournament-data artifacts')
                if not supported:
                    print('No supported unplayed pairings remain.')
    finally:
        pass


if __name__ == '__main__':
    main()
