# Local play

Launch `python -m emulation.viewer`, select `grandmaster` or `chess19xx`, press **Start game**,
then **New game**. Starting builds the current runtime; older containers need to
be started again to acquire the pointer endpoint and game identity field.
With recognition enabled, wait for **White to move · your turn**. Click a white
piece and its destination on the drawn board. The selected square is highlighted;
illegal moves are rejected. Promotion offers q/r/b/n. Input stays disabled during
reset, move acknowledgement, engine calculation, and unreadable frames.

The supported setup is Grandmaster's default 2D board, white at the bottom,
**Game > Set Players > Computer plays BLACK**. Reset verifies the player labels
and reports an incompatible mode. Chess 19xx supports reset and keyboard play
through the same drawn board. This feature does not change the legacy UCI path.

## Boundaries

`emulation/play.py` owns a UI-independent `PlaySession` and the `PlayConnector`
protocol. A game-specific connector owns keyboard input and visual menu states.
Register additional implementations in `PLAY_MODULES`. The runtime continues
to provide pixels and serialized input without chess rules. Snapshots include
the configured game identity; the viewer refuses reset if it differs from the
selected connector. The viewer's single polling worker owns recognition and play;
Tk submits commands through a queue and receives copied state snapshots.

`RuntimeRecognizer.confirmed_placement` is populated only when the current capture
has passed recognition, two-capture placement confirmation, and frame-linked
publication. The play session consumes that value directly, never the retained
board observation from an earlier screenshot. Changing debug recording preserves
the game; changing game or disabling recognition discards the tracked session.

An observed placement cannot establish a turn by itself. The connector must first
complete a reset and recognize the standard starting board. The session then
maintains a python-chess board and accepts only unique legal successors. A sent
move remains pending until the emulator shows it. If the engine replies between
captures, the observation must match the submitted move followed by a unique
legal reply. This preserves turn, castling rights, en-passant and counters.
Unrelated positions disable move input; deadlines report failure and require a
new reset. Timeout does not imply move completion. Poll pacing uses cancellable
`Event.wait`; no connector uses sleeps to decide whether the engine has moved.
Manual emulator input invalidates the tracked game and requires New game.

## Stockfish advice

**Analyze position** analyzes the current confirmed player turn. Choose the local
Stockfish executable and thinking time in the panel (or use `--stockfish` at
startup). The executable defaults to `stockfish` on PATH; no additional Python
package is needed beyond the existing `chess` dependency. The result shows SAN,
UCI coordinates and an evaluation from White's perspective. Blue outlines mark
the move's source and destination. **Play best move** submits it through the same
legal-move and emulator-acknowledgement path as a board click.

The panel first uses an explicit `--stockfish` argument, otherwise the saved
location, then `stockfish` on PATH. Startup and path edits trigger background UCI
initialization and readiness checks. A green **✓** beside Browse confirms success;
a red **✗** and status text explain failure. Edits are debounced and late results
are discarded so an old path cannot gain a check mark or overwrite preferences.
Only successfully verified paths are saved, resolved to an absolute binary
location. Invalid edits retain the last working saved location.

`emulation/settings.py` owns per-user JSON preferences, outside the checkout:
`%APPDATA%/Accent-Chess/settings.json` on Windows or
`${XDG_CONFIG_HOME:-~/.config}/Accent-Chess/settings.json` elsewhere. Atomic
replacement preserves previous settings if saving fails. Missing or malformed
settings fall back to discovery; write errors appear in the panel. Validation
does not depend on connecting to the emulator or starting a new game.

`emulation/analysis.py` isolates UCI process ownership from Tk and game connectors.
The polling worker owns an `AnalysisSession`; each request copies the complete
tracked board, including its move stack, into a background search. Recognition,
emulator input and Tk refresh continue during analysis. Each bounded search owns
and closes its engine process, including on failure. Only one search can run at
a time. Errors appear in the advice label and permit another request.

Advice requires `PlaySession.ready`: an image supplies placement but cannot
establish turn, castling rights or en-passant. Reset and legal move tracking
supply those facts. Advice clears when confirmation is lost, a move is submitted,
the session is reset, manual input occurs or the selected game changes. A
generation counter also rejects a late result when a reset returns to the same
FEN. Queued analysis and move commands check the expected FEN before use.

Validation includes a real local Stockfish search and a native Tk smoke run with
simulated runtime frames: Analyze position displayed a real engine result and
Play best move delivered a legal move to the connector. Unit tests cover UCI
cleanup, evaluation perspective, copied history, invalid limits, missing engines,
search errors, concurrent-request rejection and stale results across resets.

## Investigation findings

