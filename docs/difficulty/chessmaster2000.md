# The Chessmaster 2000 (Commodore 64)

The checksum-verified two-sided disk registered in `setup.py` exposes native
PLAY LEVEL presets **00 through 19**. Levels **00 through 18**, each with
Coffeehouse OFF and ON, produce **38 separate ranking engines**.
**19 is indefinite analysis** and requires a forced move or a
checking sequence, so it is excluded from automatic games.

These are the program's own presets, rather than a host-imposed search cutoff.
The [original C64 reference guide](https://uta.pokefinder.org/Ultimate_Tape_Archive/Chessmaster_2000%2C_The_%281986_Electronic_Arts%29_%5B2810%5D/Extras/Instructions.pdf)
describes the approximate thinking allowances below. They are historical
hardware estimates, not promises about emulated wall-clock time.

| Level | Native allowance |
| --- | --- |
| 00 | 60 moves / 5 minutes |
| 01 | 40 moves / 5 minutes |
| 02 | 60 moves / 10 minutes |
| 03 | 60 moves / 30 minutes |
| 04 | 60 moves / 45 minutes |
| 05 | 60 moves / 60 minutes |
| 06 | 30 moves / 45 minutes |
| 07 | 30 moves / 60 minutes |
| 08 | 40 moves / 90 minutes |
| 09 | 40 moves / 100 minutes |
| 10 | 40 moves / 120 minutes |
| 11 | 40 moves / 150 minutes |
| 12-14 | Three times the allowance of 08-10, respectively |
| 15-18 | Ten times the allowance of 08-11, respectively |

The guide describes **Coffeehouse** as introducing less consistent moves, and
**Easy Mode** as disabling thinking on the opponent's turn. Coffeehouse ON is
therefore a distinct weakened preset for every finite level; use the profile
`coffeehouse-level-09`, for example. Rankings keep Easy Mode OFF to allow
pondering. The disk UI calls level 00 with Easy Mode ON **NEWCOMER ON**; at higher
levels it says **EASY MODE ON**. This is the same Ctrl+E setting, not an
independent personality. Different platform releases have different options;
do not import Macintosh newcomer personalities or its 12-level table here.

## Setting and verification

After reset and before selecting the computer's side:

```powershell
python -m emulation.difficulty set --game chessmaster2000 --profile level-09 --url http://127.0.0.1:8765
```

The game-owned setter opens text view with F1 and PLAYING with Ctrl+A. It reads
the current flags, selects the requested Coffeehouse setting and Easy Mode OFF, opens
PLAY LEVEL with Ctrl+D, and types exactly two digits. **Do not press Return**:
the second digit commits the setting; Return at the move prompt starts a
computer move. The setter reads back the complete level and both flags before
returning to board view. Unknown menus/values and missed keys fail closed with
a bounded navigation error. Navigation deadlines never force a chess move.

The reference atlas contains the exact inverted digit cells from all 19 finite
levels, captured with the production 640x480 C64 display. Full menu references
are deliberately small crops. This avoids ambiguous OCR of resampled 6/8/9
glyphs, and does not require a VICE monitor or unverified memory offsets.

## Investigation evidence (2026-11-06)

Every finite preset was selected on the actual media and captured, then all
19 were selected again through `set_difficulty`, including entering from board
view and confirming its return. Captured examples are [00](evidence/chessmaster2000/level-00.png),
[09](evidence/chessmaster2000/level-09.png), and [18](evidence/chessmaster2000/level-18.png).
All 19 Coffeehouse ON profiles were subsequently selected through the setter.
Coffeehouse ON and Easy Mode ON were also changed back to OFF and verified.
High-level games were not played to completion; the verified claim here is
native selection/readback, not measured strength or thinking duration.
