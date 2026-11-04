"""Stockfish advice for a confirmed position, independent of Tk and emulators.

The polling worker owns AnalysisSession. Only a copied board crosses into the
engine thread, preserving history for repetition detection. Invalidating advice
also discards in-flight results, even if a reset later produces the same FEN.
"""

from concurrent.futures import Future
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import shutil
from threading import Thread

import chess
import chess.engine


def validate_engine(executable: str) -> tuple[str, str]:
    """Resolve the binary and verify its UCI handshake without blocking Tk.

    File existence alone does not establish engine compatibility. Opening a UCI
    engine waits for initialization; ping also checks the ready response.
    """
    resolved = shutil.which(str(Path(executable.strip()).expanduser())) if executable.strip() else None
    if resolved is None:
        raise ValueError("Stockfish was not found; choose its executable")
    with chess.engine.SimpleEngine.popen_uci(resolved, timeout=5.0) as engine:
        engine.ping()
        name = engine.id.get("name", "UCI engine")
    return str(Path(resolved).resolve()), name


@dataclass(frozen=True)
class AnalysisResult:
    fen: str
    uci: str
    san: str
    evaluation: str


def analyze_position(board: chess.Board, executable: str, seconds: float) -> AnalysisResult:
    """Run one bounded UCI search; always release the engine process."""
    if not board.is_valid() or board.is_game_over():
        raise ValueError("Analysis needs a valid, unfinished game")
    if not executable.strip():
        raise ValueError("Choose a Stockfish executable or put stockfish on PATH")
    if not isfinite(seconds) or not 0.1 <= seconds <= 60:
        raise ValueError("Thinking time must be between 0.1 and 60 seconds")
    try:
        with chess.engine.SimpleEngine.popen_uci(executable, timeout=10.0) as engine:
            info = engine.analyse(board, chess.engine.Limit(time=seconds))
    except FileNotFoundError as error:
        raise ValueError("Stockfish was not found; choose its executable or add it to PATH") from error
    variation = info.get("pv", [])
    if not variation or variation[0] not in board.legal_moves:
        raise ValueError("Stockfish returned no legal best move")
    move = variation[0]
    score = info.get("score")
    evaluation = "Evaluation unavailable"
    if score is not None:
        white_score = score.white()
        mate = white_score.mate()
        centipawns = white_score.score()
        if mate is not None:
            evaluation = f"Mate {mate:+d} (White perspective)"
        elif centipawns is not None:
            evaluation = f"{centipawns / 100:+.2f} (White perspective)"
    return AnalysisResult(board.fen(), move.uci(), board.san(move), evaluation)


class AnalysisSession:
    """One background search at a time; advice belongs to one ready position."""

    def __init__(self) -> None:
        self.fen: str | None = None
        self.result: AnalysisResult | None = None
        self.message = "Wait for a confirmed turn to analyze"
        self.future: Future[AnalysisResult] | None = None
        self.generation = 0
        self.request_generation = 0
        self.play_requested = False

    def invalidate(self) -> None:
        self.play_requested = False
        self.generation += 1
        self.fen = None
        self.result = None
        self.message = "Wait for a confirmed turn to analyze"

    def synchronize(self, board: chess.Board | None) -> None:
        fen = board.fen() if board is not None else None
        if fen != self.fen:
            self.invalidate()
            self.fen = fen
            if fen is not None:
                self.message = "Ready to analyze with Stockfish"
        if self.future is not None and self.future.done():
            future, self.future = self.future, None
            if self.request_generation == self.generation and self.fen is not None:
                try:
                    self.result = future.result()
                    self.message = (f"Best move: {self.result.san} ({self.result.uci})"
                                    f" · {self.result.evaluation}")
                except Exception as error:
                    self.message = f"Analysis failed: {error}"

    def request(self, board: chess.Board, executable: str, seconds: float,
                *, play_after: bool = False) -> None:
        if self.future is not None:
            raise ValueError("Stockfish is already analyzing; wait for the search to finish")
        if board.fen() != self.fen:
            raise ValueError("The position changed; analyze the current board again")
        self.play_requested = play_after
        position = board.copy(stack=True)
        future: Future[AnalysisResult] = Future()
        self.future = future
        self.request_generation = self.generation
        self.result = None
        self.message = "Stockfish is analyzing…"

        def work() -> None:
            try:
                future.set_result(analyze_position(position, executable, seconds))
            except Exception as error:
                future.set_exception(error)

        Thread(target=work, daemon=True).start()

    def take_requested_move(self, board: chess.Board | None, ready: bool) -> str | None:
        """Consume one automatic move only for the still-confirmed player turn.

        Invalidation clears the intent as well as advice, so a reset to the
        same FEN cannot accidentally execute an earlier search result.
        """
        if not self.play_requested or self.result is None:
            return None
        if not ready or board is None or board.fen() != self.result.fen:
            return None
        self.play_requested = False
        return self.result.uci

    def state(self) -> dict[str, object]:
        return {"message": self.message, "busy": self.future is not None,
                "uci": self.result.uci if self.result else None,
                "fen": self.result.fen if self.result else None}


class AutoPlay:
    """Worker-owned continuous play policy; observations determine readiness.

    Attempt each position once to avoid repeated searches after engine errors.
    Disabling invalidates pending advice, including an in-flight search.
    """

    def __init__(self) -> None:
        self.enabled = False
        self.executable = ""
        self.seconds = 1.0
        self.attempted_fen: str | None = None

    def configure(self, enabled: bool, analysis: AnalysisSession,
                  executable: str = "", seconds: float = 1.0) -> None:
        analysis.invalidate()
        self.enabled = enabled
        self.executable = executable
        self.seconds = seconds
        self.attempted_fen = None

    def advance(self, analysis: AnalysisSession, board: chess.Board | None,
                ready: bool) -> str | None:
        if not self.enabled or board is None:
            return None
        if board.is_game_over():
            self.enabled = False
            return None
        if not ready:
            return None
        move = analysis.take_requested_move(board, ready)
        if move is not None:
            return move
        if analysis.future is None and board.fen() != self.attempted_fen:
            self.attempted_fen = board.fen()
            analysis.request(board, self.executable, self.seconds, play_after=True)
        return None
