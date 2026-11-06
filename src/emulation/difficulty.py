"""Verified, game-owned difficulty profiles and the headless settings command.

Profile IDs describe native settings, not elapsed thinking time measured by the
host. A setter must read back its selection before returning. The tournament
shares this command's registry so a ranking name cannot silently select a
different difficulty from the standalone script.
"""

import argparse
from dataclasses import dataclass
from importlib import import_module
import json
from types import ModuleType

from .client import RuntimeClient


MODULES = {
    'grandmaster': 'games.Grandmaster_Chess.difficulty',
    'chess19xx': 'games.Chess_19xx.difficulty',
    'chessmaster2000': 'games.Chessmaster_2000.difficulty',
    'battlechess': 'games.Battle_Chess.difficulty',
}


@dataclass(frozen=True)
class Difficulty:
    game: str
    id: str
    label: str

    @property
    def engine_id(self) -> str:
        return f'{self.game}:{self.id}'


def game_module(game: str) -> ModuleType:
    if game not in MODULES:
        raise ValueError(f'No difficulty controls for {game}')
    return import_module(MODULES[game])


def profiles(game: str) -> tuple[Difficulty, ...]:
    return tuple(Difficulty(game, identifier, label)
                 for identifier, label in game_module(game).PROFILES)


def default_engines() -> dict[str, dict[str, str]]:
    """One stable ranking identity per verified native difficulty."""
    from games.catalog import GAMES
    engines: dict[str, dict[str, str]] = {}
    for index, game in enumerate(GAMES):
        address = f'http://127.0.0.1:{8765 + index}'
        native_profiles = profiles(game)
        if not native_profiles:
            # A program with only a custom time input has no difficulty
            # variants, but remains a catalog/ranking participant.
            engines[game] = {'kind': 'vintage', 'game': game, 'url': address,
                             'label': 'Default (no verified difficulty presets)'}
        for profile in native_profiles:
            engines[profile.engine_id] = {
                'kind': 'vintage', 'game': game, 'difficulty': profile.id,
                'label': profile.label, 'url': address,
            }
    return engines


def set_difficulty(game: str, profile: str, client: RuntimeClient, timeout: float = 90) -> None:
    """Reject unknown identities and wrong runtimes before sending any input."""
    if not any(item.id == profile for item in profiles(game)):
        raise ValueError(f'Unknown difficulty for {game}: {profile}')
    snapshot = client.snapshot()
    if snapshot.get('game') != game:
        raise ValueError(f'Expected runtime {game}, got {snapshot.get("game")}')
    game_module(game).set_difficulty(client, profile, timeout=timeout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('list', 'set'))
    parser.add_argument('--game', choices=tuple(MODULES))
    parser.add_argument('--profile')
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--timeout', type=float, default=90, help='Menu navigation deadline, not engine thinking time')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    if args.action == 'list':
        games = (args.game,) if args.game else tuple(MODULES)
        print(json.dumps([{'engine': p.engine_id, 'game': p.game, 'profile': p.id, 'label': p.label}
                          for game in games for p in profiles(game)], indent=2))
        return
    if args.game is None or args.profile is None:
        parser.error('set requires --game and --profile')
    try:
        set_difficulty(args.game, args.profile, RuntimeClient(args.url), timeout=args.timeout)
    except (ValueError, TimeoutError, OSError) as error:
        parser.exit(1, f'Difficulty setup failed: {error}\n')
    print(f'Verified {args.game}:{args.profile}')


if __name__ == '__main__':
    main()
