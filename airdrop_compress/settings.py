"""User settings: typed sections, validation, and persistence to settings.json.

Both the menu bar app and the command line read the same file, so a change made
in one is picked up by the other.
"""

from __future__ import annotations

import copy
import dataclasses
import fcntl
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import paths

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def _choice(default: str, options: list[str]):
    return field(default=default, metadata={"choices": options})


def _int(default: int, lo: int, hi: int):
    return field(default=default, metadata={"min": lo, "max": hi})


@dataclass
class GeneralSettings:
    # "" = automatic: ~/Desktop/AirDrop if it exists (airdropSorter users), else ~/Downloads.
    watch_folder: str = ""
    # A folder name inside the watch folder, or an absolute path.
    output_folder: str = "airdrop-compress"
    skip_web_downloads: bool = True
    notifications: bool = True
    launch_at_login: bool = True
    workers: int = _int(2, 1, 8)
    check_for_updates: bool = True
    paused: bool = False


@dataclass
class ImageSettings:
    enabled: bool = True
    # "auto" encodes every suitable format and keeps the smallest.
    format: str = _choice("webp", ["auto", "webp", "avif", "jpeg"])
    webp_quality: int = _int(80, 1, 100)
    avif_quality: int = _int(60, 1, 100)
    jpeg_quality: int = _int(82, 1, 100)
    effort: str = _choice("balanced", ["fast", "balanced", "best"])
    png_lossless: bool = False          # lossless WebP for PNG screenshots/graphics
    target_size_kb: int = _int(0, 0, 100_000)    # 0 = off
    max_dimension: int = _int(0, 0, 16_383)      # longest edge in px, 0 = keep
    responsive_widths: list[int] = field(default_factory=list, metadata={"item_min": 16, "item_max": 8192})
    metadata: str = _choice("keep", ["keep", "no_location", "strip"])
    color: str = _choice("keep", ["keep", "srgb"])
    seo_filenames: bool = False
    jpeg_fallback: bool = False
    jpeg_progressive: bool = True
    skip_if_larger: bool = False


@dataclass
class DocumentSettings:
    enabled: bool = True
    max_size_mb: int = _int(100, 1, 2000)


@dataclass
class Settings:
    general: GeneralSettings = field(default_factory=GeneralSettings)
    images: ImageSettings = field(default_factory=ImageSettings)
    documents: DocumentSettings = field(default_factory=DocumentSettings)
    # plugin id -> {"enabled": bool, "approved": {...}, "settings": {...}}; managed by PluginManager
    plugins: dict[str, dict] = field(default_factory=dict)
    version: int = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


SECTIONS = {"general": GeneralSettings, "images": ImageSettings, "documents": DocumentSettings}


class ValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _coerce(f: dataclasses.Field, value: Any, where: str) -> Any:
    """Validate one value against its field definition. Raises ValueError."""
    meta = f.metadata
    expected = f.type if isinstance(f.type, str) else getattr(f.type, "__name__", str(f.type))
    if expected == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{where} must be true or false")
        return value
    if expected == "int":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
            raise ValueError(f"{where} must be a whole number")
        value = int(value)
        if not meta["min"] <= value <= meta["max"]:
            raise ValueError(f"{where} must be between {meta['min']} and {meta['max']}")
        return value
    if expected == "str":
        if not isinstance(value, str):
            raise ValueError(f"{where} must be text")
        if "choices" in meta and value not in meta["choices"]:
            raise ValueError(f"{where} must be one of: {', '.join(meta['choices'])}")
        return value.strip()
    if expected.startswith("list"):
        if not isinstance(value, list):
            raise ValueError(f"{where} must be a list")
        out = []
        for v in value:
            if isinstance(v, bool) or not isinstance(v, int) or not meta["item_min"] <= v <= meta["item_max"]:
                raise ValueError(f"{where} values must be between {meta['item_min']} and {meta['item_max']}")
            out.append(v)
        return sorted(set(out))
    return value


def _apply_section(section: Any, data: dict, name: str, errors: list[str], strict: bool) -> None:
    fields = {f.name: f for f in dataclasses.fields(section)}
    for key, value in data.items():
        if key not in fields:
            if strict:
                errors.append(f"Unknown setting {name}.{key}")
            continue
        try:
            setattr(section, key, _coerce(fields[key], value, f"{name}.{key}"))
        except ValueError as e:
            errors.append(str(e))


