"""Verify observer independence and frame/recognition consistency over HTTP."""

import base64
from io import BytesIO
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import chess
from PIL import Image

from src.emulation.client import RuntimeClient
from src.emulation.server import Session, make_server
from src.emulation.backend import X11Backend


class KeyboardTests(unittest.TestCase):
    def test_c64_window_focus_precedes_key_input(self) -> None:
        with patch("src.emulation.backend.subprocess.run") as run:
            X11Backend().key("a", delay_ms=200, window_title="VICE (C64SC)")
        self.assertEqual(run.call_args_list[0].args[0], [
            "xdotool", "search", "--onlyvisible", "--name", r"^VICE\ \(C64SC\)$", "windowfocus", "--sync"])
        self.assertEqual(run.call_args_list[1].args[0], [
            "xdotool", "key", "--clearmodifiers", "--delay", "200", "a"])

    def test_invalid_key_delay_is_rejected_before_input(self) -> None:
        for delay in (0, 1001, "200", True):
            with self.subTest(delay=delay), patch("src.emulation.backend.subprocess.run") as run:
                with self.assertRaises(ValueError):
                    X11Backend().key("a", delay_ms=delay)  # type: ignore[arg-type]
                run.assert_not_called()


class FakeBackend:
    def __init__(self) -> None:
        output = BytesIO()
        Image.new("RGB", (640, 480)).save(output, format="PNG")
        self.png = output.getvalue()
        self.keys: list[str] = []
        self.pointer: tuple[int, int] | None = None

    def capture(self) -> bytes:
        return self.png

    def key(self, name: str, delay_ms: int = 12, window_title: str | None = None) -> None:
        self.keys.append(name)
        self.delay_ms = delay_ms

    def click(self, x: int, y: int) -> None:
        pass

    def move_pointer(self, x: int, y: int) -> None:
        self.pointer = (x, y)


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeBackend()
        self.server = make_server(Session(self.backend), "127.0.0.1", 0)
        self.thread = Thread(target=self.server.serve_forever)
        self.thread.start()
        self.client = RuntimeClient(f"http://127.0.0.1:{self.server.server_port}")

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_frames_and_recognition_provenance(self) -> None:
        first = self.client.snapshot()
        self.assertIsNone(first["game"])
        self.assertIsNone(first["board"])
        self.assertEqual(base64.b64decode(first["png"]), self.backend.png)
        self.client.send("board", {"fen": chess.STARTING_FEN, "frame_id": first["frame_id"]})
        self.assertEqual(self.client.snapshot()["board"]["fen"], chess.STARTING_FEN)
        self.backend.png += b"changed"
        second = self.client.snapshot()
        self.assertGreater(second["frame_id"], first["frame_id"])
        self.assertEqual(second["board"]["frame_id"], first["frame_id"])
        with self.assertRaises(HTTPError) as context:
            self.client.send("board", {"fen": chess.STARTING_FEN, "frame_id": first["frame_id"]})
        self.assertEqual(context.exception.code, 400)

    def test_no_observer_needed_for_input(self) -> None:
        self.client.send("pointer", {"x": 630, "y": 470})
        self.assertEqual(self.backend.pointer, (630, 470))
        self.client.send("key", {"name": "Return"})
        self.assertEqual(self.backend.keys, ["Return"])
        observer = RuntimeClient(self.client.url)
        self.assertEqual(observer.snapshot()["frame_id"], self.client.snapshot()["frame_id"])
        self.client.send("key", {"name": "F1"})
        self.assertEqual(self.backend.keys, ["Return", "F1"])
        self.client.send("key", {"name": "a", "delay_ms": 200})
        self.assertEqual(self.backend.delay_ms, 200)

    def test_invalid_fen_is_rejected(self) -> None:
        frame = self.client.snapshot()
        with self.assertRaises(HTTPError) as context:
            self.client.send("board", {"fen": "invalid", "frame_id": frame["frame_id"]})
        self.assertEqual(context.exception.code, 400)

    def test_placement_publication_does_not_claim_position_metadata(self) -> None:
        frame = self.client.snapshot()
        self.client.send("board", {"placement": chess.STARTING_BOARD_FEN,
                                   "frame_id": frame["frame_id"]})
        observation = self.client.snapshot()["board"]
        self.assertEqual(observation["kind"], "placement")
        self.assertEqual(chess.Board(observation["fen"]).board_fen(), chess.STARTING_BOARD_FEN)
        with self.assertRaises(HTTPError) as context:
            self.client.send("board", {"placement": "invalid", "frame_id": frame["frame_id"]})
        self.assertEqual(context.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
