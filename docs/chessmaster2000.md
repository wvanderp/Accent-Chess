# The Chessmaster 2000 (C64)

Run `python -m emulation.viewer --game chessmaster2000`, press **Start game**,
then **New game**. The local viewer, recognition CLI, Stockfish advice and
tournament catalog share this registration. The legacy Archive browser UCI
launcher in `main.py` remains separate and does not expose this connector.

## Runtime and media

The requested [Archive item](https://archive.org/details/Chessmaster_2000_The_1986_Software_Toolworks_Side_A)
contains both D64 sides. Setup downloads both and checks their SHA-1 hashes
against the Archive metadata. Side A boots. Normal chess play does not require
switching sides; Side B is retained in the disposable session for the original
disk features. The connector does not automate the game's disk library menus.

The custom loader stalls at PLEASE WAIT with virtual-drive-only emulation.
Use a 1541 with true drive emulation, its DOS ROM and autostart drive handling.
`emulation/c64.py` owns these options and the checksum-verified upstream VICE
ROM downloads. Chess 19xx uses the same helper with its faster virtual-drive
configuration. The production runtime does not expose a VICE monitor port.

## Verified controls and synchronization

Keep the original color 2D display, white at the bottom, and default
YOU vs. CHESSMASTER player mode. Reference coordinates describe the private
640×480 Xvfb display, with VICE CRT filtering disabled.

- F1 switches text and board views. In text view Ctrl+A opens PLAYING,
  Ctrl+B requests NEW GAME, and Y confirms. Observe the actual confirmation
  disappearing and the cleared move list before accepting a reset.
- Coordinate input is `e2e4`, without a hyphen or Return. The game inserts the
  hyphen into its completed move log. A promotion waits for a fifth letter:
  `a7a8q`, `a7a8r`, `a7a8b`, or `a7a8n`.
- Enter moves in text view so every character can be acknowledged by visible
  prompt growth. A board reply can appear before keyboard input is ready.
  The next blank move entry's block cursor establishes readiness. WHITE TO MOVE
  alone is insufficient: it can remain visible during search.
- F1 can leave the text view with CHOICES cleared at normal C64 speed. Confirm
  the board's rank/file labels; bounded retries require an unchanged ready text
  view, never a guessed engine duration.
- CHECKMATE and STALEMATE share the MATE suffix. Search both move columns and
  all list rows, since the history scrolls. Then show the final board and let
  PlaySession determine the result from confirmed legal chess positions.

Electrical key duration is 200ms for the C64 scanner. There are no sleeps for
engine completion. Frame-driven states, finite deadlines, observed text input
and unique legal board successors establish progress. The connector allows
240 seconds for boot/reset and 180 seconds for move input plus the reply.

## Recognition and memory findings

The board region is `(202, 146, 243, 178)`. Human pieces have gold interiors;
computer pieces have blue interiors, with common black line art. Filled
silhouettes confused moved rooks and bishops after GTK resampling. The profile
therefore supplies a game-specific shape reader that retains internal black
ink. Gold-pixel counts determine color. Existing games retain their original
silhouette extractor. Flashing selection frames can be rejected; subsequent
readable captures supply the actual position.

Investigation also located a useful alternative to pixels. In this media,
the initial board appears at `$C000` and `$C400`, using a 16-byte rank stride
and the first eight bytes of each rank. Rank 8 comes first. Empty is `$00`;
white pieces use `$10` and black `$20`, plus pawn=0, king=1, knight=2, rook=3,
bishop=4 and queen=5. An initial-position copy also appears at `$7A8C` with
an eight-byte stride. These are **not interchangeable live-state contracts**:
the setup editor clears/rebuilds arrays, and the other eight bytes in a rank
contain additional engine data. A future memory adapter needs lifecycle and
turn-field validation before replacing the supported frame interface.

## Validation

Live investigation used the exact Archive media in Debian VICE, including a
fresh container downloading its own media through the production setup.
Checks covered boot, reset from an active game, acknowledged coordinate entry,
engine replies, captures, moved kings/rooks/bishops, engine queenside castling,
human kingside castling, and confirmed checkmates on moves 24 and 23. The
final move-23 run reached `Game over: 1-0` through PlaySession. Queen promotion was checked through the
original position editor (white king e1, pawn a7, black king h8); the game
accepted `a7a8q` and replied `h8g7`. Knight promotion was also verified through
the connector: `a7a8n` produced the confirmed knight on a8 and PlaySession
reported `Game over: 1/2-1/2` for insufficient material. Such terminal human
moves use the submitted position context and do not wait for an engine reply.

Captured frames and tests cover native positions, the resampled rook/bishop
distinction, checkmate, reset/menu gates, stalled input, view recovery,
promotion character retention, verified media setup and shortcut validation.
Automated position loading, playing as Black, alternative display settings,
and the legacy browser UCI launcher are outside this local connector's scope.
