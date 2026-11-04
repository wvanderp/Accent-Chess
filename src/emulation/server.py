"""Versioned local HTTP boundary shared by connectors and the optional viewer.

Board recognition belongs to a game connector. No board is inferred here. A
publication must identify the captured frame it describes, preventing a delayed
recognizer from attaching an old board to a newer screenshot.
"""

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Lock
from typing import Any

import chess

from .backend import Backend, X11Backend


class Session:
    def __init__(self, backend: Backend) -> None:
        self.backend = backend
        self.lock = Lock()
        self.sequence = 0
        self.png = b""
        self.board: dict[str, Any] | None = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            png = self.backend.capture()
            if png != self.png:
                self.sequence += 1
                self.png = png
            return {"version": 1, "frame_id": self.sequence,
                    "png": base64.b64encode(self.png).decode("ascii"), "board": self.board}

    def publish(self, fen: str, frame_id: int, *, placement_only: bool = False) -> None:
        board = chess.Board(fen)
        with self.lock:
            if frame_id != self.sequence or not self.png:
                raise ValueError("Recognition must reference the latest captured frame")
            self.board = {"fen": board.fen(), "frame_id": frame_id,
                          "kind": "placement" if placement_only else "position"}


def make_server(session: Session, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code: int, data: dict[str, Any]) -> None:
            payload = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            if self.path != "/v1/snapshot":
                self.reply(404, {"error": "Unknown endpoint"})
                return
            try:
                self.reply(200, session.snapshot())
            except Exception:
                self.reply(503, {"error": "Emulator display unavailable"})

        def do_POST(self) -> None:
            # Only local CLI clients should mutate a session; reject browser forms.
            if self.headers.get_content_type() != "application/json" or self.headers.get("Origin"):
                self.reply(403, {"error": "Expected a local JSON client"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(length))
                if self.path == "/v1/board":
                    if "placement" in data:
                        placement = data["placement"]
                        board = chess.Board(None)
                        board.set_board_fen(placement)
                        session.publish(board.fen(), int(data["frame_id"]), placement_only=True)
                    else:
                        session.publish(data["fen"], int(data["frame_id"]))
                elif self.path == "/v1/key":
                    with session.lock:
                        session.backend.key(data["name"])
                elif self.path == "/v1/click":
                    with session.lock:
                        session.backend.click(int(data["x"]), int(data["y"]))
                else:
                    self.reply(404, {"error": "Unknown endpoint"})
                    return
                self.reply(200, {"ok": True})
            except (ValueError, KeyError, TypeError):
                self.reply(400, {"error": "Invalid request or stale frame"})
            except Exception:
                self.reply(503, {"error": "Emulator input unavailable"})

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with make_server(Session(X11Backend()), args.host, args.port) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
