"""
Abstract base class for chess game connectors.

Each chess game implementation must extend GameConnector and implement
the abstract methods for each state. The UCIHandler manages state transitions
and calls these methods appropriately.
"""

from abc import ABC, abstractmethod
from typing import Optional
from chess import Board, Move, STARTING_FEN, WHITE, BLACK, Color

from state import GameState


class GameConnector(ABC):
    """
    Abstract base class that defines the interface for chess game connectors.
    
    Each game implementation must provide:
    - Game metadata (name, author, year)
    - State-specific behavior implementations
    - Board state reading capabilities
    - Move execution capabilities
    
    The connector acts as a bridge between the UCI protocol and a specific
    chess game emulator.
    """
    
    def __init__(self, name: str, author: str, year: str) -> None:
        """
        Initialize the game connector.
        
        Args:
            name: Display name of the chess game
            author: Author/creator of the connector
            year: Year of the original game
        """
        self.name = name
        self.author = author
        self.year = year
        self._engine_color: Color = WHITE
    
    @property
    def engine_color(self) -> Color:
        """The color that the engine is playing as."""
        return self._engine_color
    
    @engine_color.setter
    def engine_color(self, color: Color) -> None:
        """Set the color that the engine is playing as."""
        self._engine_color = color
    
    # =========================================================================
    # Initialization Methods
    # =========================================================================
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the connector and find the emulator.
        
        Called when transitioning from INITIALIZING to GAME_READY.
        Should locate the game window, set up any classifiers, etc.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def is_emulator_ready(self) -> bool:
        """
        Check if the emulator is found and ready.
        
        Returns:
            True if the emulator is detected and responsive
        """
        pass
    
    # =========================================================================
    # Game State Methods
    # =========================================================================
    
    @abstractmethod
    def get_board_state(self) -> Board:
        """
        Read and return the current board state from the emulator.
        
        Returns:
            A chess.Board object representing the current position
        """
        pass
    
    @abstractmethod
    def setup_new_game(self) -> bool:
        """
        Set up a new game in the emulator.
        
        Called during CONFIGURING state. Should:
        - Navigate menus if needed
        - Start a new game
        - Ensure board is in starting position
        
        Returns:
            True if setup was successful
        """
        pass
    
    @abstractmethod
    def setup_position(self, board: Board) -> bool:
        """
        Set up a specific position in the emulator.
        
        Args:
            board: The target position to set up
            
        Returns:
            True if the position was set up successfully
        """
        pass
    
    # =========================================================================
    # Move Execution Methods
    # =========================================================================
    
    @abstractmethod
    def execute_move(self, move: Move) -> bool:
        """
        Execute a move on the emulator.
        
        This is called when the engine needs to make a move (COMPUTING state)
        or when entering the opponent's move (OBSERVING -> COMPUTING transition).
        
        Args:
            move: The move to execute
            
        Returns:
            True if the move was executed successfully
        """
        pass
    
    @abstractmethod
    def wait_for_engine_move(self, expected_pre_state: Optional[Board] = None) -> Optional[Move]:
        """
        Wait for the emulator's engine to make its move.
        
        Called during COMPUTING state when the emulator is thinking.
        
        Args:
            expected_pre_state: The expected board state before the engine moves.
                               If provided, implementations should ensure the screen
                               stably matches this state before capturing the pre-move
                               position to avoid race conditions with fast engines.
        
        Returns:
            The move made by the emulator's engine, or None if interrupted
        """
        pass
    
    @abstractmethod
    def is_engine_thinking(self) -> bool:
        """
        Check if the emulator's engine is currently calculating.
        
        Returns:
            True if the engine is thinking
        """
        pass
    
    # =========================================================================
    # Pondering Methods (optional - default implementations provided)
    # =========================================================================
    
    def start_pondering(self, predicted_move: Move) -> bool:
        """
        Start pondering on a predicted opponent move.
        
        Override this if the game supports pondering.
        
        Args:
            predicted_move: The move predicted for the opponent
            
        Returns:
            True if pondering started successfully
        """
        return False  # Default: pondering not supported
    
    def stop_pondering(self) -> Optional[Move]:
        """
        Stop pondering and return any result.
        
        Returns:
            The best move found during pondering, or None
        """
        return None
    
    def supports_pondering(self) -> bool:
        """
        Check if this game connector supports pondering.
        
        Returns:
            True if pondering is supported
        """
        return False
    
    # =========================================================================
    # Control Methods
    # =========================================================================
    
    @abstractmethod
    def stop_calculation(self) -> bool:
        """
        Stop any ongoing calculation in the emulator.
        
        Returns:
            True if calculation was stopped successfully
        """
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """
        Gracefully shut down the emulator connection.
        
        Called during TERMINATING state. Should:
        - Save any necessary state
        - Close connections
        - Release resources
        """
        pass
    
    # =========================================================================
    # Error Recovery Methods
    # =========================================================================
    
    def attempt_recovery(self) -> bool:
        """
        Attempt to recover from an error state.
        
        Override this to provide game-specific error recovery.
        
        Returns:
            True if recovery was successful
        """
        return False
    
    def get_error_info(self) -> Optional[str]:
        """
        Get information about the current error.
        
        Returns:
            Error description string, or None if no error
        """
        return None
    
    # =========================================================================
    # Configuration Methods
    # =========================================================================
    
    def set_option(self, name: str, value: str) -> bool:
        """
        Set a game-specific option.
        
        Override to handle game-specific UCI options.
        
        Args:
            name: Option name
            value: Option value
            
        Returns:
            True if the option was set successfully
        """
        return False
    
    def get_options(self) -> dict[str, dict]:
        """
        Get available options for this game connector.
        
        Returns:
            Dictionary of option names to option definitions
        """
        return {}
