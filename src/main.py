#!/usr/bin/env python3
"""
Accent-Chess: UCI interface for vintage chess game emulators.

This is the main entry point for the UCI chess engine connector.
It initializes a game connector and runs the UCI handler.
"""

import argparse
import logging
import sys
from typing import Optional

from uci_handler import UCIHandler


def get_available_games() -> dict[str, type]:
    """
    Get a dictionary of available game connectors.
    
    Returns:
        Dictionary mapping game names to their connector classes
    """
    games = {}
    
    try:
        from games.Chess_19xx.Chess_19xx import Chess19xxConnector
        games['chess19xx'] = Chess19xxConnector
    except ImportError:
        pass
    
    try:
        from games.Grandmaster_Chess.Grandmaster_Chess import GrandmasterChessConnector
        games['grandmaster'] = GrandmasterChessConnector
    except ImportError:
        pass
    
    return games


def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code (0 for success)
    """
    parser = argparse.ArgumentParser(
        description='UCI interface for vintage chess game emulators'
    )
    parser.add_argument(
        '--game', '-g',
        type=str,
        default='grandmaster',
        help='Game to use (chess19xx, grandmaster)'
    )
    parser.add_argument(
        '--log', '-l',
        type=str,
        default='uci.log',
        help='Log file path (use "none" to disable logging)'
    )
    parser.add_argument(
        '--list-games',
        action='store_true',
        help='List available games and exit'
    )
    
    args = parser.parse_args()
    
    available_games = get_available_games()
    
    if args.list_games:
        print("Available games:")
        for name in available_games:
            print(f"  - {name}")
        return 0
    
    if args.game not in available_games:
        print(f"Error: Unknown game '{args.game}'", file=sys.stderr)
        print(f"Available games: {', '.join(available_games.keys())}", file=sys.stderr)
        return 1
    
    # Create the game connector
    connector_class = available_games[args.game]
    connector = connector_class()
    
    # Set up logging
    log_file: Optional[str] = None if args.log == 'none' else args.log
    
    # Create and run the UCI handler
    handler = UCIHandler(
        connector=connector,
        log_file=log_file
    )
    
    handler.run()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
