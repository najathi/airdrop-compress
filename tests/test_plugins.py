import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from airdrop_compress.plugins.manager import PluginManager, load_manifest, sandbox_available
from airdrop_compress.processors.base import Job, SkipFile
from conftest import EXAMPLES

needs_sandbox = pytest.mark.skipif(not sandbox_available(), reason="sandbox-exec not available")

MANIFEST = {"id": "demo", "name": "Demo", "version": "1.0.0", "api_version": 1, "min_app_version": "2.0.0",
            "entry": "plugin.py", "file_types": [".txt"], "outputs": [".txt"], "permissions": [], "timeout": 20}


def make_plugin(root: Path, code: str, **manifest) -> Path:
    folder = root / manifest.get("id", "demo")
    folder.mkdir(parents=True)
    (folder / "plugin.json").write_text(json.dumps({**MANIFEST, **manifest}))
    (folder / "plugin.py").write_text(code)
    return folder


@pytest.fixture
def pm(tmp_path, settings_mgr):
    return PluginManager(settings_mgr, tmp_path / "plugins")


def run_plugin(pm, plugin_id, src, tmp_path):
    proc = next(p for p in pm.processors() if p.info.id == plugin_id)
    work = Path(tempfile.mkdtemp(dir=tmp_path))
    return proc.process(Job(src, work, pm.settings.current))


@pytest.mark.parametrize("change,error", [
    ({"id": "Bad Id"}, "'id'"),
    ({"version": "1"}, "'version'"),
    ({"file_types": []}, "file_types"),
    ({"outputs": ["png"]}, "outputs"),
    ({"permissions": ["root"]}, "unknown permissions"),
    ({"entry": "../evil.py"}, "entry file"),
    ({"timeout": 0}, "timeout"),
])
def test_manifest_validation(tmp_path, change, error):
    folder = make_plugin(tmp_path, "def process(ctx): pass", **change)
    info = load_manifest(folder)
    assert any(error in e for e in info.errors), info.errors


def test_compatibility(tmp_path, pm):
    make_plugin(pm.dir, "def process(ctx): pass", id="future-api", api_version=99)
    make_plugin(pm.dir, "def process(ctx): pass", id="future-app", min_app_version="99.0.0")
    pm.discover()
    assert {p["id"]: p["status"] for p in pm.to_ui()} == {"future-api": "incompatible", "future-app": "incompatible"}
    with pytest.raises(ValueError):
        pm.enable("future-api")


def test_off_until_approved_and_reapproval_after_change(pm):
    folder = make_plugin(pm.dir, "def process(ctx): pass")
    pm.discover()
    assert pm.status(pm.plugins["demo"]) == "disabled" and not pm.processors()
    pm.enable("demo")
    assert [p.id for p in pm.processors()] == ["plugin.demo"]
    (folder / "plugin.py").write_text("def process(ctx): print('changed')")
    pm.discover()
    assert pm.status(pm.plugins["demo"]) == "changed" and not pm.processors()


def test_settings_validation(pm):
    make_plugin(pm.dir, "def process(ctx): pass",
                settings=[{"key": "n", "type": "int", "default": 2, "min": 0, "max": 5},
                          {"key": "mode", "type": "choice", "options": ["a", "b"], "default": "a"}])
    pm.discover()
    assert pm.update_settings("demo", {"n": 4}) == {"n": 4, "mode": "a"}
    for bad in ({"n": 9}, {"n": "x"}, {"mode": "c"}, {"other": 1}):
        with pytest.raises(ValueError):
            pm.update_settings("demo", bad)


@needs_sandbox
def test_example_svg_plugin(pm, tmp_path):
    pm.install(EXAMPLES / "svg-minify")
    pm.enable("svg-minify")
    src = tmp_path / "logo.svg"
    src.write_text('<svg xmlns="http://www.w3.org/2000/svg">\n  <!-- c -->\n  <rect width="1.23456"/>\n</svg>\n')
    result = run_plugin(pm, "svg-minify", src, tmp_path)
    assert result.outputs[0].path.read_text() == '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1.23"/></svg>\n'


@needs_sandbox
def test_sandbox_blocks_everything_else(pm, tmp_path):
    secret = Path.home() / ".adc-test-secret"
    code = f'''
import os, socket, subprocess, pathlib
def process(ctx):
    results = {{}}
    def attempt(name, fn):
        try:
            fn(); results[name] = "allowed"
        except Exception as e:
            results[name] = "blocked"
    attempt("read_home", lambda: os.listdir(pathlib.Path.home().parent / {Path.home().name!r}))
    attempt("read_secret", lambda: open({str(secret)!r}).read())
    attempt("write_home", lambda: open({str(Path.home() / ".adc-test-pwned")!r}, "w").write("x"))
    attempt("write_tmp", lambda: open("/tmp/adc-test-pwned", "w").write("x"))
    attempt("network", lambda: socket.create_connection(("1.1.1.1", 443), timeout=3))
    attempt("subprocess", lambda: subprocess.run(["/bin/ls"], capture_output=True))
    attempt("read_input", lambda: ctx.input.read_text())
    ctx.output(".txt").write_text(repr(results))
'''
    secret.write_text("top secret")
    try:
        make_plugin(pm.dir, code)
        pm.discover()
        pm.enable("demo")
        src = tmp_path / "in.txt"
        src.write_text("input")
        results = eval(run_plugin(pm, "demo", src, tmp_path).outputs[0].path.read_text())
    finally:
        secret.unlink()
    assert results == {"read_home": "blocked", "read_secret": "blocked", "write_home": "blocked",
                       "write_tmp": "blocked", "network": "blocked", "subprocess": "blocked",
                       "read_input": "allowed"}
    assert not (Path.home() / ".adc-test-pwned").exists()


