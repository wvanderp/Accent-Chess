"""Docker game control panel and optional emulator observer."""

import argparse
import base64
import io
from queue import Empty, Queue
from threading import Event, Thread
import tkinter as tk
from tkinter import ttk
from typing import Any

import chess
from PIL import Image, ImageTk

from .client import RuntimeClient
from .control import DockerControl
from games.catalog import GAMES


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    client = RuntimeClient(args.runtime)
    root = tk.Tk()
    root.title("Accent Chess — control panel")
    toolbar = ttk.Frame(root, padding=8)
    toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
    selected = tk.StringVar(value="grandmaster")
    ttk.Label(toolbar, text="Game").pack(side="left", padx=4)
    picker = ttk.Combobox(toolbar, textvariable=selected, values=list(GAMES), state="readonly", width=20)
    picker.pack(side="left", padx=4)
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
        busy = True
        start_button.configure(state="disabled")
        stop_button.configure(state="disabled")

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
        def send() -> None:
            try:
                client.send(action_name, data)
            except Exception as error:
                messages.put(f"Input failed: {error}")
        Thread(target=send, daemon=True).start()

    def click(event: tk.Event) -> None:
        screen.focus_set()
        input_event("click", {"x": event.x, "y": event.y})

    def key(event: tk.Event) -> str:
        input_event("key", {"name": event.keysym})
        return "break"

    screen.bind("<Button-1>", click)
    screen.bind("<KeyPress>", key)
    updates: Queue[dict[str, Any] | str] = Queue(maxsize=1)
    stop = Event()

    def fetch() -> None:
        while not stop.is_set():
            try:
                update: dict[str, Any] | str = client.snapshot()
            except Exception as error:
                update = f"Disconnected: {error}"
            if updates.empty():
                updates.put_nowait(update)
            # Refresh pacing only; this is never used to decide move completion.
            stop.wait(0.25)

    photo: ImageTk.PhotoImage | None = None

    def redraw() -> None:
        nonlocal photo, busy
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
                status.configure(text=update)
            else:
                image = Image.open(io.BytesIO(base64.b64decode(update["png"])))
                image.thumbnail((640, 480))
                photo = ImageTk.PhotoImage(image)
                screen.configure(image=photo, width=640, height=480)
                board_canvas.delete("all")
                observation = update["board"]
                board = chess.Board(observation["fen"]) if observation else chess.Board(None)
                for rank in range(8):
                    for file in range(8):
                        x, y = file * 60, (7 - rank) * 60
                        board_canvas.create_rectangle(x, y, x + 60, y + 60,
                            fill="#eadcc2" if (file + rank) % 2 else "#81947c", outline="")
                        piece = board.piece_at(chess.square(file, rank))
                        if piece:
                            board_canvas.create_text(x + 30, y + 30, text=piece.unicode_symbol(),
                                                     font=("Segoe UI Symbol", 38))
                message = "No recognized position published"
                if observation:
                    stale = observation["frame_id"] != update["frame_id"]
                    message = f"Board from frame {observation['frame_id']}" + (" (older than image)" if stale else "")
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
