"""The bridge between the web UI (window.pywebview.api.*) and the app.

pywebview exposes every public method of this class to JavaScript. Internal
objects are kept in underscore attributes so they are never exposed.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .. import APP_NAME, AUTHOR, AUTHOR_LINKS, CONTACT_EMAIL, GITHUB_REPO, WEBSITE, __version__, macos, paths
from ..processors.documents import CODE_EXTS, MARKITDOWN_EXTS, TEXTUTIL_EXTS
from ..processors.images import FORMATS, IMAGE_EXTS, compare_formats
from ..settings import ValidationError, describe

log = logging.getLogger("airdrop-compress")

UPDATE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_INTERVAL = 24 * 3600


class Api:
    def __init__(self, app):
        self._app = app
        self._update: dict = {}
        self._update_checked = 0.0
        self._update_lock = threading.Lock()

    # -- helpers ------------------------------------------------------------ #

    @property
    def _engine(self):
        return self._app.engine

    @property
    def _settings(self):
        return self._app.settings

    @property
    def _plugins(self):
        return self._app.plugins

    def _dialog(self, kind, **kw):
        window = self._app.window
        result = window.create_file_dialog(kind, **kw) if window else None
        return [str(p) for p in result] if result else []

    # -- state -------------------------------------------------------------- #

    def bootstrap(self) -> dict:
        return {
            "app": {"name": APP_NAME, "version": __version__, "repo": GITHUB_REPO,
                    "frozen": paths.is_frozen(), "support_dir": str(paths.SUPPORT_DIR),
                    "log_file": str(paths.LOG_FILE), "plugins_dir": str(paths.PLUGINS_DIR),
                    "author": AUTHOR, "author_links": AUTHOR_LINKS, "website": WEBSITE},
            "settings": self._settings.current.to_dict(),
            "schema": describe(),
            "formats": {k: {"label": v["label"], "ext": v["ext"], "alpha": v["alpha"],
                            "animation": v["animation"]} for k, v in FORMATS.items()},
            "file_types": {
                "images": sorted(IMAGE_EXTS),
                "documents": sorted(MARKITDOWN_EXTS),
                "legacy_documents": sorted(TEXTUTIL_EXTS),
                "code": sorted(CODE_EXTS),
            },
            **self.poll(-1),
            "plugins": self._plugins.to_ui(),
            "update": self._update,
        }

    def poll(self, revision: int = -1) -> dict:
        out = {
            "status": self._app.status(),
            "stats": self._engine.activity.stats(),
            "revision": self._engine.activity.revision,
            "history_count": self._engine.store.count() if revision == -1 else None,
        }
        if revision != self._engine.activity.revision:
            out["activity"] = self._engine.activity.snapshot()
        return out

    # -- settings ----------------------------------------------------------- #

    def save_settings(self, patch: dict) -> dict:
        try:
            new = self._settings.update(patch)
        except ValidationError as e:
            return {"ok": False, "errors": e.errors, "settings": self._settings.current.to_dict()}
        return {"ok": True, "settings": new.to_dict()}

    def reset_settings(self, section: str | None = None) -> dict:
        return {"ok": True, "settings": self._settings.reset(section or None).to_dict()}

    def choose_watch_folder(self) -> dict:
        import webview
        chosen = self._dialog(webview.FileDialog.FOLDER)
        if not chosen:
            return {"ok": False}
        return self.save_settings({"general": {"watch_folder": chosen[0]}})

    # -- actions ------------------------------------------------------------ #

    def pause(self) -> dict:
        self._engine.pause()
        return self._app.status()

    def resume(self) -> dict:
        self._engine.resume()
        return self._app.status()

    def open_folder(self, which: str) -> None:
        targets = {"watch": self._engine.watch_dir, "output": self._engine.output_dir,
                   "plugins": paths.PLUGINS_DIR, "support": paths.SUPPORT_DIR, "logs": paths.LOG_DIR}
        target = targets.get(which)
        if target:
            target.mkdir(parents=True, exist_ok=True)
            macos.open_path(target)

    def reveal_output(self, name: str) -> None:
        path = (self._engine.output_dir / name).resolve()
        if path.parent == self._engine.output_dir.resolve() and path.exists():
            macos.reveal(path)

    def scan_existing(self) -> dict:
        if self._engine.state != "running":
            return {"ok": False, "error": "Start watching first (it's paused or waiting)."}
        return {"ok": True, "count": self._engine.scan_existing()}

    def convert_files(self) -> dict:
        import webview
        files = self._dialog(webview.FileDialog.OPEN, allow_multiple=True)
        return self.convert_paths(files)

    def convert_paths(self, files: list[str]) -> dict:
        if not files:
            return {"ok": False, "count": 0}
        supported = [Path(f) for f in files if self._engine.route(Path(f))]
        if self._engine.state != "running":
            return {"ok": False, "error": "Processing is paused - resume it first."}
        count = self._engine.convert_now(supported)
        skipped = len(files) - len(supported)
        return {"ok": True, "count": count, "unsupported": skipped}

    def compare_formats(self) -> dict:
        import webview
        exts = ";".join(f"*{e}" for e in sorted(IMAGE_EXTS))
        files = self._dialog(webview.FileDialog.OPEN, file_types=(f"Images ({exts})",))
        if not files:
            return {"ok": False}
        try:
            return {"ok": True, **compare_formats(Path(files[0]), self._settings.current)}
        except Exception as e:
            log.exception("Compare failed")
            return {"ok": False, "error": f"Couldn't read that image: {e}"}

    def clear_history(self) -> dict:
        count = self._engine.store.clear()
        self._engine.activity.clear()
        return {"ok": True, "count": count}

    def open_url(self, url: str) -> None:
        if url.startswith("https://"):
            macos.open_url(url)

    def contact(self, topic: str = "business") -> None:
        """Open an email to the developer with a ready-to-fill inquiry (address fixed in code)."""
        macos.open_url(contact_mailto(topic))

    def open_privacy_settings(self) -> None:
        macos.open_privacy_settings()

    def remove_legacy_service(self) -> dict:
        macos.remove_legacy_service()
        self._app.legacy_resolved()
        return {"ok": True}

    def quit(self) -> None:
        threading.Thread(target=self._app.quit, daemon=True).start()

    # -- plugins ------------------------------------------------------------ #

    def list_plugins(self) -> list:
        self._plugins.discover()
        return self._plugins.to_ui()

    def enable_plugin(self, plugin_id: str) -> dict:
        try:
            self._plugins.enable(plugin_id)
        except (KeyError, ValueError) as e:
            return {"ok": False, "error": str(e), "plugins": self._plugins.to_ui()}
        return {"ok": True, "plugins": self._plugins.to_ui()}

    def disable_plugin(self, plugin_id: str) -> dict:
        self._plugins.disable(plugin_id)
        return {"ok": True, "plugins": self._plugins.to_ui()}

    def save_plugin_settings(self, plugin_id: str, values: dict) -> dict:
        try:
            self._plugins.update_settings(plugin_id, values)
        except (KeyError, ValueError) as e:
            return {"ok": False, "error": str(e), "plugins": self._plugins.to_ui()}
        return {"ok": True, "plugins": self._plugins.to_ui()}

    def install_plugin(self, from_folder: bool = False, replace: bool = False) -> dict:
        import webview
        if from_folder:
            chosen = self._dialog(webview.FileDialog.FOLDER)
        else:
            chosen = self._dialog(webview.FileDialog.OPEN, file_types=("Plugin archive (*.zip)",))
        if not chosen:
            return {"ok": False}
        return self.install_plugin_path(chosen[0], replace)

    def install_plugin_path(self, source: str, replace: bool = False) -> dict:
        try:
            info = self._plugins.install(Path(source), replace=replace)
        except FileExistsError as e:
            return {"ok": False, "exists": True, "source": source, "error": str(e)}
        except (ValueError, OSError) as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "id": info.id, "name": info.name, "plugins": self._plugins.to_ui()}

    def remove_plugin(self, plugin_id: str) -> dict:
        try:
            self._plugins.remove(plugin_id)
        except (KeyError, ValueError, OSError) as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "plugins": self._plugins.to_ui()}

    # -- updates ------------------------------------------------------------ #

    def check_updates(self, force: bool = False) -> dict:
        with self._update_lock:
            if not force and self._update and time.time() - self._update_checked < UPDATE_INTERVAL:
                return self._update
            self._update = fetch_update_info()
            self._update_checked = time.time()
            return self._update

    # -- uninstall ---------------------------------------------------------- #

    def uninstall(self) -> dict:
        """Remove the login item, settings, history, plugins and logs, move the app
        to the Trash and quit. Originals and converted files are never touched."""
        self._engine.stop()
        macos.set_login_item(False)
        shutil.rmtree(paths.SUPPORT_DIR, ignore_errors=True)
        shutil.rmtree(paths.LOG_DIR, ignore_errors=True)
        bundle = paths.app_bundle()
        trashed = bool(bundle and macos.move_to_trash(bundle))
        self._app.uninstalling = True
        threading.Timer(1.5, self._app.quit).start()
        return {"ok": True, "trashed": trashed}


CONTACT_TOPICS = {
    "business": "Business inquiry",
    "custom": "Custom solution request",
}


def contact_mailto(topic: str) -> str:
    subject = f"{CONTACT_TOPICS.get(topic, CONTACT_TOPICS['business'])} - {APP_NAME}"
    body = (f"Hi {AUTHOR},\n\n"
            "I'm interested in (delete what doesn't apply):\n"
            "- Custom app development\n- Business-specific features or integrations\n"
            "- Custom automation\n- Enterprise requirements / bulk deployment\n"
            "- Partnership or collaboration\n- Technical support or consulting\n\n"
            "Company / name:\nWhat I need:\nTimeline:\nBudget (optional):\n\n"
            f"Sent from {APP_NAME} {__version__}")
    return f"mailto:{CONTACT_EMAIL}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"


def parse_version(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.lstrip("v").split(".")[:3])
    except ValueError:
        return (0,)


def _ssl_context() -> ssl.SSLContext:
    # python.org's Python and the packaged app don't use the macOS keychain's certificates.
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_update_info() -> dict:
    info = {"current": __version__, "checked_at": time.strftime("%Y-%m-%d %H:%M")}
    req = urllib.request.Request(UPDATE_URL, headers={
        "Accept": "application/vnd.github+json", "User-Agent": f"{APP_NAME}/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=8, context=_ssl_context()) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {**info, "available": False, "latest": __version__, "note": "No releases published yet."}
        return {**info, "error": f"GitHub returned {e.code}"}
    except (urllib.error.URLError, TimeoutError, OSError):
        return {**info, "error": "Couldn't reach GitHub - check your internet connection."}
    # Only trust a plain version number and links to this repository on github.com.
    latest = str(data.get("tag_name", "")).lstrip("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", latest):
        return {**info, "error": "GitHub returned an unexpected version"}
    repo_prefix = f"https://github.com/{GITHUB_REPO}/"
    dmg = next((a.get("browser_download_url") for a in data.get("assets", [])
                if str(a.get("name", "")).endswith(".dmg")
                and str(a.get("browser_download_url", "")).startswith(repo_prefix)), None)
    page = data.get("html_url") if str(data.get("html_url", "")).startswith(repo_prefix) else None
    return {**info, "latest": latest, "available": parse_version(latest) > parse_version(__version__),
            "url": dmg or page or f"{repo_prefix}releases/latest", "page": page,
            "notes": (data.get("body") or "")[:2000]}
