"""Small per-user preferences, stored outside the checkout and written atomically."""

import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def settings_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "Accent-Chess" / "settings.json"


def load_stockfish_path() -> str | None:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        value = data.get("stockfish") if isinstance(data, dict) else None
        return value if isinstance(value, str) and value.strip() else None
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        logging.warning("Could not read Accent Chess settings: %s", error)
        return None


def save_stockfish_path(executable: str) -> None:
    """Save only a verified engine location; a failed write preserves the old file."""
    target = settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"stockfish": executable}, stream, indent=2)
            stream.write("\n")
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
