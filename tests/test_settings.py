"""Preferences survive restarts, malformed files, and failed replacement."""

from pathlib import Path
from unittest.mock import patch

import pytest

from emulation.settings import load_stockfish_path, save_stockfish_path


def test_saved_location_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "preferences" / "settings.json"
    with patch("emulation.settings.settings_path", return_value=target):
        assert load_stockfish_path() is None
        save_stockfish_path("C:/Chess Engines/Stockfish/stockfish.exe")
        assert load_stockfish_path() == "C:/Chess Engines/Stockfish/stockfish.exe"


@pytest.mark.parametrize("contents", ["{broken", "[]", '{"stockfish": 123}', '{"stockfish": ""}'])
def test_invalid_settings_fall_back(tmp_path: Path, contents: str) -> None:
    target = tmp_path / "settings.json"
    target.write_text(contents, encoding="utf-8")
    with patch("emulation.settings.settings_path", return_value=target):
        assert load_stockfish_path() is None


def test_failed_save_preserves_previous_location(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    with patch("emulation.settings.settings_path", return_value=target):
        save_stockfish_path("old-engine")
        with patch.object(Path, "replace", side_effect=PermissionError("File locked")):
            with pytest.raises(PermissionError):
                save_stockfish_path("new-engine")
        assert load_stockfish_path() == "old-engine"
    assert list(tmp_path.iterdir()) == [target]
