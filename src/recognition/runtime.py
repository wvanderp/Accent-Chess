"""Connect game-owned image readers to the local runtime, with optional evidence.

Two consecutive captures must agree before publication. This filters transient
draws without assuming elapsed time means that an engine has finished moving.
Published observations describe piece placement only, never full chess history.
"""

import base64
from datetime import datetime, timezone
from hashlib import sha256
from importlib import import_module
from io import BytesIO
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

from PIL import Image, ImageDraw

from emulation.client import RuntimeClient
from .board import BoardReader, Observation, RecognitionError

MODULES = {"grandmaster": "games.Grandmaster_Chess.recognition",
           "chess19xx": "games.Chess_19xx.recognition",
           "chessmaster2000": "games.Chessmaster_2000.recognition",
           "battlechess": "games.Battle_Chess.recognition"}


def create_reader(game: str) -> BoardReader:
    return BoardReader(import_module(MODULES[game]).PROFILE)


class FrameRecorder:
    """Bounded, opt-in evidence. Never writes into the training dataset."""

    def __init__(self, root: Path, game: str, limit: int = 500) -> None:
        self.directory = root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + game)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.game = game
        self.limit = limit
        self.count = 0
        self.last_digest = ""

    def save(self, png: bytes, frame_id: int, reader: BoardReader,
             observation: Observation | None, error: str | None) -> None:
        digest = sha256(png).hexdigest()
        if self.count >= self.limit or digest == self.last_digest:
            return
        self.last_digest = digest
        self.count += 1
        prefix = f"{self.count:05d}-frame-{frame_id}"
        (self.directory / f"{prefix}.png").write_bytes(png)
        if observation:
            observation.crop.save(self.directory / f"{prefix}-board.png")
            observation.overlay.save(self.directory / f"{prefix}-overlay.png")
        else:
            with Image.open(BytesIO(png)) as frame:
                x, y, width, height = reader.profile.region
                frame.crop((x, y, x + width, y + height)).save(self.directory / f"{prefix}-board.png")
                overlay = frame.convert("RGB")
                draw = ImageDraw.Draw(overlay)
                draw.rectangle((x, y, x + width, y + height), outline="red", width=2)
                draw.text((4, 465), str(error), fill="red", stroke_width=1, stroke_fill="white")
                overlay.save(self.directory / f"{prefix}-overlay.png")
        metadata = {"game": self.game, "frame_id": frame_id, "sha256": digest,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "region": reader.profile.region, "error": error,
                    "placement": observation.placement if observation else None,
                    "squares": observation.squares if observation else []}
        (self.directory / f"{prefix}.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


class RuntimeRecognizer:
    def __init__(self, game: str, client: RuntimeClient, recorder: FrameRecorder | None = None) -> None:
        self.reader = create_reader(game)
        self.client = client
        self.recorder = recorder
        self.previous: str | None = None
        self.last_png = b""
        self.cached: Observation | None = None
        self.error: str | None = None
        self.confirmed_placement: str | None = None

    def process(self, snapshot: dict[str, Any]) -> str:
        self.confirmed_placement = None
        png = base64.b64decode(snapshot["png"], validate=True)
        if png != self.last_png:
            self.last_png = png
            self.cached = None
            self.error = None
            try:
                with Image.open(BytesIO(png)) as image:
                    self.cached = self.reader.read(image)
            except (RecognitionError, OSError) as error:
                self.error = str(error)
            if self.recorder:
                self.recorder.save(png, snapshot["frame_id"], self.reader, self.cached, self.error)
        if self.cached is None:
            self.previous = None
            return f"Unrecognized: {self.error}"
        placement = self.cached.placement
        if placement != self.previous:
            self.previous = placement
            return "Recognized placement; confirming next capture"
        try:
            self.client.send("board", {"placement": placement, "frame_id": snapshot["frame_id"]})
        except HTTPError as error:
            if error.code != 400:
                raise
            return "Frame advanced during recognition; waiting for next capture"
        self.confirmed_placement = placement
        return "Recognized piece placement (turn and castling unknown)"