@needs_sandbox
def test_network_permission_is_honoured_in_profile(pm, tmp_path):
    from airdrop_compress.plugins.manager import sandbox_profile
    make_plugin(pm.dir, "def process(ctx): pass", permissions=["network"])
    pm.discover()
    profile = sandbox_profile(pm.plugins["demo"], tmp_path / "x", tmp_path)
    assert "(deny network*)" not in profile and "(deny process-exec*)" in profile
    assert "com.apple.dnssd.service" in profile and "(deny mach-lookup)" in profile


@needs_sandbox
def test_undeclared_output_type_is_rejected(pm, tmp_path):
    make_plugin(pm.dir, "def process(ctx):\n    ctx.output('.exe').write_text('x')\n")
    pm.discover()
    pm.enable("demo")
    src = tmp_path / "in.txt"
    src.write_text("x")
    with pytest.raises(RuntimeError, match="only declares"):
        run_plugin(pm, "demo", src, tmp_path)


@needs_sandbox
def test_skip_crash_and_timeout(pm, tmp_path):
    src = tmp_path / "in.txt"
    src.write_text("x")
    make_plugin(pm.dir, "def process(ctx):\n    ctx.skip('not today')\n", id="skipper")
    make_plugin(pm.dir, "def process(ctx):\n    raise ValueError('boom')\n", id="crasher")
    make_plugin(pm.dir, "import time\ndef process(ctx):\n    time.sleep(30)\n", id="sleeper", timeout=2)
    pm.discover()
    for pid in ("skipper", "crasher", "sleeper"):
        pm.enable(pid)
    with pytest.raises(SkipFile, match="not today"):
        run_plugin(pm, "skipper", src, tmp_path)
    with pytest.raises(RuntimeError, match="boom"):
        run_plugin(pm, "crasher", src, tmp_path)
    with pytest.raises(RuntimeError, match="longer than 2s"):
        run_plugin(pm, "sleeper", src, tmp_path)


def test_install_zip_and_reject_unsafe(pm, tmp_path):
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(good, "w") as z:
        for f in (EXAMPLES / "svg-minify").iterdir():
            z.write(f, f"svg-minify/{f.name}")
    assert pm.install(good).id == "svg-minify"
    with pytest.raises(FileExistsError):
        pm.install(good)
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../../escape.py", "x")
    with pytest.raises(ValueError, match="Unsafe path"):
        pm.install(evil)
    pm.remove("svg-minify")
    assert not (pm.dir / "svg-minify").exists()


@pytest.mark.parametrize("change,error", [
    ({"outputs": [".command"]}, "may not create"),
    ({"settings": [{"key": "n", "type": "int", "min": '"><img src=x onerror=alert(1)>'}]}, "whole number"),
    ({"settings": [{"key": "bad key!", "type": "bool"}]}, "letters, digits"),
    ({"settings": [{"key": "c", "type": "choice", "options": [1, 2]}]}, "options"),
    ({"settings": [{"key": "b", "type": "bool", "default": "yes"}]}, "default"),
])
def test_manifest_hardening(tmp_path, change, error):
    info = load_manifest(make_plugin(tmp_path, "def process(ctx): pass", **change))
    assert any(error in e for e in info.errors), info.errors


def test_folder_install_rejects_links(pm, tmp_path):
    folder = make_plugin(tmp_path / "src", "def process(ctx): pass")
    (folder / "key").symlink_to(Path.home() / ".ssh")
    with pytest.raises(ValueError, match="can't contain links"):
        pm.install(folder)


@needs_sandbox
def test_sandbox_blocks_clipboard_and_folder_listing(pm, tmp_path):
    code = f'''
import os
REAL_HOME = {str(Path.home())!r}
def process(ctx):
    r = {{}}
    try:
        import AppKit
        r["clipboard"] = AppKit.NSPasteboard.generalPasteboard().stringForType_(AppKit.NSPasteboardTypeString)
    except Exception:
        r["clipboard"] = None
    for name, path in (("home", REAL_HOME), ("inbox", str(ctx.input.parent)),
                       ("tmp", "/private/tmp"), ("shared", "/Users/Shared")):
        try:
            os.listdir(path); r[name] = "allowed"
        except Exception:
            r[name] = "blocked"
    ctx.output(".txt").write_text(repr(r))
'''
    make_plugin(pm.dir, code)
    pm.discover()
    pm.enable("demo")
    src = tmp_path / "in.txt"
    src.write_text("x")
    r = eval(run_plugin(pm, "demo", src, tmp_path).outputs[0].path.read_text())
    assert r == {"clipboard": None, "home": "blocked", "inbox": "blocked", "tmp": "blocked", "shared": "blocked"}
