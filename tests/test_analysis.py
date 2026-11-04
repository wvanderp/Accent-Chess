"""Advice must preserve chess history and never survive a changed session."""

from unittest.mock import MagicMock, patch

import chess
import chess.engine
import pytest

from emulation.analysis import AnalysisResult, AnalysisSession, analyze_position, validate_engine


def test_engine_validation_checks_uci_ready_and_closes() -> None:
    with patch("emulation.analysis.shutil.which", return_value="C:/engines/stockfish.exe"), \
            patch("emulation.analysis.chess.engine.SimpleEngine.popen_uci") as launch:
        engine = launch.return_value.__enter__.return_value
        engine.id = {"name": "Stockfish test"}
        path, name = validate_engine("stockfish")
        assert path.endswith("stockfish.exe")
        assert name == "Stockfish test"
        engine.ping.assert_called_once()
        launch.return_value.__exit__.assert_called_once()


def test_engine_validation_rejects_missing_binary() -> None:
    with patch("emulation.analysis.shutil.which", return_value=None), \
            patch("emulation.analysis.chess.engine.SimpleEngine.popen_uci") as launch:
        with pytest.raises(ValueError, match="not found"):
            validate_engine("missing-engine")
        launch.assert_not_called()


def test_engine_validation_rejects_failed_handshake() -> None:
    with patch("emulation.analysis.shutil.which", return_value="stockfish"), \
            patch("emulation.analysis.chess.engine.SimpleEngine.popen_uci") as launch:
        launch.return_value.__enter__.return_value.ping.side_effect = RuntimeError("not ready")
        with pytest.raises(RuntimeError, match="not ready"):
            validate_engine("stockfish")
        launch.return_value.__exit__.assert_called_once()


def test_uci_analysis_and_cleanup() -> None:
    board = chess.Board()
    board.push_uci("e2e4")
    engine = MagicMock()
    engine.analyse.return_value = {
        "pv": [chess.Move.from_uci("e7e5")],
        "score": chess.engine.PovScore(chess.engine.Cp(32), chess.BLACK),
    }
    with patch("emulation.analysis.chess.engine.SimpleEngine.popen_uci") as launch:
        launch.return_value.__enter__.return_value = engine
        result = analyze_position(board, "my-stockfish", 1.5)
    assert result.uci == "e7e5" and result.san == "e5"
    assert result.fen == board.fen()
    assert result.evaluation == "-0.32 (White perspective)"
    assert engine.analyse.call_args.args[0].move_stack == board.move_stack
    assert engine.analyse.call_args.args[1].time == 1.5
    launch.return_value.__exit__.assert_called_once()


def test_engine_failure_still_closes_process() -> None:
    with patch("emulation.analysis.chess.engine.SimpleEngine.popen_uci") as launch:
        launch.return_value.__enter__.return_value.analyse.side_effect = RuntimeError("engine failed")
        with pytest.raises(RuntimeError, match="engine failed"):
            analyze_position(chess.Board(), "stockfish", 1.0)
    launch.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("seconds", [0, -1, 61, float("nan"), float("inf")])
def test_invalid_limits_do_not_start_engine(seconds: float) -> None:
    with patch("emulation.analysis.chess.engine.SimpleEngine.popen_uci") as launch:
        with pytest.raises(ValueError, match="Thinking time"):
            analyze_position(chess.Board(), "stockfish", seconds)
    launch.assert_not_called()


def test_missing_executable_has_actionable_error() -> None:
    with patch("emulation.analysis.chess.engine.SimpleEngine.popen_uci", side_effect=FileNotFoundError):
        with pytest.raises(ValueError, match="choose its executable"):
            analyze_position(chess.Board(), "missing", 1.0)


def test_background_result_and_reset_discard() -> None:
    board = chess.Board()
    session = AnalysisSession()
    session.synchronize(board)
    with patch("emulation.analysis.Thread"):
        session.request(board, "stockfish", 1)
    assert session.state()["busy"]
    with pytest.raises(ValueError, match="already analyzing"):
        session.request(board, "stockfish", 1)
    result = AnalysisResult(board.fen(), "e2e4", "e4", "+0.20")
    assert session.future is not None
    session.future.set_result(result)
    session.synchronize(board)
    assert session.state()["uci"] == "e2e4"
    with patch("emulation.analysis.Thread"):
        session.request(board, "stockfish", 1)
    session.invalidate()
    session.synchronize(board)  # Same FEN, different game/reset.
    assert session.future is not None
    session.future.set_result(result)
    session.synchronize(board)
    assert not session.state()["busy"]
    assert session.state()["uci"] is None


def test_unconfirmed_board_discards_advice_and_errors_allow_retry() -> None:
    board = chess.Board()
    session = AnalysisSession()
    session.synchronize(board)
    with patch("emulation.analysis.Thread"):
        session.request(board, "stockfish", 1)
    assert session.future is not None
    session.future.set_exception(ValueError("bad engine"))
    session.synchronize(board)
    assert "bad engine" in str(session.state()["message"])
    with patch("emulation.analysis.Thread"):
        session.request(board, "stockfish", 1)
    assert session.future is not None
    session.future.set_result(AnalysisResult(board.fen(), "e2e4", "e4", "+0.20"))
    session.synchronize(board)
    session.synchronize(None)
    assert session.state()["uci"] is None


def test_worker_receives_independent_board_with_history() -> None:
    board = chess.Board()
    board.push_uci("e2e4")
    session = AnalysisSession()
    session.synchronize(board)
    with patch("emulation.analysis.Thread") as thread, patch("emulation.analysis.analyze_position") as analyze:
        session.request(board, "stockfish", 1)
        board.push_uci("e7e5")
        thread.call_args.kwargs["target"]()
    copied = analyze.call_args.args[0]
    assert len(copied.move_stack) == 1
    assert copied.turn == chess.BLACK


def test_autoplay_continues_and_can_cancel_pending_advice() -> None:
    from emulation.analysis import AutoPlay

    analysis = AnalysisSession()
    autoplay = AutoPlay()
    board = chess.Board()
    analysis.synchronize(board)
    autoplay.configure(True, analysis, "stockfish", 0.1)
    analysis.synchronize(board)
    with patch.object(analysis, "request") as request:
        assert autoplay.advance(analysis, board, False) is None
        request.assert_not_called()
        autoplay.advance(analysis, board, True)
        request.assert_called_once()
    analysis.play_requested = True
    analysis.result = AnalysisResult(board.fen(), "e2e4", "e4", "0")
    assert autoplay.advance(analysis, board, True) == "e2e4"
    board.push_uci("e2e4")
    board.push_uci("e7e5")
    analysis.synchronize(board)
    with patch.object(analysis, "request") as request:
        autoplay.advance(analysis, board, True)
        request.assert_called_once()
    autoplay.configure(False, analysis)
    assert not analysis.play_requested
    with patch.object(analysis, "request") as request:
        autoplay.advance(analysis, board, True)
        request.assert_not_called()
