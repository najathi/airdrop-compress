"""Small wrappers around macOS features (notifications, Finder, login items)."""

from __future__ import annotations

import getpass
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from . import BUNDLE_ID, paths

LOGIN_LABEL = f"{BUNDLE_ID}.login"
LOGIN_PLIST = Path(f"~/Library/LaunchAgents/{LOGIN_LABEL}.plist").expanduser()
# The v1 command-line service (`./airdrop-compress install`).
LEGACY_LABEL = f"com.{getpass.getuser()}.airdrop-compress"
LEGACY_PLIST = Path(f"~/Library/LaunchAgents/{LEGACY_LABEL}.plist").expanduser()


def notify(title: str, message: str) -> None:
    script = f"display notification {json.dumps(message)} with title {json.dumps(title)}"
    subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True)


def quarantine_agent(path: Path) -> str | None:
    """The app that quarantined the file ("sharingd" for AirDrop, "Chrome"...),
    "" for a blank tag, or None if the file has no quarantine tag."""
    result = subprocess.run(
        ["/usr/bin/xattr", "-p", "com.apple.quarantine", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    parts = result.stdout.strip().split(";")
    return parts[2] if len(parts) > 2 else ""


def open_path(path: Path) -> None:
    subprocess.run(["/usr/bin/open", str(path)], capture_output=True)


def reveal(path: Path) -> None:
    subprocess.run(["/usr/bin/open", "-R", str(path)], capture_output=True)


def open_url(url: str) -> None:
    if url.startswith(("https://", "x-apple.systempreferences:")):
        subprocess.run(["/usr/bin/open", url], capture_output=True)


def open_privacy_settings() -> None:
    open_url("x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")


# --------------------------------------------------------------------------- #
# Launch at login
# --------------------------------------------------------------------------- #

def _domain() -> str:
    return f"gui/{os.getuid()}"


def launcher_command() -> tuple[list[str], dict]:
    """How to start the app in the background (for the login item)."""
    if paths.is_frozen():
        return [sys.executable, "--background"], {}
    project = str(paths.PACKAGE_DIR.parent)
    return [sys.executable, "-m", "airdrop_compress", "gui", "--background"], {"PYTHONPATH": project}


def login_item_installed() -> bool:
    return LOGIN_PLIST.exists()


def set_login_item(enabled: bool) -> None:
    if not enabled:
        subprocess.run(["/bin/launchctl", "bootout", f"{_domain()}/{LOGIN_LABEL}"], capture_output=True)
        LOGIN_PLIST.unlink(missing_ok=True)
        return
    args, env = launcher_command()
    plist = {
        "Label": LOGIN_LABEL,
        "ProgramArguments": args,
        "RunAtLoad": True,
        # Restart after a crash, but not after the user chooses Quit.
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "ProcessType": "Interactive",
        "AssociatedBundleIdentifiers": [BUNDLE_ID],
        "StandardOutPath": str(paths.LOG_FILE),
        "StandardErrorPath": str(paths.LOG_FILE),
    }
    if env:
        plist["EnvironmentVariables"] = env
    LOGIN_PLIST.parent.mkdir(parents=True, exist_ok=True)
    new = plistlib.dumps(plist)
    if LOGIN_PLIST.exists() and LOGIN_PLIST.read_bytes() == new:
        return
    LOGIN_PLIST.write_bytes(new)
    # Only registered, not started now: the app is already running. launchd starts it at next login.


def legacy_service_installed() -> bool:
    return LEGACY_PLIST.exists()


def remove_legacy_service() -> None:
    """Stop and remove the v1 command-line LaunchAgent (the app replaces it)."""
    subprocess.run(["/bin/launchctl", "bootout", f"{_domain()}/{LEGACY_LABEL}"], capture_output=True)
    subprocess.run(["/bin/launchctl", "enable", f"{_domain()}/{LEGACY_LABEL}"], capture_output=True)
    LEGACY_PLIST.unlink(missing_ok=True)


def move_to_trash(path: Path) -> bool:
    script = f'tell application "Finder" to delete (POSIX file {json.dumps(str(path))})'
    return subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True).returncode == 0
