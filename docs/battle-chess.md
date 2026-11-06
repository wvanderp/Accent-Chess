# Battle Chess (1989): Atari ST investigation

Status: Hatari runtime, 2D recognition and two completed live validation games.
The viewer play connector and automatic startup/reset remain unfinished.

The requested release is https://archive.org/details/Battle_Chess_1989_Interplay_cr_MCA_m_EMT.
Archive.org's metadata identifies `pce-atarist-color`, extension `st`, and
startup media `Battle_Chess_1989_Interplay_cr_MCA_m_EMT.st`. This is an Atari ST
release, not the DOS release. The disk is 737280 bytes with SHA-1
`b8260f86f75ce9419d28c77c39b5886852e688f6` (metadata checked 2026-11-05).

The container now installs Hatari alongside DOSBox and VICE. Select
`battlechess` in the viewer to launch it. Setup downloads checksum-verified
EmuTOS 1.3 (US 192K firmware) and the disk, then uses Hatari's `--auto
A:\CHESS.PRG`. Live testing reached the title, 3D board, and 2D board under
EmuTOS. Space dismisses the crack intro; a left click dismisses the title.
Hold the right mouse button, move to Settings, then release over 2D Board.
The 2D reader recognizes the starting position using red/blue sprite masks.

Important input finding: Hatari supplies relative mouse movement to the ST.
Moving the host pointer to a board coordinate does not reliably place the
game cursor there, especially after crossing the window edge. Live move
submission initially failed with the existing absolute-click adapter. Moving
the host pointer to the bottom-right interior of the Hatari window and then
to its top-left interior re-aligns guest coordinates in live testing. Hatari's
window occupies (0,40)-(640,440) in the 640x480 Xvfb display. Parking outside
that window loses alignment; do not use the viewer's usual (620,460) parking
coordinate without recalibrating afterwards. Keep the validation runner's
parking point at (600,420), inside the window.
The runtime now exposes held left/right buttons via `/v1/mouse-button` so
menus can stay open across observed frames. Short X11 clicks can be missed by
the guest mouse scanner. More importantly, moving the host pointer is not
acknowledgement that the guest cursor has reached the target. Sending the
destination press immediately can click the source again. The validated runner
locates the peach hand pixels in each captured frame, waits for the guest cursor,
checks the selected-square border, and waits for the source sprite to disappear.
Replies must match a unique legal successor, confirmed over two captures.

Hatari's debugger was also tested using its local command FIFO and `savebin`.
RAM dumps worked, but a board-memory layout was not established. The completed
games use observed frames; no game memory was patched to enter moves or change
the result. The FIFO can also configure fast-forward during investigation.

## Completed games (2026-11-05)

Stockfish played White through the runtime HTTP input boundary against the
original Battle Chess engine as Black. Both games started from the normal
initial position and ended with the game's explicit **Check and mate...Game
over.** dialog:

- [First game PGN](evidence/battlechess/game.pgn): 23. Qf7#, 1-0.
  [Final dialog](evidence/battlechess/checkmate.png).
- [Reproduction PGN](evidence/battlechess/reproduction-game.pgn): 19. Qh8#, 1-0.
  [Final dialog](evidence/battlechess/reproduction-checkmate.png).

The reproduction uses the checked-in runner below, including its terminal-dialog
handling. The first investigation runner timed out after the final mating move
because the busy cursor replaced the hand; that failure did not undo the mate.
The final move was recorded against the visible mate dialog and legal position.

Both games exercised ordinary moves, captures, checks, and kingside castling by
both colors. Native frames after captures and castling are regression fixtures.
The mate dialog obscures the middle board: the reader deliberately rejects it,
rather than publishing a guessed placement. A matching mate dialog is accepted
only when the submitted legal move independently produces checkmate.
**Return on that dialog immediately resets the game**; save evidence first.

## Reproduce a validation game

Build/start Battle Chess with the viewer. Dismiss the intros, choose Settings >
2D Board, and retain Human Red / Atari Blue. Start a fresh game. If the pointer
was moved outside Hatari's window, first move to (639,439), then (0,40), allowing
the guest cursor to reach each corner; this clamps and re-aligns the relative
cursor. The runner verifies the guest hand before each board click and fails on
unacknowledged input. Use a new output directory for each run:

```powershell
$env:PYTHONPATH = "src"
python scripts/validate_battlechess.py --stockfish C:/bins/stockfish/stockfish.exe --output debug-frames/battlechess-validation
```

Use `--runtime http://127.0.0.1:8766` for the investigation container. The runner
does not start/reset the emulator and does not claim general viewer-play support.
It saves PGN, tracked moves, screenshots, and the checkmate dialog. There are no
sleep-based engine waits. Promotion input is explicitly rejected pending live
validation; en passant, queenside castling, stalemate, other draws and playing as
Black remain unverified. These completed games do not establish those features.
