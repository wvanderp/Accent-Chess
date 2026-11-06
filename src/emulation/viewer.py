"""Docker game control panel and optional emulator observer."""

import argparse
import base64
import io
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, simpledialog
from typing import Any

import chess
from PIL import Image, ImageTk

from .client import RuntimeClient
from .analysis import AnalysisSession, AutoPlay, validate_engine
from .control import DockerControl
from .play import PlaySession, create_connector, supports_play
from .settings import load_stockfish_path, save_stockfish_path
from games.catalog import GAMES
from recognition.runtime import FrameRecorder, RuntimeRecognizer, MODULES


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", default="http://127.0.0.1:8765")
    parser.add_argument("--game", choices=GAMES, default="grandmaster")
    parser.add_argument("--debug-frames", type=Path, help="Save recognition frames to this directory")
    parser.add_argument("--stockfish", help="Stockfish executable (overrides the saved location)")
    args = parser.parse_args()
    client = RuntimeClient(args.runtime)
    root = tk.Tk()
    root.title("Accent Chess — control panel")
    toolbar = ttk.Frame(root, padding=8)
    toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
    selected = tk.StringVar(value=args.game)
    ttk.Label(toolbar, text="Game").pack(side="left", padx=4)
    picker = ttk.Combobox(toolbar, textvariable=selected, values=list(GAMES), state="readonly", width=20)
    picker.pack(side="left", padx=4)
    recognition_enabled = tk.BooleanVar(value=True)
    debug_enabled = tk.BooleanVar(value=args.debug_frames is not None)
    configurations: Queue[tuple[str, bool, bool]] = Queue()
    commands: Queue[tuple[str, dict[str, Any]]] = Queue()
    play_state: dict[str, Any] = {}
    analysis_state: dict[str, Any] = {}
    selected_square: chess.Square | None = None

    def configure_recognition(*unused: object) -> None:
        play_state.clear()
        analysis_state.clear()
        configurations.put((selected.get(), recognition_enabled.get(), debug_enabled.get()))

    selected.trace_add("write", configure_recognition)
    ttk.Checkbutton(toolbar, text="Recognize board", variable=recognition_enabled,
                    command=configure_recognition).pack(side="left", padx=4)
    ttk.Checkbutton(toolbar, text="Save debug frames", variable=debug_enabled,
                    command=configure_recognition).pack(side="left", padx=4)
    configure_recognition()
    messages: Queue[str] = Queue()
    control = DockerControl(messages.put)
    busy = False
    stop = Event()

    def action(start: bool) -> None:
        nonlocal busy
        if busy:
            return
        if args.runtime.rstrip("/") != "http://127.0.0.1:8765":
            messages.put("Docker controls use the default local runtime; remove --runtime to enable them.")
            return
        game = selected.get()
        play_state.clear()
        analysis_state.clear()
        commands.put(("invalidate", {}))
        busy = True
        start_button.configure(state="disabled")
        stop_button.configure(state="disabled")
        new_button.configure(state="disabled")

        def work() -> None:
            try:
                if start:
                    control.start(game)
                    Thread(target=follow_logs, daemon=True).start()
                else:
                    control.stop()
            except Exception as error:
                messages.put(f"Error: {error}")
            finally:
                messages.put("::idle::")

        Thread(target=work, daemon=True).start()

    def follow_logs() -> None:
        try:
            control.logs()
        except Exception as error:
            messages.put(f"Container log: {error}")

    start_button = ttk.Button(toolbar, text="Start game", command=lambda: action(True))
    start_button.pack(side="left", padx=4)
    stop_button = ttk.Button(toolbar, text="Stop game", command=lambda: action(False))
    stop_button.pack(side="left", padx=4)

    def new_game() -> None:
        nonlocal selected_square, play_state
        selected_square = None
        play_state = {}
        analysis_state.clear()
        commands.put(("new_game", {}))

    new_button = ttk.Button(toolbar, text="New game", command=new_game)
    new_button.pack(side="left", padx=4)
    ttk.Label(toolbar, text="Closing this panel leaves the game running.").pack(side="left", padx=12)
    analysis_toolbar = ttk.Frame(root, padding=8)
    analysis_toolbar.grid(row=1, column=0, columnspan=2, sticky="ew")
    executable = tk.StringVar(value=args.stockfish or load_stockfish_path() or "stockfish")
    thinking_time = tk.StringVar(value="1.0")
    ttk.Label(analysis_toolbar, text="Stockfish").pack(side="left", padx=4)
    ttk.Entry(analysis_toolbar, textvariable=executable, width=30).pack(side="left", padx=4)

    def browse_stockfish() -> None:
        path = filedialog.askopenfilename(title="Select Stockfish executable", parent=root)
        if path:
            executable.set(path)

    ttk.Button(analysis_toolbar, text="Browse…", command=browse_stockfish).pack(side="left", padx=4)
    engine_indicator = ttk.Label(analysis_toolbar, text="Checking…", foreground="#666666")
    engine_indicator.pack(side="left", padx=4)
    engine_status = ttk.Label(root, text="Checking Stockfish…", anchor="w")
    engine_status.grid(row=6, column=0, columnspan=2, sticky="ew", padx=8)
    validation_requests: Queue[tuple[int, str]] = Queue()
    validation_results: Queue[tuple[int, str | None, str]] = Queue()
    validation_revision = 0
    validation_timer: str | None = None

    def check_executable(*unused: object) -> None:
        nonlocal validation_revision, validation_timer
        validation_revision += 1
        revision, path = validation_revision, executable.get()
        engine_indicator.configure(text="Checking…", foreground="#666666")
        engine_status.configure(text="Checking Stockfish…")
        if validation_timer is not None:
            root.after_cancel(validation_timer)
        validation_timer = root.after(400, lambda: validation_requests.put((revision, path)))

    def validate_executables() -> None:
        while not stop.is_set():
            try:
                revision, path = validation_requests.get(timeout=0.25)
            except Empty:
                continue
            # Coalesce edits made while a previous engine was starting.
            while not validation_requests.empty():
                revision, path = validation_requests.get_nowait()
            try:
                resolved, name = validate_engine(path)
                validation_results.put((revision, resolved, name))
            except Exception as error:
                validation_results.put((revision, None, str(error)))

    executable.trace_add("write", check_executable)
    check_executable()
    Thread(target=validate_executables, daemon=True).start()
    ttk.Label(analysis_toolbar, text="Seconds").pack(side="left", padx=4)
    ttk.Spinbox(analysis_toolbar, from_=0.1, to=60, increment=0.5,
                textvariable=thinking_time, width=5).pack(side="left", padx=4)

    def analyze(play_after: bool = False) -> None:
        if busy or not play_state.get("analyzable") or analysis_state.get("busy"):
            return
        if play_after and not play_state.get("ready"):
            return
        try:
            seconds = float(thinking_time.get())
        except ValueError:
            messages.put("Enter a thinking time between 0.1 and 60 seconds.")
            return
        analysis_state.update(busy=True, uci=None, message="Stockfish is analyzing…")
        commands.put(("analyze", {"fen": play_state["fen"],
                                  "executable": executable.get(), "seconds": seconds,
                                  "play_after": play_after}))

    def play_best() -> None:
        nonlocal selected_square
        if (busy or not play_state.get("ready") or not analysis_state.get("uci")
                or analysis_state.get("fen") != play_state.get("fen")):
            return
        commands.put(("move", {"uci": analysis_state["uci"], "fen": analysis_state["fen"]}))
        play_state["ready"] = False
        analysis_state.clear()
        selected_square = None

    analyze_button = ttk.Button(analysis_toolbar, text="Analyze position", command=analyze)
    analyze_button.pack(side="left", padx=4)
    autoplay_enabled = tk.BooleanVar(value=False)

    def toggle_autoplay() -> None:
        try:
            seconds = float(thinking_time.get())
            if not 0.1 <= seconds <= 60:
                raise ValueError()
        except ValueError:
            autoplay_enabled.set(False)
            messages.put("Enter a thinking time between 0.1 and 60 seconds.")
            return
        commands.put(("autoplay", {"enabled": autoplay_enabled.get(),
                                  "executable": executable.get(), "seconds": seconds}))

    auto_button = ttk.Checkbutton(analysis_toolbar, text="Autoplay", variable=autoplay_enabled,
                                 command=toggle_autoplay)
    auto_button.pack(side="left", padx=4)
    best_button = ttk.Button(analysis_toolbar, text="Play best move", command=play_best)
    best_button.pack(side="left", padx=4)
    turn_indicator = ttk.Label(analysis_toolbar, text="Turn: unknown", foreground="#666666")
    turn_indicator.pack(side="left", padx=12)
    analysis_label = ttk.Label(root, text="Wait for a confirmed turn to analyze", anchor="w")
    analysis_label.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8)
    screen_frame = tk.Frame(root, width=640, height=480)
    screen_frame.grid(row=2, column=0)
    screen_frame.grid_propagate(False)
    screen = tk.Label(screen_frame, text="Connecting to emulator…")
    screen.place(relx=0.5, rely=0.5, anchor="center")
    board_canvas = tk.Canvas(root, width=480, height=480)
    board_canvas.grid(row=2, column=1)
    status = tk.Label(root, text="No recognized position published", anchor="w")
    status.grid(row=3, column=0, columnspan=2, sticky="ew")
    progress = tk.Text(root, height=9, width=120, state="disabled", wrap="word")
    progress.grid(row=5, column=0, columnspan=2, sticky="ew")

    def input_event(action_name: str, data: dict[str, Any]) -> None:
        play_state.clear()
        analysis_state.clear()
        commands.put((action_name, data))

    def click(event: tk.Event) -> None:
        screen.focus_set()
        input_event("click", {"x": event.x, "y": event.y})

    def key(event: tk.Event) -> str:
        input_event("key", {"name": event.keysym})
        return "break"

    screen.bind("<Button-1>", click)
    screen.bind("<KeyPress>", key)

    def board_click(event: tk.Event) -> None:
        nonlocal selected_square, play_state
        if busy or not play_state.get("ready") or not play_state.get("fen"):
            return
        if not (0 <= event.x < 480 and 0 <= event.y < 480):
            return
        board = chess.Board(play_state["fen"])
        square = chess.square(event.x // 60, 7 - event.y // 60)
        piece = board.piece_at(square)
        if piece and piece.color == board.turn:
            selected_square = square
            return
        if selected_square is None:
            return
        moves = [move for move in board.legal_moves
                 if move.from_square == selected_square and move.to_square == square]
        selected_square = None
        if not moves:
            messages.put("Illegal move; select a piece and a legal destination.")
            return
        move = moves[0]
        if move.promotion:
            choice = simpledialog.askstring("Promotion", "Promote to q, r, b or n:", initialvalue="q", parent=root)
            if choice is None:
                return
            move = next((candidate for candidate in moves
                         if chess.piece_symbol(candidate.promotion or chess.QUEEN) == choice.lower()), None)
            if move is None:
                messages.put("Choose q, r, b or n for promotion.")
                return
        play_state["ready"] = False
        analysis_state.clear()
        commands.put(("move", {"uci": move.uci(), "fen": board.fen()}))

    board_canvas.bind("<Button-1>", board_click)
    updates: Queue[dict[str, Any] | str] = Queue(maxsize=1)

    def fetch() -> None:
        recognizer: RuntimeRecognizer | None = None
        configuration: tuple[str, bool, bool] | None = None
        session: PlaySession | None = None
        analysis = AnalysisSession()
        autoplay = AutoPlay()
        while not stop.is_set():
            try:
                # GAME_ID is supplied by the container supervisor, so attachment
                # follows the running emulator rather than the launch selection.
                snapshot = client.snapshot()
                latest = configuration
                while not configurations.empty():
                    latest = configurations.get_nowait()
                active_game = snapshot.get("game")
                if latest is not None and active_game in GAMES:
                    latest = (active_game, latest[1], latest[2])
                if latest != configuration:
                    reset_session = configuration is None or latest is None or latest[:2] != configuration[:2]
                    configuration = latest
                    assert configuration is not None
                    game, enabled, debug = configuration
                    recorder = FrameRecorder(args.debug_frames or Path("debug-frames"), game) if enabled and debug else None
                    recognizer = RuntimeRecognizer(game, client, recorder) if enabled and game in MODULES else None
                    if reset_session:
                        session = None
                        analysis.invalidate()
                    if enabled and reset_session:
                        try:
                            session = PlaySession(create_connector(game, client))
                        except ValueError as error:
                            messages.put(str(error))
                    if recorder:
                        messages.put(f"Saving up to {recorder.limit} changed frames to {recorder.directory}")
                while not commands.empty():
                    command, data = commands.get_nowait()
                    try:
                        if command == "autoplay":
                            autoplay.configure(data["enabled"], analysis,
                                               data["executable"], data["seconds"])
                        elif command == "new_game":
                            analysis.invalidate()
                            if session is None:
                                raise ValueError("Enable recognition and select a supported game to play.")
                            active = client.snapshot().get("game")
                            if active != game:
                                raise ValueError("Start the selected game to use the current runtime and input protocol.")
                            session.new_game()
                            assert recognizer is not None
                            recognizer.previous = None
                        elif command == "move":
                            if session is None:
                                raise ValueError("No active play session")
                            if session.board is None or session.board.fen() != data["fen"]:
                                raise ValueError("The position changed; select a move again")
                            analysis.invalidate()
                            session.submit(data["uci"])
                        elif command == "analyze":
                            if session is None or not session.position_confirmed or session.board is None:
                                raise ValueError("Wait for a confirmed turn before analyzing")
                            if session.board.fen() != data["fen"]:
                                raise ValueError("The position changed; analyze again")
                            analysis.synchronize(session.board)
                            analysis.request(session.board, data["executable"], data["seconds"],
                                             play_after=data.get("play_after", False))
                        else:
                            analysis.invalidate()
                            if session:
                                session.invalidate("Manual input or lifecycle change; press New game to resynchronize")
                            if command != "invalidate":
                                client.send(command, data)
                    except Exception as error:
                        messages.put(f"Game action failed: {error}")
                update: dict[str, Any] | str = client.snapshot()
                if update.get("game") != snapshot.get("game"):
                    # A container replacement during input/capture needs a fresh
                    # connector before interpreting any of its pixels.
                    continue
                if recognizer:
                    update["recognition_status"] = recognizer.process(update)
                if session and recognizer:
                    with Image.open(io.BytesIO(base64.b64decode(update["png"]))) as frame:
                        session.observe(frame, recognizer.confirmed_placement)
                    update["play"] = session.state()
                analysis.synchronize(session.board if session and session.position_confirmed else None)
                if session:
                    automatic_move = autoplay.advance(analysis, session.board, session.ready)
                    if automatic_move is not None:
                        analysis.invalidate()
                        session.submit(automatic_move)
                        update["play"] = session.state()
                update["analysis"] = analysis.state()
            except Exception as error:
                analysis.invalidate()
                if session:
                    session.invalidate("Disconnected; press New game after reconnecting")
                update = f"Disconnected: {error}"
            if updates.empty():
                updates.put_nowait(update)
            # Refresh pacing only; this is never used to decide move completion.
            stop.wait(0.25)

    photo: ImageTk.PhotoImage | None = None
    detected_game: str | None = None

    def redraw() -> None:
        nonlocal photo, busy, play_state, analysis_state, selected_square, detected_game
        while not validation_results.empty():
            revision, resolved, detail = validation_results.get_nowait()
            if revision != validation_revision:
                continue
            if resolved is None:
                engine_indicator.configure(text="✗", foreground="#b3261e")
                engine_status.configure(text=f"Stockfish unavailable: {detail}")
            else:
                engine_indicator.configure(text="✓", foreground="#188038")
                try:
                    save_stockfish_path(resolved)
                    engine_status.configure(text=f"{detail} · location saved")
                except OSError as error:
                    engine_status.configure(text=f"{detail} · could not save location: {error}")
        new_button.configure(state="normal" if not busy and supports_play(selected.get())
                             and recognition_enabled.get() else "disabled")
        for _ in range(100):
            try:
                message = messages.get_nowait()
            except Empty:
                break
            if message == "::idle::":
                busy = False
                start_button.configure(state="normal")
                stop_button.configure(state="normal")
            else:
                progress.configure(state="normal")
                progress.insert("end", message + "\n")
                if int(progress.index("end-1c").split(".")[0]) > 1000:
                    progress.delete("1.0", "100.0")
                progress.see("end")
                progress.configure(state="disabled")
        try:
            update = updates.get_nowait()
            if isinstance(update, str):
                play_state = {}
                analysis_state = {}
                selected_square = None
                status.configure(text=update)
            else:
                active_game = update.get("game")
                if active_game in GAMES and active_game != detected_game:
                    detected_game = active_game
                    if selected.get() != active_game:
                        selected.set(active_game)
                    messages.put(f"Detected running Docker game: {active_game}")
                play_state = update.get("play", {})
                analysis_state = update.get("analysis", {})
                if not play_state.get("ready"):
                    selected_square = None
                image = Image.open(io.BytesIO(base64.b64decode(update["png"])))
                image.thumbnail((640, 480))
                photo = ImageTk.PhotoImage(image)
                screen.configure(image=photo, width=640, height=480)
                board_canvas.delete("all")
                observation = update["board"]
                board = chess.Board(observation["fen"]) if observation else chess.Board(None)
                if play_state.get("fen"):
                    board = chess.Board(play_state["fen"])
                for rank in range(8):
                    for file in range(8):
                        x, y = file * 60, (7 - rank) * 60
                        board_canvas.create_rectangle(x, y, x + 60, y + 60,
                            fill="#f4d35e" if chess.square(file, rank) == selected_square else
                                 ("#eadcc2" if (file + rank) % 2 else "#81947c"), outline="")
                        piece = board.piece_at(chess.square(file, rank))
                        if piece:
                            board_canvas.create_text(x + 30, y + 30, text=piece.unicode_symbol(),
                                                     font=("Segoe UI Symbol", 38))
                if analysis_state.get("uci") and play_state.get("ready"):
                    best = chess.Move.from_uci(analysis_state["uci"])
                    for square in (best.from_square, best.to_square):
                        x, y = chess.square_file(square) * 60, (7 - chess.square_rank(square)) * 60
                        board_canvas.create_rectangle(x + 3, y + 3, x + 57, y + 57,
                                                      outline="#2166d1", width=4)
                message = "No recognized position published"
                if observation:
                    stale = observation["frame_id"] != update["frame_id"]
                    message = f"Board from frame {observation['frame_id']}" + (" (older than image)" if stale else "")
                    if observation.get("kind") == "placement":
                        message += " · piece placement only"
                if "recognition_status" in update:
                    message += " · " + update["recognition_status"]
                if play_state:
                    message = str(play_state["message"]) + " · " + message
                status.configure(text=f"Image frame {update['frame_id']} · {message}")
        except Empty:
            pass
        ready = not busy and bool(play_state.get("ready")) and recognition_enabled.get()
        turn = play_state.get("turn")
        turn_indicator.configure(text=f"Turn: {turn.capitalize()}" if turn else "Turn: unknown",
                                 foreground="#188038" if turn else "#666666")
        analyzable = not busy and bool(play_state.get("analyzable")) and recognition_enabled.get()
        analyze_button.configure(state="normal" if analyzable and not analysis_state.get("busy") else "disabled")
        auto_button.configure(state="normal")
        best_button.configure(state="normal" if ready and analysis_state.get("uci")
                              and analysis_state.get("fen") == play_state.get("fen") else "disabled")
        analysis_label.configure(text=analysis_state.get("message", "Wait for a confirmed turn to analyze"))
        root.after(100, redraw)

    def close() -> None:
        stop.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    Thread(target=fetch, daemon=True).start()
    redraw()
    root.mainloop()


if __name__ == "__main__":
    main()
