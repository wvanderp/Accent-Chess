"""Audit the three remaining supported pairings across retained run attempts."""
from pathlib import Path
from hashlib import sha256
import json
import shutil

import chess
import chess.pgn
from PIL import Image

from games.Grandmaster_Chess.play import Connector
from emulation.client import RuntimeClient
from recognition.runtime import create_reader


def main() -> None:
    root = Path('tournament-data/acceptance')
    manifests = [json.loads(path.read_text(encoding='utf-8')) for path in root.glob('run-*.json')]
    reports = {report['id']: report for report in manifests}
    wanted = {('chessmaster2000', 'grandmaster'), ('grandmaster', 'chess19xx'),
              ('grandmaster', 'chessmaster2000')}
    state = json.loads((root / 'state.json').read_text(encoding='utf-8'))
    verified: list[dict[str, object]] = []
    pairs: set[tuple[str, str]] = set()
    destination = Path('docs/evidence/tournament-2026-11-05/remaining')
    destination.mkdir(exist_ok=True, parents=True)
    for pairing in state['pairings']:
        for attempt in pairing['attempts']:
            if attempt['status'] != 'completed' or (pairing['white'], pairing['black']) not in wanted:
                continue
            pair = pairing['white'], pairing['black']
            assert pair not in pairs
            pairs.add(pair)
            directory = root / attempt['id']
            events = [json.loads(line) for line in (directory / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
            moves = [event for event in events if 'move' in event]
            board = chess.Board()
            for event in moves:
                move = chess.Move.from_uci(event['move'])
                assert move in board.legal_moves
                board.push(move)
                assert event['ply'] == board.ply()
                assert event['fen'] == board.fen()
            with (directory / 'game.pgn').open(encoding='utf-8') as stream:
                game = chess.pgn.read_game(stream)
            assert game is not None and not game.errors
            assert list(game.mainline_moves()) == board.move_stack
            assert game.headers['Result'] == attempt['result']
            assert game.headers['Termination'] == attempt['termination']
            assert attempt['final_fen'] == board.fen()
            if attempt['termination'] == 'resignation':
                assert 'grandmaster' in pair
                expected_result = '0-1' if pair[0] == 'grandmaster' else '1-0'
                assert attempt['result'] == expected_result
                connector = Connector(RuntimeClient())
                with Image.open(directory / 'grandmaster-final.png') as frame:
                    assert connector.matches(frame, 'resignation', (225, 197, 414, 281))
            else:
                assert board.is_game_over(claim_draw=True)
                assert board.result(claim_draw=True) == attempt['result']
                for name in pair:
                    definition = state['engines'][name]
                    if definition['kind'] == 'vintage':
                        reader = create_reader(definition['game'])
                        flipped = definition['game'] == 'grandmaster' and name == pair[0]
                        with Image.open(directory / f'{name}-final.png') as frame:
                            assert reader.read(frame, flipped=flipped).placement == board.board_fen()
            prefix = '-vs-'.join(pair)
            shutil.copyfile(directory / 'game.pgn', destination / f'{prefix}.pgn')
            shutil.copyfile(directory / 'events.jsonl', destination / f'{prefix}.jsonl')
            frames: list[str] = []
            for frame in directory.glob('*-final.png'):
                name = f'{prefix}-{frame.name}'
                shutil.copyfile(frame, destination / name)
                frames.append(name)
            verified.append({'white': pair[0], 'black': pair[1], 'attempt': attempt['id'], 'run_id': attempt['run_id'],
                             'result': attempt['result'], 'termination': attempt['termination'],
                             'plies': board.ply(), 'pgn': f'{prefix}.pgn',
                             'pgn_sha256': sha256((directory / 'game.pgn').read_bytes()).hexdigest(),
                             'final_frames': frames})
    assert pairs == wanted and len(verified) == 3
    run_ids = sorted({str(match['run_id']) for match in verified})
    summary = {'completed': len(verified), 'run_ids': run_ids,
               'execution': 'Completed matches retained across batches and connector fixes; source run manifests record failures, which are unscored.',
               'verification': 'Legal move replay, event FENs, PGN results, terminal boards or explicit resignation dialogs',
               'matches': verified}
    (destination / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    for run_id in run_ids:
        assert reports[run_id]['finished'] is not None
        shutil.copyfile(root / f'run-{run_id}.json', destination / f'run-{run_id}.json')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
