"""Bounded, verified Archive downloads and contained ZIP extraction."""

import hashlib
from pathlib import Path
import shutil
from urllib.request import urlopen
import zipfile


def download(url: str, target: Path, sha1: str | None = None) -> Path:
    print(f"Downloading {url}", flush=True)
    temporary = target.with_suffix(target.suffix + ".partial")
    try:
        with urlopen(url, timeout=60) as response, temporary.open("wb") as output:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 128 * 1024 * 1024:
                    raise ValueError("Download exceeds 128 MiB limit")
                output.write(chunk)
        if sha1 and hashlib.sha1(temporary.read_bytes()).hexdigest() != sha1:
            raise ValueError("Downloaded media checksum mismatch")
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def extract(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        if sum(member.file_size for member in bundle.infolist()) > 256 * 1024 * 1024:
            raise ValueError("Expanded game exceeds 256 MiB limit")
        for member in bundle.infolist():
            target = (root / member.filename.replace("\\", "/")).resolve()
            if not target.is_relative_to(root):
                raise ValueError("ZIP member escapes game directory")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
