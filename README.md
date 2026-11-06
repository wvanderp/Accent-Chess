# Accent Chess

We want to bring old chess computers back to life in this project. It will do this by providing a UCI interface to emulators of old chess computers. This way, you can play against the old chess computers using modern chess engines.

## Architecture

A local DOSBox container and optional native observer are now available as a
prototype. See [local emulation setup and architecture](docs/local-emulation.md).
The existing UCI game connectors still use Archive.org pending per-game migration.

Atari ST emulation is available through Hatari: select **battlechess** to boot
the 1989 ST release with checksum-verified EmuTOS firmware. Its 2D board reader
is implemented, and a validation runner has completed two games against its
engine through checkmate. Viewer play is still under development. See
[Battle Chess runtime findings](docs/battle-chess.md) for startup and input details.

Launch `python -m emulation.viewer` for the control panel. Choose a game and press
Start game to build and start Docker, download its media inside the container, and
watch the emulator. Grandmaster uses DOSBox; Chess 19xx and Chessmaster 2000 use VICE for Commodore 64.
The panel recognizes their default 2D boards directly from runtime frames. Enable
**Save debug frames** to collect PNGs, annotated boards and JSON diagnostics under
`debug-frames/`. For headless recognition or offline frame analysis, see
[recognition and debugging](docs/recognition.md).

To play a game, press **Start game**, then **New game**. Wait for
**White to move · your turn**, then click a piece and its destination on the
drawn board. The panel types the move in the emulator and recognizes the engine's reply
before accepting the next move. **New game** also resets a game already in progress.
For Grandmaster, keep the default **Computer plays BLACK** mode and the default
2D board. Chess 19xx uses keyboard coordinates such as `A2-A3`, then Return;
the drawn board handles this automatically.
See [local play architecture and findings](docs/local-play.md).

Choose **chessmaster2000** for The Chessmaster 2000 (1986), using the original
two-sided Commodore 64 release. Keep the default 2D board, white at the bottom,
and **YOU vs. CHESSMASTER**. Its disk loader needs accurate 1541 emulation, so
booting can take longer than Chess 19xx. The connector navigates New game,
enters moves in the text view, and returns to the board after the reply.
See [Chessmaster 2000 findings and validation](docs/chessmaster2000.md).

For Stockfish advice, use **Analyze position** when the panel confirms your turn.
The panel displays the best move and evaluation and highlights its source and
destination. **Play best move** sends that move through the normal play session.
Stockfish must be installed separately: use `stockfish` on PATH, select its
executable with **Browse…**, or launch with `--stockfish C:\path\to\stockfish.exe`.
Set **Seconds** to control thinking time (0.1–60 seconds; default 1).
The panel remembers a verified Stockfish location for the next launch. A green
**✓** beside Browse means the engine passed its UCI initialization and readiness
checks; a red **✗** shows a problem, with details below the progress log.

The architecture consists of two major parts. First, we have classes that know how to work with the emulators. Second, we have a UCI interface. The special sauce is the class that knows how to connect the two.

### Emulator Classes

These classes need to know the following things:

- How to start the emulator
- How to get into the game
- What the current game state is
- How to make a move
- How to create an arbitrary game state

They also need to know which UCI commands they can handle. Some engines cannot start from an arbitrary game state.

### UCI Interface

The UCI interface will handle the communication with the outside world. It will parse the commands and send them to the correct emulator. It will also need to know how to handle the responses from the emulators.

The UCI interface needs to soften the edges of the emulators. It can talk to the emulator classes to get things done. But it also needs to know what counts as thinking time and what counts as setup time. It can take some time to set up a game state. And it can take some time to make a move. But the UCI interface needs to know what is what.

## TODO

- [ ] Create the UCI interface
  - [ ] Understand the UCI protocol
  - [ ] Create a UCI parser
  - [ ] Create a base class for the emulators that can handle the UCI protocol
  - [ ] Create an I/O interface for the UCI interface
- [ ] Emulators
  - [ ] Create a framework for setting up emulators
    - [ ] The Internet Archive compatibility
    - [ ] DOSBox
    - [ ] GameBoy emulator
    - [ ] MAME
  - [ ] Create a prototype for one game
  - [ ] Create utilities
    - [ ] Image chessboard reader
    - [ ] Game state checker
    - [ ] Checking for valid moves

## Potential Games

