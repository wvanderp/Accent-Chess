# Local emulation investigation and first implementation

## Decision and scope

Separate three responsibilities: emulator runtime (pixels/input), game connector (recognition, menu navigation, move validation), and optional observer (presentation).
Keep `GameConnector` as the UCI boundary. Docker packages an emulator; Docker itself does not emulate DOS, consoles, or Windows. Never require an observer to run UCI.

This change implements DOS/C64 runtimes and a native control panel. It does **not** yet replace the Archive connectors in `main.py`, recognize a local game, or claim that all games in the README work. Per-game Python setup scripts download media inside Docker. Manual extracted DOS media remains supported as an alternative.

## Options investigated

| Target                                                   | Runtime                                        | Installation and integration tradeoff                                                                                                                                                       |
| -------------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DOS games                                                | DOSBox in Linux container                      | One container backend on host; emulator, X11 and Python remain inside image. Good first milestone.                                                                                          |
| DOS without Docker                                       | Local js-dos/WASM worker                       | Browser assets plus a game bundle; direct frame callbacks and input API. Can run in headless Chromium independently of observer. Must pin/self-host assets and validate game compatibility. |
| DOS portable native                                      | DOSBox Staging                                 | Extractable Windows distribution; avoids Docker/WSL. Needs a platform-specific capture/input adapter or emulator integration.                                                               |
| Dedicated chess computers, C64, other historical systems | MAME                                           | System-specific ROM/media and Lua integration; verify each machine driver and input layout individually.                                                                                    |
| Windows-era PC games                                     | QEMU (or investigate 86Box)                    | Guest OS, installation, disk snapshots and significantly more resources. Use a separate backend, not DOS-specific assumptions.                                                              |
| Game Boy/consoles                                        | System-specific emulator, potentially libretro | Additional adapter and per-game validation required; not supported by this prototype.                                                                                                       |

Primary sources (consulted 2026-11-04):

