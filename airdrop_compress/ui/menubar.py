"""The menu bar item (NSStatusItem) - status at a glance, pause/resume, quick actions."""

from __future__ import annotations

import logging

import AppKit
import Foundation
import objc
from PyObjCTools import AppHelper

from .. import APP_NAME
from ..processors.images import human

log = logging.getLogger("airdrop-compress")

ICONS = {
    "running": "arrow.down.circle",
    "busy": "arrow.down.circle.fill",
    "paused": "pause.circle",
    "problem": "exclamationmark.circle",
}
STATE_TEXT = {
    "running": "Watching for AirDrop files",
    "starting": "Starting…",
    "paused": "Paused",
    "stopped": "Stopped",
    "waiting_access": "Needs folder permission",
    "locked": "Another copy is running",
    "legacy": "Action needed - open the dashboard",
    "error": "Something went wrong",
}


class MenuController(AppKit.NSObject):
    def initWithApp_(self, app):
        self = objc.super(MenuController, self).init()
        if self is None:
            return None
        self.app = app
        self.icon_key = None
        bar = AppKit.NSStatusBar.systemStatusBar()
        self.item = bar.statusItemWithLength_(AppKit.NSVariableStatusItemLength)
        self.item.button().setToolTip_(APP_NAME)
        self.menu = AppKit.NSMenu.alloc().init()
        self.menu.setAutoenablesItems_(False)
        self.menu.setDelegate_(self)
        self.item.setMenu_(self.menu)
        self.refreshIcon_(None)
        self.timer = Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            2.0, self, "refreshIcon:", None, True)
        return self

    # -- icon --------------------------------------------------------------- #

    def refreshIcon_(self, _timer):
        status = self.app.status()
        stats = self.app.engine.activity.stats()
        state = status["state"]
        if state in ("paused", "stopped"):
            key = "paused"
        elif state in ("waiting_access", "locked", "legacy", "error"):
            key = "problem"
        elif stats["busy"]:
            key = "busy"
        else:
            key = "running"
        if key != self.icon_key:
            image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(ICONS[key], APP_NAME)
            if image:
                image.setTemplate_(True)
                self.item.button().setImage_(image)
            else:
                self.item.button().setTitle_("AC")
            self.icon_key = key

    # -- menu --------------------------------------------------------------- #

    def menuNeedsUpdate_(self, menu):
        menu.removeAllItems()
        status = self.app.status()
        stats = self.app.engine.activity.stats()
        today = stats["today"]

        def info(text):
            it = menu.addItemWithTitle_action_keyEquivalent_(text, None, "")
            it.setEnabled_(False)

        def action(title, selector, key=""):
            it = menu.addItemWithTitle_action_keyEquivalent_(title, selector, key)
            it.setTarget_(self)
            return it

        info(STATE_TEXT.get(status["state"], status["state"]))
        if stats["busy"]:
            info(f"Processing {stats['busy']} file{'s' if stats['busy'] != 1 else ''}…")
        saved = max(0, today["before"] - today["after"])
        info(f"Today: {today['files']} file{'s' if today['files'] != 1 else ''}"
             + (f" · {human(saved)} saved" if saved else ""))
        menu.addItem_(AppKit.NSMenuItem.separatorItem())
        if status["state"] in ("paused", "stopped"):
            action("Resume", "resume:")
        elif status["state"] == "running":
            action("Pause", "pause:")
        action("Open Dashboard…", "openDashboard:", ",")
        action("Open Output Folder", "openOutput:")
        action("Convert Files…", "convertFiles:")
        menu.addItem_(AppKit.NSMenuItem.separatorItem())
        action(f"Quit {APP_NAME}", "quit:", "q")

    def pause_(self, _):
        self.app.engine.pause()

    def resume_(self, _):
        self.app.engine.resume()

    def openDashboard_(self, _):
        self.app.show_window()

    def openOutput_(self, _):
        self.app.api.open_folder("output")

    def convertFiles_(self, _):
        self.app.show_window()
        AppHelper.callLater(0.3, lambda: self.app.window.evaluate_js("window.convertFiles && window.convertFiles()"))

    def quit_(self, _):
        self.app.quit()


def _handle_reopen(app):
    """Show the window when the app is opened again from Finder/Launchpad."""
    try:
        from webview.platforms.cocoa import BrowserView
    except ImportError:
        return

    def applicationShouldHandleReopen_hasVisibleWindows_(self, ns_app, has_visible):
        app.show_window()
        return True

    objc.classAddMethods(BrowserView.AppDelegate, [objc.selector(
        applicationShouldHandleReopen_hasVisibleWindows_,
        selector=b"applicationShouldHandleReopen:hasVisibleWindows:", signature=b"Z@:@Z")])


def install(app) -> None:
    ns_app = AppKit.NSApplication.sharedApplication()
    # Menu bar app: no Dock icon (the packaged app also sets LSUIElement).
    ns_app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    _handle_reopen(app)

    def create():
        app.menu_bar = MenuController.alloc().initWithApp_(app)

    AppHelper.callAfter(create)
