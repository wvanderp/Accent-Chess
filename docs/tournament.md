# Tournament architecture and investigation

## Native difficulty update

The default schedule now uses separate verified native difficulty profiles.
See [difficulty investigation and commands](difficulty/README.md). The historical
acceptance results below predate recorded difficulty profiles and retain their
original engine names; they are not evidence of results at every new level.
Vintage move waits no longer have the former external search deadlines.

## Verified six-match invocation

On 2026-11-05 this single command completed six distinct ordered pairings in
23 minutes, with exit code 0 and no failed attempts or manual game input:

```powershell
python -m emulation.tournament run --count 6 --data tournament-data/acceptance
```

The batch included both vintage colors against Stockfish and a direct
Chessmaster 2000 versus Chess 19xx game. Four games ended in checkmate and two
in explicit Grandmaster resignations. An independent audit replayed every
legal move, compared event FENs with PGNs, checked all final board frames, and
verified the resignation dialogs. All 109 repository tests passed.

See the [verification report](evidence/tournament-2026-11-05/verification.json),
[run manifest](evidence/tournament-2026-11-05/run.json), and
[provisional ranking](evidence/tournament-2026-11-05/ranking.json). The same
evidence directory contains the six PGNs, move logs, final frames, runner log,
and audit script. Runtime containers were removed automatically.

The acceptance ledger retains its completed pairings. Use a fresh `--data`
directory for another six-match batch, or inspect/play its remaining pending
pairings with a smaller count. This proves unattended tournament operation;
Battle Chess and Chess 19xx's White-side control remain unsupported, so the
full-catalog ranking is still provisional.

The tournament schedules ordered pairs (each color assignment once), persists
attempts, and ranks completed games by points, then wins. The catalog includes
programs whose connectors are not yet ready; capability checks retain those
pairings as pending instead of replacing their moves with another engine.

## Remaining supported pairings completed

All nine currently runnable ordered pairings are now complete in the acceptance
ledger. The three additional results are:

| White | Black | Result | Ending |
| --- | --- | --- | --- |
| Chessmaster 2000 | Grandmaster | 1/2-1/2 | Threefold repetition, 39 plies |
| Grandmaster | Chessmaster 2000 | 1/2-1/2 | Threefold repetition, 74 plies |
| Grandmaster | Chess 19xx | 1-0 | Checkmate, 107 plies |

These results were retained across batches while longer games exposed the
connector issues documented below. Failed attempts remain unscored; this
extension is not claimed as one failure-free invocation. The final one-game
invocation completed unattended, including queen promotion and both programs'
final-board acknowledgement. All 127 tests passed with a workspace-local pytest
temporary directory (the default Windows temporary directory denied access).

The [additional verification report](evidence/tournament-2026-11-05/remaining/verification.json)
links each successful attempt and source run manifest. Its directory includes
three PGNs, move logs, six final frames, runner logs, the independent audit
script, and the [updated ranking](evidence/tournament-2026-11-05/remaining/ranking.json).
The audit checked every legal move/FEN, PGN and both final boards. No tournament
runtime containers remain running.

Stockfish leads with 5/5 points; Grandmaster has 2/5, Chess 19xx 1/3, and
Chessmaster 2000 1/5. Battle Chess is unplayed. Eleven ordered pairings remain
unsupported: eight involving Battle Chess, plus three additional pairings with
Chess 19xx playing White. These unequal schedules make the ranking provisional.

## Responsibilities

- `tournament.py`: ledger, scheduling, authoritative chess history, PGN and run
  manifests. It validates every move and requires a normal ending or verified
  UI resignation before completing a game.
- `participants.py`: a common move-producing boundary for UCI processes and
  vintage programs. Vintage histories must agree with the tournament history;
  the adapter submits only the opponent's next move and waits for confirmation.
- `tournament_runtime.py`: disposable Docker ownership, dynamically allocated
  loopback ports, startup checks, runtime logs, and cleanup on exceptions.
- Game `play.py` connectors: reset menus, side changes, keyboard readiness,
  coordinate entry and explicit UI acknowledgements. Color capabilities live
  with the connector and gate scheduling through `supports_color`.