def from_dict(data: dict, base: Settings | None = None, strict: bool = False) -> Settings:
    """Build Settings from (possibly partial) data. Invalid values raise when strict,
    otherwise they are logged and the previous/default value is kept."""
    settings = copy.deepcopy(base) if base else Settings()
    errors: list[str] = []
    data = migrate(dict(data))
    for name, cls in SECTIONS.items():
        if name in data:
            if not isinstance(data[name], dict):
                errors.append(f"{name} must be an object")
                continue
            _apply_section(getattr(settings, name), data[name], name, errors, strict)
    if isinstance(data.get("plugins"), dict):
        settings.plugins = copy.deepcopy(data["plugins"])
    if errors:
        if strict:
            raise ValidationError(errors)
        for e in errors:
            log.warning("Ignoring invalid setting: %s", e)
    return settings


def migrate(data: dict) -> dict:
    """Upgrade settings written by older versions. (v1 is the first schema.)"""
    data.setdefault("version", SCHEMA_VERSION)
    return data


def resolve_watch_folder(settings: Settings) -> Path:
    if os.environ.get("AIRDROP_DIR"):
        return Path(os.environ["AIRDROP_DIR"]).expanduser()
    if settings.general.watch_folder:
        return Path(settings.general.watch_folder).expanduser()
    sorted_dir = Path("~/Desktop/AirDrop").expanduser()
    return sorted_dir if sorted_dir.is_dir() else Path("~/Downloads").expanduser()


def resolve_output_folder(settings: Settings) -> Path:
    out = Path(settings.general.output_folder or "airdrop-compress").expanduser()
    return out if out.is_absolute() else resolve_watch_folder(settings) / out


class SettingsManager:
    """Holds the current settings, saves them atomically and tells listeners about changes."""

    def __init__(self, path: Path = paths.SETTINGS_FILE):
        self.path = path
        self._lock = threading.RLock()
        self._listeners: list[Callable[[Settings, Settings], None]] = []
        self._mtime = 0.0
        self.current = self._read()

    def _read(self) -> Settings:
        try:
            raw = json.loads(self.path.read_text())
            self._mtime = self.path.stat().st_mtime
            return from_dict(raw if isinstance(raw, dict) else {})
        except FileNotFoundError:
            return Settings()
        except (OSError, json.JSONDecodeError) as e:
            log.error("Could not read %s (%s); using defaults.", self.path, e)
            return Settings()

    def subscribe(self, fn: Callable[[Settings, Settings], None]) -> None:
        self._listeners.append(fn)

    def update(self, patch: dict) -> Settings:
        """Apply a partial update like {"images": {"format": "avif"}}. Raises ValidationError."""
        with self._lock:
            old = self.current
            new = from_dict(patch, base=old, strict=True)
            self._commit(old, new)
        self._notify(old, new)
        return new

    def replace_plugins(self, plugins: dict) -> None:
        with self._lock:
            old = self.current
            new = copy.deepcopy(old)
            new.plugins = copy.deepcopy(plugins)
            self._commit(old, new)
        self._notify(old, new)

    def reset(self, section: str | None = None) -> Settings:
        with self._lock:
            old = self.current
            new = copy.deepcopy(old)
            if section:
                setattr(new, section, SECTIONS[section]())
            else:
                new = Settings(plugins=old.plugins)
            self._commit(old, new)
        self._notify(old, new)
        return new

    def reload_if_changed(self) -> bool:
        """Pick up edits made by another process (e.g. the app while the CLI runs)."""
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            return False
        if mtime == self._mtime:
            return False
        with self._lock:
            old, self.current = self.current, self._read()
        self._notify(old, self.current)
        return True

    def save(self) -> None:
        with self._lock:
            self._write(self.current)

    def _commit(self, old: Settings, new: Settings) -> None:
        # Listeners are notified by the caller after the lock is released.
        self.current = new
        self._write(new)

    def _write(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_suffix(".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(settings.to_dict(), indent=2))
            os.replace(tmp, self.path)
            self._mtime = self.path.stat().st_mtime

    def _notify(self, old: Settings, new: Settings) -> None:
        for fn in list(self._listeners):
            try:
                fn(old, new)
            except Exception:
                log.exception("Settings listener failed")


def describe() -> dict:
    """Field metadata for the UI (choices, ranges, defaults)."""
    out = {}
    for name, cls in SECTIONS.items():
        out[name] = {}
        for f in dataclasses.fields(cls):
            default = f.default_factory() if f.default_factory is not dataclasses.MISSING else f.default
            out[name][f.name] = {"default": default, **dict(f.metadata)}
    return out
