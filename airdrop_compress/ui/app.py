"""The menu bar app: a status item in the menu bar plus a dashboard/settings window.

The window is a native WKWebView (pywebview) showing ui/web/index.html. Closing it
only hides it - the app keeps watching from the menu bar until you choose Quit.
"""

from __future__ import annotations

import logging

from .. import APP_NAME, macos, paths
from ..activity import ActivityLog
from ..engine import Engine
from ..plugins.manager import PluginManager
from ..settings import SettingsManager
from .api import Api

log = logging.getLogger("airdrop-compress")


class App:
    def __init__(self, background: bool):
        paths.ensure_dirs()
        self.background = background
        self.settings = SettingsManager()
        self.plugins = PluginManager(self.settings)
        self.engine = Engine(self.settings, self.plugins, ActivityLog(paths.ACTIVITY_FILE))
        self.api = Api(self)
        self.window = None
        self.menu_bar = None
        self.quitting = False
        self.uninstalling = False
        self.legacy_service = macos.legacy_service_installed()
        self.settings.subscribe(self._on_settings_changed)

    # -- lifecycle ---------------------------------------------------------- #

    def start_engine(self) -> None:
        if self.legacy_service:
            # The v1 command-line service would process every file a second time.
            log.warning("The v1 command-line service is installed; waiting for the user to switch.")
            return
        if not self.settings.current.general.paused:
            self.engine.start()
        else:
            self.engine.state, self.engine.message = "paused", "Paused - new files aren't processed."

    def legacy_resolved(self) -> None:
        self.legacy_service = False
        self.start_engine()

    def status(self) -> dict:
        s = self.engine.status()
        if self.legacy_service:
            s.update(state="legacy", message="The command-line service from version 1 is still installed.")
        s["legacy_service"] = self.legacy_service
        s["login_item"] = macos.login_item_installed()
        s["paused"] = self.settings.current.general.paused
        return s

    def sync_login_item(self) -> None:
        # Only the installed app manages the login item; a source checkout shouldn't
        # register itself to start at every login.
        if paths.is_frozen():
            try:
                macos.set_login_item(self.settings.current.general.launch_at_login)
            except OSError as e:
                log.error("Couldn't update the login item: %s", e)

    def _on_settings_changed(self, old, new) -> None:
        if old.general.launch_at_login != new.general.launch_at_login:
            self.sync_login_item()

    def show_window(self) -> None:
        if not self.window:
            return
        try:
            import AppKit
            AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except ImportError:
            pass
        self.window.show()
        self.window.restore()

    def prepare_for_exit(self) -> None:
        """macOS is terminating the app: stop quickly (results are written atomically,
        and unfinished work folders are cleaned up at the next start)."""
        self.quitting = True
        log.info("Quitting (requested by macOS).")
        self.engine.stop_event.set()
        self.engine.notifier.flush()

    def quit(self) -> None:
        if self.quitting:
            return
        self.quitting = True
        log.info("Quitting.")
        self.engine.stop()
        if self.window:
            self.window.destroy()

    def _on_closing(self):
        if self.quitting:
            return True
        self.window.hide()
        return False  # keep running in the menu bar

    def _on_loaded(self):
        try:
            from webview.dom import DOMEventHandler
        except ImportError:
            return

        def on_drop(event):
            files = event.get("dataTransfer", {}).get("files", [])
            full = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
            result = self.api.convert_paths(full)
            self.window.evaluate_js(f"window.onFilesDropped && window.onFilesDropped({json_dumps(result)})")

        self.window.dom.document.events.dragover += DOMEventHandler(lambda e: None, True, True)
        self.window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)

    def _after_start(self) -> None:
        """Runs once the GUI loop is up (pywebview's start callback, own thread)."""
        self.sync_login_item()
        self.start_engine()
        if self.settings.current.general.check_for_updates:
            info = self.api.check_updates()
            if info.get("available"):
                macos.notify(APP_NAME, f"Version {info['latest']} is available - open the app to update.")


def free_port() -> int:
    """A port that's free on 127.0.0.1 for the window's local server. (pywebview's own pick
    checks "localhost", which can be IPv6, so it occasionally collides and the window stays blank.)"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def json_dumps(obj) -> str:
    import json
    return json.dumps(obj)


def run_app(background: bool = False) -> int:
    import webview
    import webview.platforms.cocoa  # noqa: F401  (sets up NSApplication)

    app = App(background)
    index = paths.resource("ui/web/index.html")
    app.window = webview.create_window(
        APP_NAME, url=str(index), js_api=app.api, width=1040, height=720, min_size=(720, 540),
        hidden=background, text_select=False, background_color="#F5F5F7",
    )
    app.window.events.closing += app._on_closing
    app.window.events.loaded += app._on_loaded

    from . import menubar
    menubar.install(app)

    def started():
        app._after_start()

    webview.start(started, private_mode=False, storage_path=str(paths.SUPPORT_DIR / "webview"),
                  http_port=free_port())
    app.engine.stop()
    return 0