- `recognition/board.py`: piece placement, including an optional reversed square
  mapping. It does not infer side to move, special-move rights or results.
- `PlaySession`: resets establish the initial position; unique legal successors
  preserve turn, castling, en passant and move counters.

Both vintage participants run independently. Each computes its own moves from
the same relayed history. The losing program also receives and acknowledges
the final move before completion is recorded. UCI searches use the complete
history, rather than a FEN stripped of repetition information.

`--count 6` requires six distinct ordered pairings completed by one invocation.
Failures do not consume this count. The process exits unsuccessfully if it runs
out of runnable pairings before reaching the target. A fresh data directory
starts a new schedule; otherwise completed pairings are never silently replayed.
Timeouts and ply limits are failures. Standard draw claims are adjudicated from
the authoritative history using `python-chess`, with the termination in the PGN.

## Live findings, 2026-11-05

Grandmaster's Game > Switch Sides is `F2`, `Down`, `Down`, `Return` from a closed
menu. At the starting position it makes the computer play White and reverses
the board ends. Sprites remain upright and coordinate entry remains absolute.
Recognition therefore remaps square indices, rather than rotating pixels or
swapping chess colors. A real side change is essential: reflecting a position
alone cannot make two engines that only play Black start a game.

Grandmaster can draw its reply before accepting coordinate keys. Observing the
lower human clock advance gates subsequent input; the initial stopped clock is
handled by the verified reset. The 12ms X11 key duration lost characters under
host load; 150ms key sequences are reliable in probing. Key duration is an
electrical-input setting, not evidence of engine completion.

The original Grandmaster templates misread a white queen on a dark square as a
second white king. A live frame after Qf4+/Kg6 supplied the missing queen
silhouette. Black gold sprite interiors also provide a more robust color cue
than counting only dark-red shadow pixels. Chess 19xx's moved queen at f6 was
misread as a rook after GTK resampling; the explicit D8-F6 move display and legal
history confirmed its identity. Captured regression frames cover both cases.
Later, the legal E5-F5 king reply to 44.Nd7+ lost its crown under GTK
resampling and matched a pawn. Its move display and the confirmed predecessor
label a dedicated king template; the full captured position is a regression
fixture. The failed recognition attempt receives no tournament points.

Grandmaster also resigns through a modal Computer Resigns! dialog. That exact
dialog is a verified result, not a move timeout or a checkmate inferred from
engine evaluation. The connector reports its actual computer color; the runner
records resignation in the event log and PGN, retaining the dialog screenshot.
It can also show a nonterminal "Mate in 3 !" search announcement after playing
a move. The connector recognizes a GAME notification with one centered OK
button, acknowledges it, then resumes legal-board observation. Two-button
decisions such as resignation and new-game confirmation do not match. Forecasts are never
recorded as results: play must still reach a verified game ending. The first
Grandmaster/Chess 19xx attempt exposed this modal after Bd7 and stayed unscored.
Actual mate also shows a one-OK notification titled GAME COMPLETED. That
notification is dismissed to expose the terminal board; its text alone never
supplies a result. The captured Qb7# frame exposed this second title.
After that acknowledgement Grandmaster asks whether to use the game for its
native player-rating calculation. The connector declines CHESS RATING and
any subsequent new-game offer, exposing and preserving the terminal board.
Project scores are recorded only in the ledger after normal board verification.

Chess 19xx's longer games exposed a separate input race at H4-F3: ink growth
from an earlier character could acknowledge a missed destination letter, then
send a rank while the game still expected a file. Its connector now verifies
occupied coordinate cells, the separator, and a blank tail. Unlike Chessmaster,
this field has no block cursor. Font-template matching was rejected after a
correctly printed final digit varied too much from the board legend's font.
Only the proven missing key is retried; the exact move is still verified from
the legal board history before any further move or result is accepted.

