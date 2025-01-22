# Chess Game State Diagram

This document describes the states and UCI command handling in chess game connectors. The connectors serve as interfaces between UCI and chess game emulators, translating UCI commands to emulator-specific actions and vice versa.

## Connector States

### Initializing

Initial state when the connector is starting or searching for the emulator.

Available UCI commands:

- None (all commands should be queued or rejected)

Transitions to:

- `GameReady` when emulator is found and initialized

### GameReady

The connector is connected to the emulator and ready for a new game. The emulator is typically in its main menu or game screen.

Available UCI commands:

- `uci`: Initialize UCI mode
- `isready`: Check if engine is ready
- `ucinewgame`: Start a new game
- `position`: Set up initial position
- `setoption`: Configure engine parameters
- `quit`: Exit the program

Transitions to:

- `Configuring` when receiving game initialization commands
- `Terminating` when receiving quit command

### Configuring

Handles initialization tasks like:

- Setting up board position
- Configuring time controls
- Skipping cutscenes/menus
- Establishing player sides

Available UCI commands:

- `isready`: Check setup completion
- `stop`: Abort setup if possible

Transitions to:

- `Computing` when setup complete and engine plays white
- `Observing` when setup complete and engine plays black

### Computing

Engine is calculating and executing its move.

Available UCI commands:

- `stop`: Cancel current calculation
- `isready`: Check if move is complete
- `go`: Analyze position (only if previous calculation was stopped)

Transitions to:

- `Observing` after move execution
- `Pondering` if ponder is enabled
- `Terminating` when receiving quit command
- `Error` on critical failure

### Pondering

Engine is calculating during opponent's time, analyzing predicted moves.

Available UCI commands:

- `ponderhit`: Opponent made the predicted move
- `stop`: Cancel pondering
- `isready`: Check engine status
- `quit`: Exit program

Transitions to:

- `Computing` on ponderhit
- `Observing` when stopping
- `Terminating` when receiving quit command
- `Error` on critical failure

### Observing

Engine is waiting for opponent's move.

Available UCI commands:

- `position`: Update with opponent's move
- `isready`: Check engine status
- `stop`: Cancel any background processing
- `go`: Start new calculation after position update

Transitions to:

- `Computing` after receiving opponent's move
- `Terminating` when receiving quit command
- `Error` on critical failure

### Error

Handles error conditions and recovery attempts.

Available UCI commands:

- `isready`: Check if engine can recover
- `quit`: Exit program

Transitions to:

- `Initializing` on recovery attempt
- `Terminating` when recovery impossible or quit received

### Terminating

Final state for shutting down the emulator gracefully.

Available UCI commands:

- None (all commands should be rejected)

Performs:

- Saves any necessary state
- Closes emulator process
- Releases system resources
- Sends final acknowledgment to UCI interface

Transitions to:

- None (terminal state)
