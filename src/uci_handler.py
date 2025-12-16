"""
UCI Protocol Handler with State Machine.

This module implements the UCI (Universal Chess Interface) protocol
with a state machine that manages transitions between game states.
The UCIHandler delegates game-specific actions to a GameConnector.
"""

import sys
import logging
from typing import Optional, TextIO, Callable
from chess import Board, Move, STARTING_FEN, WHITE, BLACK

from state import GameState, StateTransitionError
from connector import GameConnector


class UCIHandler:
    """
    Handles the UCI protocol and manages game state transitions.
    
    The UCIHandler is responsible for:
    - Parsing and responding to UCI commands
    - Managing state transitions according to the state diagram
    - Delegating game-specific actions to the GameConnector
    
    The GameConnector handles the actual game interactions while
    this class handles the protocol and state management.
    """
    
    # Commands valid in each state
    VALID_COMMANDS: dict[GameState, set[str]] = {
        GameState.INITIALIZING: set(),  # All commands queued/rejected
        GameState.GAME_READY: {'uci', 'isready', 'ucinewgame', 'position', 'setoption', 'quit'},
        GameState.CONFIGURING: {'isready', 'stop'},
        GameState.COMPUTING: {'stop', 'isready', 'go', 'quit'},
        GameState.PONDERING: {'ponderhit', 'stop', 'isready', 'quit'},
        GameState.OBSERVING: {'position', 'isready', 'stop', 'go', 'quit'},
        GameState.ERROR: {'isready', 'quit'},
        GameState.TERMINATING: set(),  # All commands rejected
    }
    
    def __init__(
        self,
        connector: GameConnector,
        input_stream: TextIO = sys.stdin,
        output_stream: TextIO = sys.stdout,
        log_file: Optional[str] = 'uci.log'
    ) -> None:
        """
        Initialize the UCI handler.
        
        Args:
            connector: The game connector to delegate actions to
            input_stream: Input stream for UCI commands (default: stdin)
            output_stream: Output stream for UCI responses (default: stdout)
            log_file: Path to log file, or None to disable logging
        """
        self.connector = connector
        self.input_stream = input_stream
        self.output_stream = output_stream
        
        self._state = GameState.INITIALIZING
        self._position = Board(STARTING_FEN)
        self._ponder_move: Optional[Move] = None
        self._running = True
        
        # Set up logging
        if log_file:
            logging.basicConfig(
                filename=log_file,
                level=logging.DEBUG,
                format='%(asctime)s - %(levelname)s - %(message)s'
            )
        
        # Command handlers
        self._command_handlers: dict[str, Callable[[list[str]], None]] = {
            'uci': self._handle_uci,
            'isready': self._handle_isready,
            'ucinewgame': self._handle_ucinewgame,
            'position': self._handle_position,
            'go': self._handle_go,
            'stop': self._handle_stop,
            'ponderhit': self._handle_ponderhit,
            'setoption': self._handle_setoption,
            'quit': self._handle_quit,
        }
    
    @property
    def state(self) -> GameState:
        """Current state of the game connector."""
        return self._state
    
    def _transition_to(self, new_state: GameState) -> None:
        """
        Transition to a new state.
        
        Args:
            new_state: The state to transition to
        """
        logging.info(f"State transition: {self._state.name} -> {new_state.name}")
        self._state = new_state
    
    def _output(self, message: str) -> None:
        """
        Send a message to the UCI interface.
        
        Args:
            message: The message to send
        """
        print(message, file=self.output_stream, flush=True)
        logging.debug(f"<<< {message}")
    
    def _is_command_valid(self, command: str) -> bool:
        """
        Check if a command is valid in the current state.
        
        Args:
            command: The base command (without arguments)
            
        Returns:
            True if the command is valid in the current state
        """
        return command in self.VALID_COMMANDS.get(self._state, set())
    
    # =========================================================================
    # Main Loop
    # =========================================================================
    
    def run(self) -> None:
        """
        Main loop for processing UCI commands.
        
        This method blocks until 'quit' is received.
        """
        # First, try to initialize the connector
        self._initialize()
        
        while self._running:
            try:
                line = self.input_stream.readline()
                if not line:
                    break
                    
                line = line.strip()
                if not line:
                    continue
                    
                logging.debug(f">>> {line}")
                self._process_command(line)
                
            except EOFError:
                break
            except Exception as e:
                logging.error(f"Error processing command: {e}")
                self._transition_to(GameState.ERROR)
        
        # Ensure clean shutdown
        if self._state != GameState.TERMINATING:
            self._handle_quit([])
    
    def _initialize(self) -> None:
        """Initialize the connector and transition to GAME_READY."""
        try:
            if self.connector.initialize():
                self._transition_to(GameState.GAME_READY)
            else:
                logging.error("Failed to initialize connector")
                self._transition_to(GameState.ERROR)
        except Exception as e:
            logging.error(f"Exception during initialization: {e}")
            self._transition_to(GameState.ERROR)
    
    def _process_command(self, line: str) -> None:
        """
        Process a single UCI command.
        
        Args:
            line: The command line to process
        """
        parts = line.split()
        if not parts:
            return
            
        command = parts[0].lower()
        args = parts[1:]
        
        # Check if command is valid in current state
        if not self._is_command_valid(command):
            if self._state == GameState.INITIALIZING:
                logging.warning(f"Command '{command}' received during initialization, ignoring")
                return
            elif self._state == GameState.TERMINATING:
                logging.warning(f"Command '{command}' received during termination, ignoring")
                return
            else:
                logging.warning(
                    f"Command '{command}' not valid in state {self._state.name}"
                )
                # Still try to handle some commands gracefully
        
        # Handle the command
        handler = self._command_handlers.get(command)
        if handler:
            try:
                handler(args)
            except Exception as e:
                logging.error(f"Error handling command '{command}': {e}")
                self._transition_to(GameState.ERROR)
        else:
            logging.debug(f"Unknown command: {command}")
    
    # =========================================================================
    # Command Handlers
    # =========================================================================
    
    def _handle_uci(self, args: list[str]) -> None:
        """Handle the 'uci' command."""
        self._output(f"id name {self.connector.name}")
        self._output(f"id author {self.connector.author}")
        
        # Output available options
        for name, definition in self.connector.get_options().items():
            option_str = f"option name {name}"
            if 'type' in definition:
                option_str += f" type {definition['type']}"
            if 'default' in definition:
                option_str += f" default {definition['default']}"
            if 'min' in definition:
                option_str += f" min {definition['min']}"
            if 'max' in definition:
                option_str += f" max {definition['max']}"
            self._output(option_str)
        
        self._output("uciok")
    
    def _handle_isready(self, args: list[str]) -> None:
        """Handle the 'isready' command."""
        # In ERROR state, try recovery first
        if self._state == GameState.ERROR:
            if self.connector.attempt_recovery():
                self._transition_to(GameState.INITIALIZING)
                self._initialize()
        
        # Check if connector is ready
        if self.connector.is_emulator_ready():
            self._output("readyok")
        else:
            # Try to re-initialize
            if self.connector.initialize():
                self._transition_to(GameState.GAME_READY)
                self._output("readyok")
            else:
                self._transition_to(GameState.ERROR)
    
    def _handle_ucinewgame(self, args: list[str]) -> None:
        """Handle the 'ucinewgame' command."""
        self._transition_to(GameState.CONFIGURING)
        
        if self.connector.setup_new_game():
            self._position = Board(STARTING_FEN)
            # After setup, we observe (wait for first move or compute if engine is white)
            if self.connector.engine_color == WHITE:
                self._transition_to(GameState.COMPUTING)
            else:
                self._transition_to(GameState.OBSERVING)
        else:
            logging.error("Failed to set up new game")
            self._transition_to(GameState.ERROR)
    
    def _handle_position(self, args: list[str]) -> None:
        """
        Handle the 'position' command.
        
        Syntax: position [fen <fenstring> | startpos] [moves <move1> ... <movei>]
        """
        if not args:
            return
            
        # Parse the position
        if args[0] == 'startpos':
            self._position = Board(STARTING_FEN)
            args = args[1:]
        elif args[0] == 'fen':
            # Find where 'moves' starts (if present)
            moves_idx = None
            for i, arg in enumerate(args):
                if arg == 'moves':
                    moves_idx = i
                    break
            
            if moves_idx:
                fen_parts = args[1:moves_idx]
                args = args[moves_idx:]
            else:
                fen_parts = args[1:]
                args = []
            
            fen = ' '.join(fen_parts)
            self._position = Board(fen)
        else:
            logging.warning(f"Unknown position type: {args[0]}")
            return
        
        # Apply moves if present
        if args and args[0] == 'moves':
            for move_str in args[1:]:
                try:
                    move = Move.from_uci(move_str)
                    self._position.push(move)
                except ValueError:
                    logging.error(f"Invalid move: {move_str}")
                    return
        
        logging.debug(f"Position set to: {self._position.fen()}")
        
        # If we were observing and received a new position, opponent made a move
        if self._state == GameState.OBSERVING:
            # Position updated, ready for 'go' command
            pass
    
    def _handle_go(self, args: list[str]) -> None:
        """
        Handle the 'go' command.
        
        This triggers the engine to start calculating.
        """
        # Parse go arguments (time controls, etc.)
        ponder = 'ponder' in args
        
        # Transition to computing
        self._transition_to(GameState.COMPUTING)
        
        # Set up the position in the emulator if needed
        if not self.connector.setup_position(self._position):
            logging.error("Failed to set up position")
            self._transition_to(GameState.ERROR)
            return
        
        # Wait for engine to calculate
        engine_move = self.connector.wait_for_engine_move()
        
        if engine_move:
            # Output the best move
            best_move_str = f"bestmove {engine_move.uci()}"
            
            # Add ponder move if available and pondering is enabled
            if ponder and self.connector.supports_pondering():
                # For now, no ponder move
                pass
            
            self._output(best_move_str)
            
            # Update our internal position
            self._position.push(engine_move)
            
            # Transition to observing (waiting for opponent)
            self._transition_to(GameState.OBSERVING)
        else:
            # Calculation was stopped or failed
            if self._state == GameState.COMPUTING:
                self._transition_to(GameState.OBSERVING)
    
    def _handle_stop(self, args: list[str]) -> None:
        """Handle the 'stop' command."""
        if self._state == GameState.COMPUTING:
            self.connector.stop_calculation()
            # We should still output a bestmove if we have one
            # For now, transition to observing
            self._transition_to(GameState.OBSERVING)
            
        elif self._state == GameState.PONDERING:
            result = self.connector.stop_pondering()
            if result:
                self._output(f"bestmove {result.uci()}")
            self._transition_to(GameState.OBSERVING)
            
        elif self._state == GameState.CONFIGURING:
            # Abort setup if possible
            self._transition_to(GameState.GAME_READY)
    
    def _handle_ponderhit(self, args: list[str]) -> None:
        """Handle the 'ponderhit' command."""
        if self._state == GameState.PONDERING:
            # Opponent made the predicted move, continue calculating
            self._transition_to(GameState.COMPUTING)
    
    def _handle_setoption(self, args: list[str]) -> None:
        """
        Handle the 'setoption' command.
        
        Syntax: setoption name <id> [value <x>]
        """
        if len(args) < 2 or args[0] != 'name':
            return
        
        # Find the 'value' keyword
        value_idx = None
        for i, arg in enumerate(args):
            if arg == 'value':
                value_idx = i
                break
        
        if value_idx:
            name = ' '.join(args[1:value_idx])
            value = ' '.join(args[value_idx + 1:])
        else:
            name = ' '.join(args[1:])
            value = ''
        
        if not self.connector.set_option(name, value):
            logging.warning(f"Failed to set option: {name} = {value}")
    
    def _handle_quit(self, args: list[str]) -> None:
        """Handle the 'quit' command."""
        self._transition_to(GameState.TERMINATING)
        self.connector.shutdown()
        self._running = False