Chess 19xx's HTTP display can exist before VICE's keyboard window. The adapter
waits for the actual game board before its F1 reset. It currently plays Black;
underpromotion input and a White-side operation remain unverified. A queen
promotion can be requested through the ordinary coordinates, but must be
confirmed as an actual queen by the normal legal-board observer; sending the
request never supplies a result or assumes the promotion succeeded.
The Return key can also be missed after a complete coordinate. A retained full
prompt plus an advancing human clock proves it was not accepted; only that
combination permits a bounded Return retry. During search the human clock stops,
so elapsed time cannot trigger a retry that interrupts the engine.

Chessmaster 2000 changes sides with Return at its empty input cursor. This is
documented under Changing Sides in the [original manual](https://www.retrogames.cz/manualy/DOS/Chessmaster_2000_-_Manual.pdf)
and verified against the C64 release. It plays White without rotating the board
or exchanging sprite colors. The connector waits for the Black input cursor
after White's opening move, then returns to board view. Later coordinate input
uses the Black move column and BLACK TO MOVE label. Board visibility alone does
not establish input readiness. Fresh boot menus can ignore early shortcuts;
bounded retries require repeated unchanged menu observations. Capture pacing
uses `Event.wait`; engine completion always depends on the UI and legal history.
The coordinate field's block cursor can redraw before a key is accepted. This
made simple ink-count growth advance the key queue prematurely (captured with
only D visible while D5 was expected). Game-owned C64 glyph templates now verify
the entire expected prefix and its cursor. A retry requires the exact previous
prefix, preventing duplicated input when only a cursor has changed.
Glyph baselines allow one pixel of vertical phase relative to the filled cursor;
the live C2-C3 entry on the seventh input row demonstrated this GTK difference.
The solid cursor is located independently around its nominal cell because its
horizontal/vertical threshold phase can differ from the thin character strokes.
Both observed C-prefix phases have captured regression fixtures.
Thin text strokes can be gray after resampling (the eighth-row E2 prefix lost
most of its digit under a black-only threshold). Glyph detection includes those
gray strokes, while the independent cursor test still requires a solid black
block. This keeps anti-aliasing tolerance separate from key acknowledgement.
The king sprite on narrow blue squares can leave only 24.4-28.8% background
(verified Kxh2 and queenside castling). Chessmaster's profile therefore uses a
20% minimum background fraction, while other games retain the 30% default.
Sprite confidence, king counts, repeated captures and legal-history checks still
gate recognition; no position is accepted merely because this bound passes.
After the source square, the live input cursor skips a separator cell, which
can remain blank until the destination is complete. Both blank and hyphen
forms are recognized. Entering text view also uses an unchanged-board F1 retry:
the board can be visible while the prior F1 transition is still finishing.
Black-delivered checkmate writes CHECKMATE in the left move column, whose GTK
phase shifts the suffix one pixel right. The terminal marker matcher accepts
both verified column phases before returning to the final board.

Battle Chess remains in the catalog but lacks an automatic reset/play connector.
Its existing validation script has an operator reset precondition, so it cannot
be scheduled as an unattended participant yet. Unsupported games and colors
remain visible in `pending`, and incomplete schedules produce provisional point
rankings rather than a claimed rating of all catalog programs.

## Persistence and evidence

The tournament CLI configures redirected stdout/stderr as UTF-8. An uncached
Windows build exposed Docker/package log arrows that CP1252 could not encode;
without this, printing a build line aborted the run before starting a game.
The private Xvfb display uses `-noreset`: short-lived screenshot clients must
not reset the display while SDL/DOSBox is opening its connection. A fresh
Grandmaster runtime exited with "Couldn't open X11 display" while an isolated
DOSBox test succeeded; retaining the X server avoids that startup race.

`state.json` is replaced atomically after each attempt transition. A process-owned
file lock prevents concurrent writers and releases on a crash; the next run
marks abandoned running attempts failed while preserving their artifacts.
Each match has a UUID directory with a PGN, confirmed move/FEN events, final
screenshots, runtime logs and failure diagnostics. Progress PGNs are rewritten
after every confirmed move. A run manifest links attempts by `run_id`, records
engine definitions and the schedule, and distinguishes requested from completed
counts. Interrupted attempts and unsupported pairings never contribute points.
