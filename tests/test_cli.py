import subprocess
import sys
from pathlib import Path

from conftest import EXAMPLES

ROOT = Path(__file__).resolve().parent.parent


def cli(*args):
    return subprocess.run([sys.executable, "-m", "airdrop_compress", *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)


def test_version():
    r = cli("--version")
    assert r.returncode == 0 and "AirDrop Compress 2." in r.stdout


def test_plugin_validate():
    ok = cli("plugin", "validate", str(EXAMPLES / "svg-minify"))
    assert ok.returncode == 0 and "SVG Minifier" in ok.stdout
    bad = cli("plugin", "validate", str(ROOT))
    assert bad.returncode == 1 and "plugin.json is missing" in bad.stdout


def test_settings_command():
    r = cli("settings")
    assert r.returncode == 0 and '"format": "webp"' in r.stdout
