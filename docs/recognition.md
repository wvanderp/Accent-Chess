# Local board recognition and frame debugging

Run `python -m pip install -r requirements.txt` globally, then
`python -m emulation.viewer`. Choose the game matching the running emulator.
**Recognize board** is enabled by default; **Save debug frames** is opt-in.
Navigate startup screens manually. Supported boards use the default theme, 2D
layout and white at the bottom; moving/resizing VICE's window changes calibration.
The UCI launcher still uses legacy Archive connectors: this change migrates the
recognition path, not menu automation or UCI input/cancellation.

## Headless and offline use

With the runtime running, no viewer is required:

```powershell
python -m recognition --game grandmaster --debug-frames debug-frames
python -m recognition --game chess19xx --once --debug-frames debug-frames
python -m recognition --game grandmaster --image tests/fixtures/recognition/grandmaster-e4-e5.png
```

Use `--runtime URL` for a different runtime. `--once` captures twice to confirm
placement. `--image` reads a saved full-display PNG and prints piece placement,
without connecting to an emulator. Ctrl+C stops the headless observer.

Each debug session gets a unique UTC directory. Every changed captured frame
produces a source PNG, `-board.png`, `-overlay.png`, and JSON with frame ID,
source hash, capture time, board region, recognized placement, square labels,
shape distances and background coverage. Rejected frames include the source,
crop, error overlay and rejection reason. JSON has no placement on rejection.
Frames are recorded only when their image bytes change; identical polls do not
fill the disk. A session stores at most 500 frames (three PNGs plus JSON each);
headless `--max-debug-frames N` changes the limit. Disable/re-enable recording
to start a new session in the panel. Recording never changes training data.

## Boundaries and evidence

`recognition/board.py` accepts PIL images and returns piece placement plus
diagnostics. Each game's `recognition.py` owns the display region, palette and
piece-color rules. Its `recognition.png` is a native reference frame with a
known starting position, used to label shape templates. Actual observations
start with an empty board; they are never replaced by a starting-position guess.
Templates remove square background and fill enclosed holes so outlined and solid
sprites can share shapes. Unknown shapes, absent backgrounds, wrong display
dimensions and missing/duplicate kings are rejected. The reader supports the
calibrated sprites, not arbitrary themes or 3D boards.

`recognition/runtime.py` handles capture decoding, repeated-placement confirmation,
debug recording and frame-linked publication. Only two consecutive agreeing
captures publish a placement. Sampling intervals pace capture; they never prove
that an engine has completed a move. Changing frames can legitimately retain
the same placement (timers/cursor). The server rejects publication if another
observer advanced the captured frame meanwhile; the next capture is tried.

The transport accepts `{"placement": "...", "frame_id": N}` and labels the
result `kind: placement`. Its FEN field exists for existing board renderers;
turn, castling, en-passant and counters are unknown. Those must come from trusted
game history before validating moves in a future runtime UCI connector. Existing
full-FEN publications remain supported. Capture/input stay in `emulation`, while
piece reading runs on the host. A future memory/monitor reader can publish through
the same transport without requiring the image reader or an open viewer.

## Investigation findings (2026-11-04)

* DOSBox's 640x480 Grandmaster default board occupies `(16, 24, 472, 440)`
  (x, y, width, height), with 59x55 squares. The old browser crop started at y=60
  and clipped the board. Background RGB values are `(255,255,255)` and
  `(81,85,93)`; black pieces contain red/brown pixels, white pieces are gray.
* VICE's default local C64 board occupies `(180,138,242,193)` inside the private
  display. GTK resamples fractional square boundaries even with CRT filtering
  disabled, so crop boundaries must be rounded individually. Native square
  colors are gray `(213,213,213)` and blue `(62,81,240)`. Black piece interiors
  stay blue and white interiors gray across outlined/solid variations. A median
  patch in the common sprite base distinguishes colors despite resampling.
* Historical browser training samples include scanlines, resizing, duplicate
  examples and differing square palettes. Local recognition uses native
  reference shapes without importing Playwright or training sklearn models.
* Live captures of both starting boards were inspected. Grandmaster accepted
  keyboard `e2e4`, then replied `e7e5`; the captured changed board was recognized
  correctly and saved as a regression fixture. Rapid input sequences can lose
  keys in vintage programs. A second live fixture verifies `Nf3 ...Nc6` across
  opposite square colors. Future input automation needs UI acknowledgments.
  A full local game, special moves, changed themes/orientation, and moved C64
  positions are not yet validated.

Run `python -m pytest -q` for native reference recognition, changed-square
recognition, rejected frames, debug limits, repeated-capture confirmation and
real HTTP publication/stale-frame regression checks.