- [Docker Windows setup](https://docs.docker.com/desktop/setup/install/windows-install/): a supported backend such as WSL 2 is still required. Docker reduces per-emulator dependencies, not the host's initial setup cost.
- [js-dos command interface](https://js-dos.com/command-interface.html): frame callbacks, screenshots, keyboard/mouse and runtime lifecycle operations. This is the strongest alternative if minimizing installations outweighs native emulator preference.
- [js-dos bundles](https://js-dos.com/jsdos-bundle.html): ZIP bundles contain program files and DOSBox configuration.
- [DOSBox Staging captures](https://www.dosbox-staging.org/0.83/manual/using-dosbox-staging/capture/): raw captures are possible, but screenshot hotkeys are not a continuous transport API.
- [MAME Lua](https://docs.mamedev.org/luascript/index.html): machine access and frame callbacks support an eventual dedicated adapter.
- [QEMU architecture](https://www.qemu.org/docs/master/system/introduction.html): full guest machine emulation and machine management interfaces.

The container currently uses Debian's classic DOSBox package for a small,
distribution-managed prototype. Staging is an upgrade candidate; no unsupported
assumption is made that either exposes a remote automation API. Xvfb supplies an
isolated 640x480 display, Pillow captures it, and xdotool supplies input. These are
virtual-display pixels, not raw VGA framebuffer pixels. Scaling is fixed initially;
recognition calibration must record this coordinate space. A future native frame
adapter can replace X11 behind the same transport boundary.

## Run

### Control panel (recommended)

```powershell
python -m emulation.viewer
```

Choose `grandmaster` or `chess19xx` and press **Start game**. The panel builds the
image, starts a managed Docker container, and follows its setup log. Python setup
scripts inside each game's `src/games/<game>/setup.py` download and verify game media inside that
container, then launch DOSBox or VICE. Once capture is available, the panel connects
automatically and shows boot and game screens. Click the image to focus it; keyboard
keys and mouse clicks are forwarded. Stop game stops the managed container. Starting
a new game replaces the previous managed session; its disposable saves are lost.
Only one managed session runs at a time on port 8765. Closing the panel leaves it
running; reopening attaches automatically. Docker CLI and a running Linux backend
are required. Build/download operations run in background threads, keeping the UI
responsive. Downloads that are unavailable or require Archive authentication fail
visibly in the log; the setup does not bypass access restrictions.

Grandmaster uses the Archive-provided `grandchs/CHESS.BAT` and correct working
directory. Chess 19xx's Archive metadata identifies a C64 D64, not DOS software;
its setup uses VICE and upstream VICE C64 ROM data. Game media SHA-1 hashes are
checked against the Archive metadata observed during investigation. ROM files
currently follow the upstream VICE main branch and are not pinned.

Each game's setup and legacy connector live together under `src/games/`:
`Grandmaster_Chess/setup.py` and `Chess_19xx/setup.py`. `games/catalog.py` registers
them without importing the legacy Playwright/classifier stack. Shared media I/O
belongs to `emulation/media.py`; Docker lifecycle belongs to `emulation/control.py`.
Add a game by adding its setup module and catalog entry, keeping its configuration
out of the runtime and panel. Debian VICE uses `+drive8truedrive` rather than the
older `+truedrive` flag. Native C64 pixel size avoids clipping on the private
640x480 display; CRT filtering is disabled for future recognition calibration.

Verified against live media: both container setups downloaded successfully,
Grandmaster reached its title screen, and VICE autostart reached Chess 19xx's board.
Capture was visually inspected for both. Transport/extraction tests pass. Automatic
chess recognition and a full played game have not been validated in these runtimes.

This starts the original programs; in-game menu navigation is manual through the
image. Automatic recognition/UCI migration remains a separate task. Setup scripts
download and configure media, without guessing when a chess engine has moved.

### Manual local-media mode

From PowerShell in the repository, with Docker Desktop's Linux backend available:

```powershell
$env:GAME_DIRECTORY = 'C:\Games\MyDosChess'
$env:GAME_EXECUTABLE = 'CHESS.EXE'
docker compose up --build
```

The runtime starts without a visualizer. Supplied media is mounted read-only and copied into disposable `/tmp/game` so DOS games can save settings. Session changes are lost on restart; persistent saves and disk images need a later media abstraction. The prototype disables sound and uses fixed 10,000 DOSBox cycles; tune per game.

For the optional viewer, use the project's global Python dependencies (no venv):

```powershell
pip install -r requirements.txt
python -m emulation.viewer
```

Tkinter ships with standard Windows Python; Linux hosts may need python3-tk.
The requirements install registers the local `emulation` package through an
editable install, so no `PYTHONPATH` setting is required. For an existing checkout,
run `python -m pip install -e .` once using the Python that launches the viewer.
Closing or disconnecting the panel leaves the runtime alive.
The left panel shows the virtual display, the right panel shows the latest published
recognized FEN. Until a connector publishes a position, the board is empty and labeled
unrecognized. No starting position or demonstration board is presented as recognition.
Recognition overlays are intentionally deferred.

## Transport and connector migration

`RuntimeClient.snapshot()` returns version, frame ID, base64 PNG and optional board observation. IDs increase when captured image bytes change (not on every emulated frame). `send('key', {'name': 'Return'})` and
`send('click', {'x': 320, 'y': 240})` control the isolated display. For recognition,
call `send('board', {'fen': board.fen(), 'frame_id': snapshot['frame_id']})`.
Old publications are rejected; retained observations carry their original ID and
are visibly marked older when the image changes. Multiple readers are supported;
one connector should own input and recognition. Capture and input are serialized.

This is a loopback-only development API, not a remotely authenticated service.
Compose publishes only on 127.0.0.1. Do not expose its input endpoints publicly.
There is no CORS support and browser-origin writes are rejected.

Repository findings affecting the next migration:

1. Both game classes inherit `ArchiveOrgConnector` and use `_page`, canvas locators, and mouse coordinates directly. Simply changing the URL cannot migrate them.
2. Extract classifiers into game-owned image readers accepting PIL images. Keep sample data but recalibrate crops/scaling against actual local media.
3. Add runtime-backed connectors that receive a `RuntimeClient`, with game-specific
   boot/menu state machines and explicit capability declarations for position setup.
4. Implement move waits from fresh visual observations: UI ready/thinking markers,
   stable board observations, and a unique legal successor of the expected board.
   Use deadlines and cancellation; elapsed time alone never proves a completed move.
   Viewer refresh pacing is unrelated to engine synchronization.
5. Existing move-wait paths contain sleeps and fixed Playwright delays. Do not copy
   these into new connectors. The synchronous UCI `go` path also needs cancellation
   work so `stop` can interrupt recognition while it waits.
6. Validate a complete local game with supplied media before changing the default
   launcher or deleting the Archive implementation. Confirm startup, both colors,
   special moves, new game, cancellation, and operation with zero viewers.

Container package versions follow Debian bookworm repositories; image digest and
package locks should be recorded once a game-compatible baseline is validated.

Runtime smoke check (no game files required):

```powershell
docker run --rm --init --entrypoint xvfb-run accent-chess-runtime -a -s '-screen 0 640x480x24 -nolisten tcp' python /app/docker/smoke.py
```

Use `--init` for direct Docker runs as Compose does: Xvfb's startup wrapper needs
normal signal handling. Investigation also found that `xdotool mousemove --sync`
can wait indefinitely if the pointer already occupies the target; the adapter
therefore uses ordered mouse commands without that flag.
