"""Duplicate protection: remembers processed files by content hash."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import threading
import time
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class ProcessedStore:
    """Remembers files by content hash, so the same file is only converted once."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.in_progress: set[str] = set()

    def _load(self) -> dict[str, dict]:
        try:
            data = json.loads(self.path.read_text())
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def claim(self, digest: str, output_dir: Path) -> str | None:
        """Reserve a hash for processing. Returns why it should be skipped, or None."""
        with self.lock:
            if digest in self.in_progress:
                return "already being processed"
            # Read from disk each time: another run (e.g. `scan`) may have added records.
            entry = self._load().get(digest)
            if entry:
                outputs = entry.get("outputs") or [entry.get("output")]
                existing = [o for o in outputs if o and (output_dir / o).exists()]
                if existing:
                    return f"already converted to {existing[0]}"
            self.in_progress.add(digest)
            return None

    def finish(self, digest: str, src: Path, outputs: list[Path] | None) -> None:
        with self.lock:
            self.in_progress.discard(digest)
            if not outputs:
                return
            self._update(lambda data: data.__setitem__(digest, {
                "source": src.name,
                "output": outputs[0].name,          # v1 field, kept for compatibility
                "outputs": [o.name for o in outputs],
                "converted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }))

    def clear(self) -> int:
        with self.lock:
            count = len(self._load())
            self._update(lambda data: data.clear())
            return count

    def count(self) -> int:
        return len(self._load())

    def _update(self, change) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # File lock so two processes never overwrite each other's records.
        with open(self.path.with_suffix(".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = self._load()
            change(data)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=1))
            os.replace(tmp, self.path)