- 1K ZX Chess (<https://archive.org/details/doshaven_bootchess>)
- Battle Chess (<https://archive.org/details/Battle_Chess_1989_Interplay_cr_MCA_m_EMT>)
- Bobby Fischer Teaches Chess (<https://archive.org/details/msdos_Bobby_Fischer_Teaches_Chess_1994>)
- Chess 7.0
- Chess Champion 2175
- Chess Simulator
- Chess Titans
- Chess Wars
- Chessmaster 3000 (and the other Chessmaster games)
- Colossus Chess
- Combat Chess
- Cyber Chess
- Fritz
- Grandmaster Chess
- How About A Nice Game of Chess?
- Kasparov Chessmate
- Kasparov's Gambit
- Kotok-McCarthy
- Lego Chess
- Mac Hack
- MChess Pro
- Microchess
- Nova Chess (<https://archive.org/details/NovaChessV1.121996ThomasStarkeStrategyChess>)
- Paul Whitehead Teaches Chess
- Pocket Fritz
- Power Chess
- Sargon
- Sargon II (<https://archive.org/details/d64_Sargon_II_1983_Hayden_Software>)
- Sega Chess
- Silver Star Chess
- Socrates II
- Star Wars Chess
- Toledo Nanochess
- Ultimate Brain Game
- Video Chess
- Virtua Chess
- Virtual Chess 64
- Virtual Kasparov
- Wii Chess
- Zillions of Games

And while this is an impressive list of games, it is currently just a list. We need to determine which games we can emulate and which of these games we can actually play against.

## Thoughts

To make this project a success, it needs to be easily accessible. Controlling it with UCI is the most straightforward way to do this.

The challenge with the UCI protocol is that the game state is very fragile, and UCI can ask an engine to start from any game state.

To ensure we can accommodate this, we need to implement a more narrow version of the UCI protocol and error out when we cannot handle the request.

## Tournament

Native difficulty presets are separate ranking engines by default. See
[difficulty findings and setting scripts](docs/difficulty/README.md) for each
program's verified presets. Vintage engines can finish their full native search;
there is no external thinking deadline by default. Stockfish remains the single
maximum-skill measuring stick.

Run six different pairings unattended, including runtime startup and shutdown:

```powershell
python -m emulation.tournament run --count 6
```

Docker Desktop must have a running Linux backend. Stockfish is discovered from
its verified viewer setting or PATH; use `--stockfish C:\bins\stockfish\stockfish.exe`
to select it explicitly. No open viewer or manually started game is required.
The runner builds the image once and gives each vintage participant a fresh
container on an automatically allocated loopback port. Viewer sessions are kept
separate. Use `--data PATH` for an independent tournament.

All ordered catalog pairings are retained in `tournament-data/state.json`,
including unsupported ones. Grandmaster and Chessmaster 2000 can play either
side; Chess 19xx currently plays Black. Battle Chess is pending a fully automated
reset/play connector. Registered UCI engines can play either color. Adding a game
extends the schedule without losing history.

```powershell
python -m emulation.tournament pending
python -m emulation.tournament ranking
python -m emulation.tournament history
```

`--count` means completed, distinct ordered pairings in that invocation, not
attempts. A color reversal is a different round-robin pairing. Failed matches
remain pending; the runner continues to other runnable pairings and exits with
an error unless the requested count completes. It refuses a request larger than
the available runnable schedule. Run again to play remaining pending pairings;
use a different data directory to start a new tournament.

Each attempt has a UUID directory with PGN, confirmed move/FEN log, final frames,
emulator logs, and failure diagnostics when applicable. A `run-<id>.json` manifest
links attempts from a single invocation and records its requested/completed count.
Verified game endings and explicit UI resignations enter the ranking. Threefold/fifty-move claims follow
python-chess rules; timeouts and ply limits remain failures, never invented draws
or wins. Rankings are provisional point totals until the schedule is complete.

The ledger uses atomic replacement and a process lock. Interrupted attempts are
recovered as failed on the next run. Back up the entire data directory. Additional
UCI engine definitions can be stored in the ledger as `{"kind": "uci", "command":
"C:\\path\\engine.exe"}`. `--external-runtimes` is available for investigation
using each vintage entry's `url`; the default owns its runtimes automatically.
See [tournament architecture and findings](docs/tournament.md).

A single unattended invocation has completed six distinct matches, with zero
failed attempts. See the [verified run and evidence](docs/tournament.md#verified-six-match-invocation).
All nine currently supported pairings have since completed; see the
[additional results and remaining limitations](docs/tournament.md#remaining-supported-pairings-completed).
