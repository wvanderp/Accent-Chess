#!/usr/bin/env python3
"""
Play a game between Stockfish and a vintage chess game connector.

This script orchestrates a game where Stockfish plays against the
vintage chess game running in an emulator. The connector reads the
board state from the emulator and executes moves.
"""

import argparse
import logging
import sys
import time
from typing import Optional

import chess
import chess.engine

from games.Grandmaster_Chess.Grandmaster_Chess import GrandmasterChessConnector


def _piece_placement_fen(board: chess.Board) -> str:
    """Return only the piece-placement part of a FEN string."""
    return board.fen().split()[0]


def wait_for_board_to_match(
    connector: GrandmasterChessConnector,
    expected_board: chess.Board,
    *,
    timeout: float = 10.0,
    poll_interval: float = 0.25,
    stable_samples: int = 2,
) -> bool:
    """Wait until the on-screen board matches the expected piece placement.

    This avoids fixed sleeps and instead polls the emulator UI via
    `connector.get_board_state()`.

    Returns:
        True if the expected position was observed within timeout.
    """
    expected = _piece_placement_fen(expected_board)
    start = time.time()
    stable = 0

    while time.time() - start < timeout:
        try:
            current = connector.get_board_state()
        except Exception as e:
            logging.debug(f"Failed reading board state while waiting: {e}")
            time.sleep(poll_interval)
            continue

        current_placement = _piece_placement_fen(current)
        if current_placement == expected:
            stable += 1
            if stable >= stable_samples:
                return True
        else:
            stable = 0

        time.sleep(poll_interval)

    return False


def setup_logging(log_file: Optional[str] = None, verbose: bool = False) -> None:
    """
    Set up logging configuration.
    
    Args:
        log_file: Path to log file (None for stderr only)
        verbose: Enable verbose output
    """
    level = logging.DEBUG if verbose else logging.INFO
    
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

    # Pillow can emit extremely verbose debug logs when the root logger is DEBUG.
    # Keep our game logs readable.
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("PIL.PngImagePlugin").setLevel(logging.WARNING)


