"""Frame-driven play session, independent of Tk and Docker.

Pixels supply placement only. A confirmed reset establishes chess metadata;
subsequent unique legal successors preserve turn, castling and en-passant.
Sending input never counts as acknowledgement. Even a very fast reply must
match the submitted move followed by exactly one legal engine move.
"""

from importlib import import_module
from time import monotonic
from typing import Protocol

import chess
from PIL import Image

from .client import RuntimeClient


class GameResigned(Exception):
    """A verified game UI explicitly reports the computer's resignation."""

    def __init__(self, color: chess.Color) -> None:
        self.color = color
        super().__init__(f'{chess.COLOR_NAMES[color]} resigned')


class PlayConnector(Protocol):
    human_color: chess.Color

    def reset(self) -> None: ...
    def advance_reset(self, frame: Image.Image, placement: str | None) -> bool: ...
    def move(self, move: chess.Move) -> None: ...
    def advance(self, frame: Image.Image) -> None: ...


PLAY_MODULES = {"grandmaster": "games.Grandmaster_Chess.play",
                "chess19xx": "games.Chess_19xx.play",
                "chessmaster2000": "games.Chessmaster_2000.play"}


def supports_play(game: str) -> bool:
    return game in PLAY_MODULES


def supports_color(game: str, color: chess.Color) -> bool:
    if not supports_play(game):
        return False
    connector = import_module(PLAY_MODULES[game]).Connector
    return color in getattr(connector, "computer_colors", (chess.BLACK,))


def create_connector(game: str, client: RuntimeClient) -> PlayConnector:
    if not supports_play(game):
        raise ValueError(f"Playing {game} is not supported yet.")
    return import_module(PLAY_MODULES[game]).Connector(client)


def successors(board: chess.Board, placement: str) -> list[chess.Board]:
    matches: list[chess.Board] = []
    for move in board.legal_moves:
        candidate = board.copy()
        candidate.push(move)
        if candidate.board_fen() == placement:
            matches.append(candidate)
    return matches


class PlaySession:
    """Owned by a single polling worker; UI submits commands through its queue."""

    def __init__(self, connector: PlayConnector) -> None:
        self.connector = connector
        self.board: chess.Board | None = None
        self.pending: chess.Board | None = None
        self.resetting = False
        self.deadline = 0.0
        self.ready = False
        self.position_confirmed = False
        self.message = "Waiting for a confirmed board and an active clock"
        self.clock_samples: tuple[bytes, bytes] | None = None
        self.attach_placement: str | None = None
        self.resigned: chess.Color | None = None

    def invalidate(self, reason: str) -> None:
        self.position_confirmed = False
        self.clock_samples = None
        self.attach_placement = None
        self.board = None
        self.pending = None
        self.resetting = False
        self.ready = False
        self.deadline = 0.0
        self.message = reason
        self.resigned = None

    def new_game(self) -> None:
        self.invalidate("Resetting emulator; waiting for the starting board")
        self.resetting = True
        self.deadline = monotonic() + getattr(self.connector, "reset_timeout", 90)
        try:
            self.connector.reset()
        except Exception:
            self.invalidate("Reset input failed; rebuild/start the runtime and try New game again")
            raise

    def submit(self, uci: str) -> None:
        if not self.ready or self.board is None:
            raise ValueError("Wait for your turn and a confirmed emulator board")
        move = chess.Move.from_uci(uci)
        if move not in self.board.legal_moves:
            raise ValueError(f"Illegal move: {uci}")
        self.ready = False
        self.position_confirmed = False
        self.pending = self.board.copy()
        self.pending.push(move)
        self.deadline = monotonic() + getattr(self.connector, "move_timeout", 20)
        self.message = f"Sent {uci}; waiting for emulator acknowledgement"
        try:
            # Optional position context lets a connector distinguish a terminal
            # human move (no engine reply expected) from a normal reply wait.
            if set_position := getattr(self.connector, "set_position", None):
                set_position(self.board.copy())
            self.connector.move(move)
        except Exception:
            self.invalidate("Move input failed; press New game to resynchronize")
            raise

    def observe(self, frame: Image.Image, placement: str | None) -> None:
        self.ready = False
        self.position_confirmed = False
        if self.resigned is not None:
            return
        if self.deadline and monotonic() > self.deadline:
            self.invalidate("Emulator timed out; press New game to resynchronize")
            return
        if self.resetting:
            try:
                complete = self.connector.advance_reset(frame, placement)
            except ValueError as error:
                self.invalidate(str(error))
                return
            if complete:
                self.board = chess.Board()
                self.resetting = False
                self.deadline = 0.0
            else:
                return
        if self.board is None:
            reader = getattr(self.connector, "clock_samples", None)
            if placement is None or reader is None:
                self.clock_samples = None
                self.attach_placement = None
                return
            samples = reader(frame)
            previous = self.clock_samples
            self.clock_samples = samples
            if self.attach_placement != placement:
                self.attach_placement = placement
                return
            if previous is None:
                return
            changed = [samples[index] != previous[index] for index in range(2)]
            if sum(changed) != 1:
                return
            # Clock crops are ordered white, black. Never infer a turn from
            # placement alone: most placements permit either side to move.
            turn = chess.WHITE if changed[0] else chess.BLACK
            candidate = chess.Board(f"{placement} {'w' if turn else 'b'} - - 0 1")
            if not candidate.is_valid():
                return
            self.board = candidate
            self.message = "Attached using active clock; historical special-move rights unknown"
        try:
            self.connector.advance(frame)
        except GameResigned as resignation:
            self.resigned = resignation.color
            self.deadline = 0.0
            result = '0-1' if resignation.color == chess.WHITE else '1-0'
            self.message = f'Game over: {result} ({chess.COLOR_NAMES[resignation.color]} resigned)'
            return
        if placement is None:
            return
        if self.pending is not None:
            # The human move may appear only briefly, between captures.
            replies = successors(self.pending, placement)
            if placement == self.pending.board_fen():
                self.board = self.pending
            elif len(replies) == 1:
                self.board = replies[0]
            else:
                return
            self.pending = None
            self.deadline = monotonic() + 180 if self.board.turn != self.connector.human_color else 0.0
        elif placement != self.board.board_fen():
            matches = successors(self.board, placement)
            if self.board.turn == self.connector.human_color or len(matches) != 1:
                self.message = "Board differs from tracked game; waiting for a legal position"
                if not self.deadline:
                    self.deadline = monotonic() + 20
                return
            self.board = matches[0]
            self.deadline = 0.0
        self.position_confirmed = True
        if self.board.is_game_over():
            self.deadline = 0.0
            self.message = f"Game over: {self.board.result()}"
        elif self.board.turn == self.connector.human_color:
            self.deadline = 0.0
            self.ready = True
            self.message = f"{chess.COLOR_NAMES[self.board.turn].capitalize()} to move · your turn"
        else:
            self.message = f"{chess.COLOR_NAMES[self.board.turn].capitalize()} to move · waiting for the engine"

    def state(self) -> dict[str, object]:
        return {"fen": self.board.fen() if self.board else None,
                "ready": self.ready, "message": self.message,
                "analyzable": self.position_confirmed,
                "turn": chess.COLOR_NAMES[self.board.turn] if self.board and self.position_confirmed else None,
                "resetting": self.resetting}
