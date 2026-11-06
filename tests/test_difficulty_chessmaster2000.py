"""Failure-closed difficulty readback on real native C64 menu captures."""

import base64
from pathlib import Path
from typing import Any

from PIL import Image
import pytest

from games.Chessmaster_2000.difficulty import PROFILES, read_level, set_difficulty


EVIDENCE = Path(__file__).resolve().parents[1] / 'docs/difficulty/evidence/chessmaster2000'


class FrozenClient:
    def __init__(self, game: str = 'chessmaster2000') -> None:
        self.game = game
        self.keys: list[str] = []

    def snapshot(self) -> dict[str, Any]:
        return {'game': self.game, 'png': base64.b64encode((EVIDENCE / 'level-00.png').read_bytes()).decode()}

    def send(self, action: str, data: dict[str, Any]) -> None:
        assert action == 'key'
        self.keys.append(data['name'])


@pytest.mark.parametrize('level', [0, 9, 18])
def test_native_level_readback(level: int) -> None:
    with Image.open(EVIDENCE / f'level-{level:02}.png') as frame:
        assert read_level(frame) == level


def test_unknown_digits_are_not_a_level() -> None:
    assert read_level(Image.new('RGB', (640, 480), 'white')) is None


def test_analysis_level_is_rejected_before_input() -> None:
    client = FrozenClient()
    assert len(PROFILES) == 38
    with pytest.raises(ValueError, match='Unknown'):
        set_difficulty(client, 'level-19')  # type: ignore[arg-type]
    assert client.keys == []


def test_wrong_runtime_is_rejected_before_input() -> None:
    client = FrozenClient('grandmaster')
    with pytest.raises(ValueError, match='Expected runtime'):
        set_difficulty(client, 'level-09')  # type: ignore[arg-type]
    assert client.keys == []


def test_missed_level_command_cannot_report_success() -> None:
    client = FrozenClient()
    with pytest.raises(TimeoutError, match='level input selection'):
        set_difficulty(client, 'level-09', timeout=0.15)  # type: ignore[arg-type]
    assert client.keys == ['ctrl+d']


def test_missed_coffeehouse_toggle_cannot_report_success() -> None:
    client = FrozenClient()
    with pytest.raises(TimeoutError, match='Coffeehouse ON'):
        set_difficulty(client, 'coffeehouse-level-00', timeout=0.15)  # type: ignore[arg-type]
    assert client.keys == ['ctrl+c']
