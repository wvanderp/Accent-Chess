"""
State machine implementation for chess game connectors.

This module defines the states and transitions for UCI-compatible chess game connectors.
See docs/state-diagram.md for the full state diagram documentation.
"""

from enum import Enum, auto


class GameState(Enum):
    """
    Represents the possible states of a chess game connector.
    
    States:
        INITIALIZING: Initial state when connector is starting or searching for emulator
        GAME_READY: Connected to emulator and ready for a new game
        CONFIGURING: Setting up board position, time controls, skipping menus
        COMPUTING: Engine is calculating and executing its move
        PONDERING: Engine is calculating during opponent's time
        OBSERVING: Engine is waiting for opponent's move
        ERROR: Handles error conditions and recovery attempts
        TERMINATING: Final state for shutting down gracefully
    """
    INITIALIZING = auto()
    GAME_READY = auto()
    CONFIGURING = auto()
    COMPUTING = auto()
    PONDERING = auto()
    OBSERVING = auto()
    ERROR = auto()
    TERMINATING = auto()


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    
    def __init__(self, current_state: GameState, attempted_command: str) -> None:
        self.current_state = current_state
        self.attempted_command = attempted_command
        super().__init__(
            f"Cannot execute '{attempted_command}' in state {current_state.name}"
        )