def play_game(
    connector: GrandmasterChessConnector,
    stockfish_path: str,
    stockfish_plays_white: bool = True,
    time_limit: float = 1.0,
    max_moves: int = 200
) -> Optional[chess.Board]:
    """
    Play a game between Stockfish and the vintage chess connector.
    
    Args:
        connector: The game connector for the vintage chess game
        stockfish_path: Path to the Stockfish executable
        stockfish_plays_white: True if Stockfish plays as white
        time_limit: Time limit per move for Stockfish (seconds)
        max_moves: Maximum number of moves before declaring a draw
        
    Returns:
        The final board position, or None if game failed
    """
    # Initialize Stockfish engine
    try:
        engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
        logging.info(f"Stockfish initialized: {engine.id.get('name', 'Unknown')}")
    except Exception as e:
        logging.error(f"Failed to start Stockfish: {e}")
        return None
    
    # Initialize the connector
    if not connector.initialize():
        logging.error("Failed to initialize game connector")
        engine.quit()
        return None
    
    logging.info("Game connector initialized")
    
    # Set up the board tracking
    board = chess.Board()
    move_count = 0
    
    try:
        logging.info("=" * 60)
        logging.info("Starting game!")
        logging.info(f"Stockfish plays: {'White' if stockfish_plays_white else 'Black'}")
        logging.info(f"Vintage game plays: {'Black' if stockfish_plays_white else 'White'}")
        logging.info("=" * 60)
        
        while not board.is_game_over() and move_count < max_moves:
            move_count += 1
            is_stockfish_turn = (board.turn == chess.WHITE) == stockfish_plays_white
            
            logging.info(f"\nMove {(move_count + 1) // 2}{'.' if board.turn == chess.WHITE else '...'}")
            logging.debug(f"Board FEN: {board.fen()}")
            
            if is_stockfish_turn:
                # Stockfish's turn
                logging.info("Stockfish is thinking...")
                
                result = engine.play(board, chess.engine.Limit(time=time_limit))
                move = result.move
                
                if move is None:
                    logging.error("Stockfish returned no move")
                    break
                
                logging.info(f"Stockfish plays: {board.san(move)}")
                
                # Execute the move on the vintage game
                if not connector.execute_move(move):
                    logging.error(f"Failed to execute move {move} on vintage game")
                    break
                
                # Update our tracking board
                board.push(move)

                # Wait for the UI board state to reflect the move (no fixed sleeps)
                if not wait_for_board_to_match(connector, board, timeout=15.0):
                    logging.warning("Timed out waiting for vintage UI to reflect Stockfish move")
                
            else:
                # Vintage game's turn - wait for it to make a move
                logging.info("Waiting for vintage game to move...")
                
                # Wait for the vintage game to finish thinking.
                # Provide an expected pre-state so the connector can sync to the UI.
                vintage_move = connector.wait_for_engine_move(expected_pre_state=board)
                
                if vintage_move is None:
                    logging.error("Failed to detect vintage game's move")
                    # Try to read the board state and figure out what happened
                    current_state = connector.get_board_state()
                    logging.debug(f"Current board state: {current_state.fen()}")
                    break
                
                logging.info(f"Vintage game plays: {board.san(vintage_move)}")
                board.push(vintage_move)
            
            # Display the current position
            print(f"\n{board}\n")
        
        # Game ended
        logging.info("=" * 60)
        
        if board.is_checkmate():
            winner = "Black" if board.turn == chess.WHITE else "White"
            logging.info(f"Checkmate! {winner} wins!")
        elif board.is_stalemate():
            logging.info("Stalemate! Draw.")
        elif board.is_insufficient_material():
            logging.info("Insufficient material! Draw.")
        elif board.is_fifty_moves():
            logging.info("Fifty move rule! Draw.")
        elif board.is_repetition():
            logging.info("Threefold repetition! Draw.")
        elif move_count >= max_moves:
            logging.info(f"Game stopped after {max_moves} moves.")
        
        logging.info(f"Final position: {board.fen()}")
        logging.info("=" * 60)
        
        return board
        
    except KeyboardInterrupt:
        logging.info("\nGame interrupted by user")
        return board
        
    finally:
        engine.quit()
        connector.shutdown()


def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code (0 for success)
    """
    parser = argparse.ArgumentParser(
        description='Play Stockfish against a vintage chess game'
    )
    parser.add_argument(
        '--stockfish', '-s',
        type=str,
        default='stockfish',
        help='Path to Stockfish executable (default: stockfish)'
    )
    parser.add_argument(
        '--stockfish-white', '-w',
        action='store_true',
        default=True,
        help='Stockfish plays as white (default)'
    )
    parser.add_argument(
        '--stockfish-black', '-b',
        action='store_true',
        help='Stockfish plays as black'
    )
    parser.add_argument(
        '--time', '-t',
        type=float,
        default=1.0,
        help='Time limit per move for Stockfish in seconds (default: 1.0)'
    )
    parser.add_argument(
        '--max-moves', '-m',
        type=int,
        default=200,
        help='Maximum number of moves before stopping (default: 200)'
    )
    parser.add_argument(
        '--log', '-l',
        type=str,
        default=None,
        help='Log file path (default: None, logs to stderr only)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.log, args.verbose)
    
    # Determine which color Stockfish plays
    stockfish_plays_white = not args.stockfish_black
    
    # Create the connector
    connector = GrandmasterChessConnector()
    
    # Play the game
    result = play_game(
        connector=connector,
        stockfish_path=args.stockfish,
        stockfish_plays_white=stockfish_plays_white,
        time_limit=args.time,
        max_moves=args.max_moves
    )
    
    return 0 if result is not None else 1


if __name__ == '__main__':
    sys.exit(main())
