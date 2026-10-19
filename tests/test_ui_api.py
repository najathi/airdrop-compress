"""The JavaScript bridge, tested without a window."""

import io
import json
import urllib.error

import pytest

from airdrop_compress import macos, paths
from airdrop_compress.activity import ActivityLog
from airdrop_compress.engine import Engine
from airdrop_compress.plugins.manager import PluginManager
from airdrop_compress.store import ProcessedStore
from airdrop_compress.ui import api as api_mod
from airdrop_compress.ui.api import Api
from conftest import EXAMPLES


class FakeApp:
    def __init__(self, settings, tmp_path):
        self.settings = settings
        self.plugins = PluginManager(settings, tmp_path / "plugins")
        self.engine = Engine(settings, self.plugins, ActivityLog(None), ProcessedStore(tmp_path / "p.json"))
        self.window = None
        self.quit_called = False
        self.uninstalling = False

    def status(self):
        return {**self.engine.status(), "paused": self.settings.current.general.paused}

    def quit(self):
        self.quit_called = True

    def legacy_resolved(self):
        pass


@pytest.fixture
def api(settings_mgr, tmp_path):
    return Api(FakeApp(settings_mgr, tmp_path))


def test_bootstrap_is_json_serialisable(api):
    data = api.bootstrap()
    json.dumps(data)
    assert data["settings"]["images"]["format"] == "webp"
    assert ".heic" in data["file_types"]["images"] and ".pdf" in data["file_types"]["documents"]


def test_save_settings_reports_errors(api):
    assert api.save_settings({"images": {"format": "avif"}})["ok"]
    bad = api.save_settings({"images": {"webp_quality": 500}})
    assert not bad["ok"] and "between 1 and 100" in bad["errors"][0]
    assert bad["settings"]["images"]["format"] == "avif"


def test_poll_only_sends_activity_when_changed(api):
    first = api.poll(-1)
    assert "activity" in first
    assert "activity" not in api.poll(first["revision"])


def test_plugin_lifecycle(api, tmp_path):
    res = api.install_plugin_path(str(EXAMPLES / "svg-minify"))
    assert res["ok"] and res["plugins"][0]["status"] == "disabled"
    assert api.install_plugin_path(str(EXAMPLES / "svg-minify"))["exists"]
    assert api.enable_plugin("svg-minify")["plugins"][0]["status"] == "ok"
    assert api.save_plugin_settings("svg-minify", {"precision": 3})["ok"]
    assert not api.save_plugin_settings("svg-minify", {"precision": 99})["ok"]
    assert api.disable_plugin("svg-minify")["plugins"][0]["status"] == "disabled"
    assert api.remove_plugin("svg-minify")["ok"] and api.list_plugins() == []


def test_convert_requires_running_engine(api, photo_jpeg):
    assert not api.convert_paths([str(photo_jpeg)])["ok"]


def test_update_check(monkeypatch):
    def fake_urlopen(req, timeout, context):
        body = {"tag_name": "v9.0.0", "html_url": "https://github.com/najathi/airdrop-compress/releases/tag/v9.0.0",
                "assets": [{"name": "AirDrop-Compress-9.0.0-arm64.dmg", "browser_download_url": "https://github.com/najathi/airdrop-compress/releases/download/v9.0.0/AirDrop-Compress-9.0.0-arm64.dmg"}]}
        return io.BytesIO(json.dumps(body).encode())
    monkeypatch.setattr(api_mod.urllib.request, "urlopen", fake_urlopen)
    info = api_mod.fetch_update_info()
    assert info["available"] and info["latest"] == "9.0.0" and info["url"].endswith("v9.0.0/AirDrop-Compress-9.0.0-arm64.dmg")

    def not_found(req, timeout, context):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
    monkeypatch.setattr(api_mod.urllib.request, "urlopen", not_found)
    assert api_mod.fetch_update_info()["available"] is False


def test_uninstall_removes_app_data_only(api, monkeypatch):
    calls = []
    monkeypatch.setattr(macos, "set_login_item", lambda enabled: calls.append(("login", enabled)))
    monkeypatch.setattr(macos, "remove_legacy_service", lambda: calls.append("legacy"))
    monkeypatch.setattr(macos, "move_to_trash", lambda p: calls.append("trash"))
    monkeypatch.setattr(api_mod.threading, "Timer", lambda *a, **k: type("T", (), {"start": lambda self: None})())
    paths.ensure_dirs()
    (paths.SUPPORT_DIR / "settings.json").write_text("{}")
    assert api.uninstall()["ok"]
    assert not paths.SUPPORT_DIR.exists()
    assert calls == [("login", False)]  # never the v1 service; no bundle to trash from source


def test_update_check_rejects_unexpected_data(monkeypatch):
    def fake(body):
        return lambda req, timeout, context: io.BytesIO(json.dumps(body).encode())
    monkeypatch.setattr(api_mod.urllib.request, "urlopen", fake({"tag_name": "v9.0.0; rm -rf ~"}))
    assert "error" in api_mod.fetch_update_info()
    monkeypatch.setattr(api_mod.urllib.request, "urlopen", fake({
        "tag_name": "v9.0.0", "html_url": "https://evil.example/x",
        "assets": [{"name": "a.dmg", "browser_download_url": "https://evil.example/a.dmg"}]}))
    info = api_mod.fetch_update_info()
    assert info["url"].startswith("https://github.com/najathi/airdrop-compress/")


def test_notifications_keep_unicode(monkeypatch):
    seen = []
    monkeypatch.setattr(macos.subprocess, "run", lambda args, **kw: seen.append(args))
    macos.notify("AirDrop Compress", "12 MB → 3 MB")
    assert "→" in seen[0][-1] and "\\u2192" not in seen[0][-1]
