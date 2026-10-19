"""Where AirDrop Compress keeps its files."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# AIRDROP_COMPRESS_HOME relocates all app data (used by the tests).
SUPPORT_DIR = Path(os.environ.get(
    "AIRDROP_COMPRESS_HOME", "~/Library/Application Support/AirDropCompress",
)).expanduser()

SETTINGS_FILE = SUPPORT_DIR / "settings.json"
STATE_FILE = SUPPORT_DIR / "processed.json"      # duplicate protection (content hashes)
ACTIVITY_FILE = SUPPORT_DIR / "activity.json"    # recent activity + daily stats
PLUGINS_DIR = SUPPORT_DIR / "plugins"
ENGINE_LOCK = SUPPORT_DIR / "engine.lock"        # only one watcher may run at a time

LOG_DIR = (SUPPORT_DIR / "logs") if "AIRDROP_COMPRESS_HOME" in os.environ \
    else Path("~/Library/Logs/AirDropCompress").expanduser()
LOG_FILE = LOG_DIR / "airdrop-compress.log"

PACKAGE_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    """True when running from the packaged .app (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def resource(relative: str) -> Path:
    """Path to a file shipped inside the package (works in the .app too)."""
    base = Path(getattr(sys, "_MEIPASS", PACKAGE_DIR.parent))
    return base / "airdrop_compress" / relative


def app_bundle() -> Path | None:
    """The .app bundle we're running from, if any."""
    if not is_frozen():
        return None
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


def ensure_dirs() -> None:
    # Private to this user: history and logs contain the names of files you received.
    for d in (SUPPORT_DIR, PLUGINS_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
        try:
            d.chmod(0o700)
        except OSError:
            pass
