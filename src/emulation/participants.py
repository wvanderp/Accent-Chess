"""Tournament participants: authoritative move histories over UCI or live frames.

Every adapter accepts the complete tournament history. Vintage programs retain
their own state: only the opponent's next move is submitted, never an invented
position. Grandmaster's Switch Sides rotates square locations, not sprites.
"""
from io import BytesIO
from time import monotonic
from threading import Event
from typing import Protocol
import base64

import chess
import chess.engine
from PIL import Image

from .client import RuntimeClient
from .play import GameResigned, PlaySession, create_connector, supports_color
from recognition.runtime import create_reader


class Participant(Protocol):
    def choose(self, board: chess.Board) -> chess.Move: ...
    def close(self) -> None: ...


class UciParticipant:
    def __init__(self, command: str, timeout: float, move_time: float) -> None:
        self.engine = chess.engine.SimpleEngine.popen_uci(command, timeout=timeout)
        self.move_time = move_time

    def choose(self, board: chess.Board) -> chess.Move:
        choice = self.engine.play(board, chess.engine.Limit(time=self.move_time))
        if choice.move is None:
            raise RuntimeError('UCI engine returned no move')
        return choice.move

    def close(self) -> None:
        self.engine.close()


class VintageParticipant:
    def __init__(self, game: str, client: RuntimeClient, color: chess.Color, timeout: float) -> None:
        if not supports_color(game, color):
            raise ValueError(f'{game} has no verified computer-as-white control')
        self.client = client
        self.game = game
        self.timeout = timeout
        self.reader = create_reader(game)
        self.session = PlaySession(create_connector(game, client))
        self.flipped = False
        self.previous: str | None = None
        self.last_png = b''
        self.last_error: str | None = None
        self.poll = Event()
        if getattr(self.session.connector, 'requires_board_before_reset', False):
            # The HTTP display exists before GTK creates its keyboard window.
            # Wait for a real board before F1, not an elapsed boot delay.
            from recognition.board import RecognitionError
            end = monotonic() + timeout
            while True:
                self.poll.wait(0.05)
                self.last_png = base64.b64decode(client.snapshot()['png'])
                try:
                    with Image.open(BytesIO(self.last_png)) as frame:
                        self.reader.read(frame)
                    break
                except RecognitionError:
                    if monotonic() >= end:
                        raise TimeoutError(f'{game} did not reach its board')
        self.session.new_game()
        end = monotonic() + max(timeout, getattr(self.session.connector, 'reset_timeout', 90))
        while not self.session.ready:
            self.observe()
            if monotonic() >= end:
                raise TimeoutError(f'{game}: reset: {self.session.message}; {self.last_error}')
        if play_as := getattr(self.session.connector, 'play_as', None):
            play_as(color)
            self.flipped = getattr(self.session.connector, 'flipped', False)
            self.previous = None
            self.session.ready = False

    def observe(self) -> None:
        # Capture pacing only. Completion always requires a legal UI observation.
        self.poll.wait(0.05)
        snapshot = self.client.snapshot()
        if snapshot.get('game') != self.game:
            raise ValueError(f'Expected runtime {self.game}, got {snapshot.get("game")}')
        self.last_png = base64.b64decode(snapshot['png'], validate=True)
        placement: str | None = None
        from recognition.board import RecognitionError
        with Image.open(BytesIO(self.last_png)) as frame:
            try:
                placement = self.reader.read(frame, flipped=self.flipped).placement
                self.last_error = None
            except RecognitionError as error:
                self.last_error = str(error)
            confirmed = placement if placement is not None and placement == self.previous else None
            self.previous = placement
            before = getattr(self.session.connector, 'stage', None)
            self.session.observe(frame, confirmed)
            if self.session.resigned is not None:
                raise GameResigned(self.session.resigned)
            after = getattr(self.session.connector, 'stage', None)
            if before != after:
                print(f'{self.game}: {before} -> {after}', flush=True)
        if self.session.board is None and not self.session.resetting:
            diagnostics = getattr(self.session.connector, 'diagnostics', lambda: '')()
            raise RuntimeError(f'{self.game}: {self.session.message}; {self.last_error}; {diagnostics}')

    def submit_opponent(self, board: chess.Board, end: float) -> None:
        """Deliver at most one opponent move, preserving the complete history."""
        current = self.session.board
        assert current is not None
        # The other participant has made at most one move since our last search.
        if len(board.move_stack) == len(current.move_stack) + 1:
            if current.move_stack != board.move_stack[:-1]:
                raise ValueError('Vintage history diverged from tournament')
            while not self.session.ready:
                self.observe()
                if monotonic() >= end:
                    raise TimeoutError(f'{self.game}: opponent input readiness')
            if input_ready := getattr(self.session.connector, 'input_ready', None):
                while monotonic() < end:
                    self.observe()
                    with Image.open(BytesIO(self.last_png)) as frame:
                        if self.session.ready and input_ready(frame, current):
                            break
                else:
                    raise TimeoutError(f'{self.game}: input readiness was not acknowledged')
            self.session.submit(board.peek().uci())
        elif current.move_stack != board.move_stack:
            raise ValueError('Vintage history diverged from tournament')

    def choose(self, board: chess.Board) -> chess.Move:
        end = monotonic() + self.timeout
        self.submit_opponent(board, end)
        while monotonic() < end:
            self.observe()
            current = self.session.board
            assert current is not None
            if self.session.position_confirmed and len(current.move_stack) == len(board.move_stack) + 1:
                if current.move_stack[:-1] != board.move_stack:
                    raise ValueError('Vintage reply history diverged from tournament')
                return current.peek()
        raise TimeoutError(f'{self.game}: no confirmed reply: {self.session.message}; {self.last_error}')

    def finish(self, board: chess.Board) -> None:
        """The losing emulator must receive and acknowledge the final move too."""
        end = monotonic() + self.timeout
        self.submit_opponent(board, end)
        while monotonic() < end:
            self.observe()
            if (self.session.position_confirmed and self.session.board is not None
                    and self.session.board.move_stack == board.move_stack):
                return
        raise TimeoutError(f'{self.game}: final position not acknowledged')

    def close(self) -> None:
        """The runtime owner closes the emulator, including on adapter failure."""
