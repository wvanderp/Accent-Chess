# Chess 19xx: C64 strength presets

Investigated the exact checksum-verified disk selected by `setup.py`, under
VICE 3.7.1, on 2026-11-06. This Swedish program displays **SPEL STYRKA**
(playing strength) in the right panel. Its native presets are **1–9**.
Each preset is a separate engine identity: `chess19xx:level-1` through
`chess19xx:level-9` (use the central CLI's listed identity spelling).

Send the native `>` control to increase strength and `<` to decrease it.
The X11 keysyms `greater` and `less` were verified live. A numeric key enters
the move field and does **not** set strength. F2 requests a computer move;
F4 changes sides/orientation. Neither belongs in a difficulty setter.

The complete 1–9 range was captured live. The setter was then verified from
9 down to 1 and back to 9, acknowledging every displayed strength digit.
`difficulty-levels.png` contains nine small native digit crops in ascending
order. `difficulty-label.png` supplies an independent static SPELSTYRKA label
guard, so a coincidental digit on another screen cannot acknowledge strength.
The readback ignores clocks, board placement, move prompts, and colors
outside these regions. Missed keyboard scans are retried only while the old
strength remains visible; reaching the requested digit is required for success.

Additional investigation used a disposable VICE remote-monitor RAM dump,
without changing game memory. The native dispatcher at `$2961` maps PETSCII
`$3e` (`>`) to `$29f2` and `$3c` (`<`) to `$29fc`. These routines update the
strength byte at `$27`, reject values outside 1–9, and write its digit to
screen RAM `$0604`. Search code at `$1adf` consults this byte and lookup tables
at `$28b1`/`$28bb`; consequently these are genuine shipped search presets.
An exact advertised seconds/depth mapping has not been established and should
not be invented. No custom thinking-time entry was found in this release.

The runtime must already show an idle game board. The setter preserves the
current position and does not force a move or reset the program. Tournament
setup should apply it after reset. UI setup has a bounded acknowledgement
timeout; that timeout is unrelated to engine thinking time during play.

Source media: [Archive.org Chess 19xx disk](https://archive.org/download/Chess_19xx_-/Chess_19xx_-.d64),
SHA-1 `64f581bf98bcdf31372c6006016f55f9e1bc81f0`.
