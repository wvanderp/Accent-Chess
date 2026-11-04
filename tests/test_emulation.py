"""Verify observer independence and frame/recognition consistency over HTTP."""

import base64
from io import BytesIO
from threading import Thread
import unittest
from urllib.error import HTTPError

import chess
from PIL import Image

from src.emulation.client import RuntimeClient
from src.emulation.server import Session, make_server


class FakeBackend:
    def __init__(self) -> None:
        output = BytesIO()
        Image.new("RGB", (640, 480)).save(output, format="PNG")
        self.png = output.getvalue()
        self.keys: list[str] = []

    def capture(self) -> bytes:
        return self.png

    def key(self, name: str) -> None:
        self.keys.append(name)

    def click(self, x: int, y: int) -> None:
        pass


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
        self.client.send("key", {"name": "Return"})
        self.assertEqual(self.backend.keys, ["Return"])
        observer = RuntimeClient(self.client.url)
        self.assertEqual(observer.snapshot()["frame_id"], self.client.snapshot()["frame_id"])
        self.client.send("key", {"name": "F1"})
        self.assertEqual(self.backend.keys, ["Return", "F1"])

    def test_invalid_fen_is_rejected(self) -> None:
        frame = self.client.snapshot()
        with self.assertRaises(HTTPError) as context:
            self.client.send("board", {"fen": "invalid", "frame_id": frame["frame_id"]})
        self.assertEqual(context.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
