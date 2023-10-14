from chess import COLORS, WHITE, BLACK, Move, Board
import chess.pgn
import pathlib

from moveFromFens import moveFromFens


def test_pawn_kickstart():
    board1 = Board()
    board2 = board1.copy()
    board2.push_san("e4")

    move = moveFromFens(board1, board2)

    assert move.uci() == "e2e4"


def test_pawn_advance():
    Board1 = Board()
    Board2 = Board1.copy()
    Board2.push_san("e3")

    move = moveFromFens(Board1, Board2)

    assert move.uci() == "e2e3"


def test_a_capture():
    board1 = Board()
    board1.push_san("e4")
    board1.push_san("d5")
    board1.push_san("Qg4")

    board2 = board1.copy()
    board2.push_san("Bxg4")

    move = moveFromFens(board1, board2)

    assert move.uci() == "c8g4"


def test_a_promotion():
    board1 = Board("8/3P4/8/6k1/8/8/1K6/8 w - - 0 1 ")
    board2 = board1.copy()
    board2.push_san("d8=Q")

    move = moveFromFens(board1, board2)

    assert move.uci() == "d7d8q"


def test_a_king_castle():
    board1 = Board()
    # 1. d4 e5 2. Bg5 Bb4+ 3. Nc3 h5 4. a4 Nf6 5. Qd3 O-O 6. O-O-O 1/2-1/2
    board1.push_san("d4")
    board1.push_san("e5")
    board1.push_san("Bg5")
    board1.push_san("Bb4+")
    board1.push_san("Nc3")
    board1.push_san("h5")
    board1.push_san("a4")
    board1.push_san("Nf6")
    board1.push_san("Qd3")

    board2 = board1.copy()
    board2.push_san("O-O")

    move = moveFromFens(board1, board2)

    assert move.uci() == "e8g8"


def test_a_queen_castle():
    board1 = Board()
    # 1. d4 e5 2. Bg5 Bb4+ 3. Nc3 h5 4. a4 Nf6 5. Qd3 O-O 6. O-O-O 1/2-1/2
    board1.push_san("d4")
    board1.push_san("e5")
    board1.push_san("Bg5")
    board1.push_san("Bb4+")
    board1.push_san("Nc3")
    board1.push_san("h5")
    board1.push_san("a4")
    board1.push_san("Nf6")
    board1.push_san("Qd3")
    board1.push_san("O-O")

    board2 = board1.copy()
    board2.push_san("O-O-O")

    move = moveFromFens(board1, board2)

    assert move.uci() == "e1a1"


def test_a_en_passant():
    board1 = Board(
        "rnbqkbnr/pp2p1pp/2p2p2/3pP3/2P5/8/PP1P1PPP/RNBQKBNR w KQkq d6 0 4")
    board2 = board1.copy()
    board2.push_san("exd6")

    move = moveFromFens(board1, board2)

    assert move.uci() == "e5d6"


castling_moves = [
    "e1g1", "e1c1", "e1a1", "e1h1",
    "e8g8", "e8c8", "e8a8", "e8h8"
]


def test_two_pawns():
    fen1 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    fen2 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1"

    board1 = Board(fen1)
    board2 = Board(fen2)

    move = moveFromFens(board1, board2)

    assert move.uci() == "e7e5"
