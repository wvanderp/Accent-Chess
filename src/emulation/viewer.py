"""Docker game control panel and optional emulator observer."""

import argparse
import base64
import io
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
import tkinter as tk
from tkinter import ttk
from tkinter import simpledialog
from typing import Any

import chess
from PIL import Image, ImageTk

from .client import RuntimeClient
from .control import DockerControl
from .play import PlaySession, create_connector, supports_play
from games.catalog import GAMES
from recognition.runtime import FrameRecorder, RuntimeRecognizer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", default="http://127.0.0.1:8765")
    parser.add_argument("--game", choices=GAMES, default="grandmaster")
    parser.add_argument("--debug-frames", type=Path, help="Save recognition frames to this directory")
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
    selected_square: chess.Square | None = None

    def configure_recognition(*unused: object) -> None:
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

    def action(start: bool) -> None:
        nonlocal busy
        if busy:
            return
        if args.runtime.rstrip("/") != "http://127.0.0.1:8765":
            messages.put("Docker controls use the default local runtime; remove --runtime to enable them.")
            return
        game = selected.get()
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
        commands.put(("new_game", {}))

    new_button = ttk.Button(toolbar, text="New game", command=new_game)
    new_button.pack(side="left", padx=4)
    ttk.Label(toolbar, text="Closing this panel leaves the game running.").pack(side="left", padx=12)
    screen_frame = tk.Frame(root, width=640, height=480)
    screen_frame.grid(row=1, column=0)
    screen_frame.grid_propagate(False)
    screen = tk.Label(screen_frame, text="Connecting to emulator…")
    screen.place(relx=0.5, rely=0.5, anchor="center")
    board_canvas = tk.Canvas(root, width=480, height=480)
    board_canvas.grid(row=1, column=1)
    status = tk.Label(root, text="No recognized position published", anchor="w")
    status.grid(row=2, column=0, columnspan=2, sticky="ew")
    progress = tk.Text(root, height=9, width=120, state="disabled", wrap="word")
    progress.grid(row=3, column=0, columnspan=2, sticky="ew")

    def input_event(action_name: str, data: dict[str, Any]) -> None:
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
        commands.put(("move", {"uci": move.uci()}))

    board_canvas.bind("<Button-1>", board_click)
    updates: Queue[dict[str, Any] | str] = Queue(maxsize=1)
    stop = Event()

    def fetch() -> None:
        recognizer: RuntimeRecognizer | None = None
        configuration: tuple[str, bool, bool] | None = None
        session: PlaySession | None = None
        while not stop.is_set():
            try:
                latest = configuration
                while not configurations.empty():
                    latest = configurations.get_nowait()
                if latest != configuration:
                    reset_session = configuration is None or latest is None or latest[:2] != configuration[:2]
                    configuration = latest
                    assert configuration is not None
                    game, enabled, debug = configuration
                    recorder = FrameRecorder(args.debug_frames or Path("debug-frames"), game) if enabled and debug else None
                    recognizer = RuntimeRecognizer(game, client, recorder) if enabled else None
                    if reset_session:
                        session = None
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
                        if command == "new_game":
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
                            session.submit(data["uci"])
                        else:
                            if session:
                                session.invalidate("Manual input or lifecycle change; press New game to resynchronize")
                            if command != "invalidate":
                                client.send(command, data)
                    except Exception as error:
                        messages.put(f"Game action failed: {error}")
                update: dict[str, Any] | str = client.snapshot()
                if recognizer:
                    update["recognition_status"] = recognizer.process(update)
                if session and recognizer:
                    with Image.open(io.BytesIO(base64.b64decode(update["png"]))) as frame:
                        session.observe(frame, recognizer.confirmed_placement)
                    update["play"] = session.state()
            except Exception as error:
                if session:
                    session.invalidate("Disconnected; press New game after reconnecting")
                update = f"Disconnected: {error}"
            if updates.empty():
                updates.put_nowait(update)
            # Refresh pacing only; this is never used to decide move completion.
            stop.wait(0.25)

    photo: ImageTk.PhotoImage | None = None

    def redraw() -> None:
        nonlocal photo, busy, play_state, selected_square
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
                selected_square = None
                status.configure(text=update)
            else:
                play_state = update.get("play", {})
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
