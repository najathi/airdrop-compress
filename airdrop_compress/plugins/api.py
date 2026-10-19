"""The public plugin API. This is the only module a plugin should import.

A plugin is a folder with a ``plugin.json`` manifest and a Python entry file that
defines ``process(ctx)``::

    def process(ctx):
        text = ctx.input.read_text()
        ctx.output(".txt").write_text(text.upper())

See docs/PLUGINS.md for the full guide.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

API_VERSION = 1
SUPPORTED_API_VERSIONS = {1}

# What a plugin may ask for in its manifest. Everything else is always denied:
# plugins can read only the incoming file and their own folder, and write only
# to their private output folder.
PERMISSIONS = {
    "network": "Connect to the internet",
    "subprocess": "Run other programs on this Mac",
}

SUFFIX_RE = re.compile(r"^[A-Za-z0-9_\-]{0,40}\.[A-Za-z0-9]{1,10}$")
MAX_OUTPUTS = 20


class PluginSkip(Exception):
    """Raise (or call ctx.skip) to leave a file alone without it counting as an error."""


class PluginContext:
    """What a plugin's ``process(ctx)`` receives."""

    def __init__(self, input_path: Path, output_dir: Path, settings: dict[str, Any], plugin_id: str):
        self.input = input_path            # the received file - read it, never modify it
        self.output_dir = output_dir       # the only folder you may write to
        self.settings = settings           # this plugin's settings (from the app's Plugins page)
        self.plugin_id = plugin_id
        self.outputs: list[dict] = []

    def output(self, suffix: str, label: str = "") -> Path:
        """Reserve an output file and return the path to write it to.

        ``suffix`` is appended to the original file's name: ".svg" -> "logo.svg",
        "-small.png" -> "logo-small.png". The app picks a unique final name.
        """
        if not SUFFIX_RE.match(suffix):
            raise ValueError(f"Invalid output suffix {suffix!r} (expected something like '.png' or '-small.png')")
        if len(self.outputs) >= MAX_OUTPUTS:
            raise ValueError(f"A plugin may create at most {MAX_OUTPUTS} files per input")
        ext = Path("x" + suffix).suffix  # Path(".svg").suffix is "" - it's treated as a name
        path = self.output_dir / f"out{len(self.outputs)}{ext}"
        self.outputs.append({"file": path.name, "suffix": suffix, "label": label})
        return path

    def skip(self, reason: str) -> None:
        raise PluginSkip(reason)

    def log(self, message: str) -> None:
        """Write a line to the app's log."""
        print(f"[{self.plugin_id}] {message}", file=sys.stderr, flush=True)
