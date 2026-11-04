"""Game definitions; import setup only, without legacy connector dependencies."""

from pathlib import Path
from .Grandmaster_Chess import setup as grandmaster
from .Chess_19xx import setup as chess19xx

GAMES = {"grandmaster": grandmaster, "chess19xx": chess19xx}


def prepare(game: str, destination: Path) -> list[str]:
    if game not in GAMES:
        raise ValueError(f"Unknown game: {game}")
    destination.mkdir(parents=True, exist_ok=True)
    return GAMES[game].prepare(destination)