Grandmaster accepts coordinate keys (`e`, `2`, `e`, `4`, `Return`). It needs no
click on the board, focus delay or Escape after a normal move. F2 opens Game;
Down selects its first entry and Return opens the new-game confirmation. A second
Return accepts. Saved menu/dialog reference frames gate these actions. Stable boot
screens receive Escape until the calibrated board is visible. Animation is never
treated as a ready board.

The DOS hand cursor is included in captured pixels and can cause an unknown-piece
error. Grandmaster recenters it when closing the new-game dialog, independently
of the host pointer. Parking immediately after sending Return races that warp.
The connector therefore waits until the dialog disappears, then moves the X11
pointer from the far corner to the origin to clamp the game's relative cursor
outside the board. The new `/v1/pointer` input moves without clicking. Switching
DOSBox to windowed mode did not resolve the relative-cursor behavior; the existing
fullscreen configuration is retained.

Validation covers real DOSBox startup, reset, coordinate move input, and a
recognized engine reply. Automated tests cover staged menu/dialog navigation,
pending acknowledgement, fast replies, turn gating, castling history, illegal
moves, unreadable/unrelated frames, timeout, and reset recovery. A complete game
and live promotion/en-passant/castling input have not yet been validated against
the emulator; rule tracking covers legal special moves but is separate from the
vintage program's input behavior.

### Chess 19xx keyboard findings

F1 restores the starting board, clears coordinate input, last move and move count,
and retains the on-screen clocks. Moves use `A2-A3` followed by Return. The C64
keyboard scan can miss xdotool's default 12ms key sequence. The local key endpoint
now accepts a bounded `delay_ms` parameter; the C64 connector uses 200ms sequences
to make the physical key events visible to the emulated hardware. This does not
decide when an engine move is complete.

VICE's GTK window can also leave keyboard focus at Xvfb's root window because
there is no window manager. Pointer position does not guarantee delivery. C64 key
requests specify the exact `VICE (C64SC)` window title; the runtime focuses that
window before each key using a literal, escaped title match. No game clicks are
needed. The key endpoint's optional `window_title` keeps X11 details in the runtime.

The connector's `advance(frame)` types one coordinate character at a time. The
prompt text must visibly grow and stabilize across two captures before the next
character is sent. The input routine can reposition existing text, so exact
prefix pixel equality is not required. An unchanged prompt permits at most two retries
of the same key after four unchanged captures; continued failure blocks input
until the session deadline. After Return, legal board observations
acknowledge the human move and engine reply using the same PlaySession as DOS.
Reset requires the starting placement, empty input, cleared last move and count.

Live validation repeated F1, `A2-A3`, Return, and recognition of `B8-C6` twice.
The native panel was also exercised with New game and actual A2/A3 canvas events,
through keyboard entry, engine reply, and restoration of the user's turn.
The moved knight exposed a recognition problem: GTK's fractional resampling
shifted its silhouette enough to favor a bishop template. C64 templates now allow
two normalized pixels of alignment in each direction; a captured regression
fixture checks the actual position after a3/Nc6. Grandmaster retains zero template
shift. C64 promotion input remains unverified and is rejected explicitly.


### Attaching to an existing game

The local connectors sample only the two clock digit regions (white first,
black second). On a repeated confirmed placement, a change to exactly one
clock establishes the side to move. No reset or fixed engine delay is needed.
A paused clock cannot establish a turn; resume the game and allow a clock tick.
Grandmaster uses the lower clock for white and upper clock for black in the
default orientation; C64 uses the second and first TID rows respectively.
These regions were identified from the native recognition fixtures. Live
validation of attachment in changed display modes remains outstanding.

Placement and clocks cannot recover castling or en passant history. Attached
positions therefore omit those rights; start through New game for complete
history and special-move analysis. Once attached, legal successors preserve
turn tracking as before. This does not require emulator process-memory access.


Live attachment investigation: the running C64 game after B7xA6 ticks the lower
TID row while awaiting White input. The initial implementation mapped this row
to Black, leaving both Stockfish buttons disabled. Corrected the mapping and
separated confirmed analysis availability from human move-input readiness.
The toolbar now explicitly shows Turn: White, Black, or unknown; unconfirmed
frames clear analysis availability rather than presenting a stale known turn.


The control panel queries the runtime snapshot's `game` field before choosing
recognition and play connectors. This field comes from Docker's `GAME_ID`,
passed to the HTTP session by the container supervisor. A running recognized
game takes precedence over the panel's launch selection (including --game).
The dropdown synchronizes when a running game is first detected or changes;
it can still select another game for the next Start game action. Containers
launched with custom GAME_EXECUTABLE media and no GAME_ID retain manual selection.
