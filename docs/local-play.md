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
