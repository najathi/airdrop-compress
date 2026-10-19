"""Shared fixtures. App data goes to a temporary folder, never ~/Library."""

import os
import tempfile
from pathlib import Path

# Must happen before airdrop_compress is imported (paths are resolved at import time).
_HOME = Path(tempfile.mkdtemp(prefix="adc-test-home-"))
os.environ["AIRDROP_COMPRESS_HOME"] = str(_HOME)
os.environ.pop("AIRDROP_DIR", None)

import pytest  # noqa: E402
from PIL import Image, ImageCms  # noqa: E402

from airdrop_compress.settings import Settings, SettingsManager  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "plugins"


@pytest.fixture
def settings_mgr(tmp_path):
    return SettingsManager(tmp_path / "settings.json")


@pytest.fixture
def settings():
    return Settings()


def _gradient(size=(1600, 1200)):
    """A photo-like image (smooth gradients + noise) so codecs behave realistically."""
    w, h = size
    img = Image.radial_gradient("L").resize(size)
    r = Image.linear_gradient("L").resize(size)
    noise = Image.effect_noise(size, 40)
    return Image.merge("RGB", (img, r, noise))


@pytest.fixture
def photo_jpeg(tmp_path):
    """JPEG with EXIF (camera, GPS, orientation=6) and a Display P3-like ICC profile."""
    img = _gradient()
    exif = Image.Exif()
    exif[0x010F] = "Apple"
    exif[0x0110] = "iPhone 17 Pro"
    exif[0x0112] = 6  # rotate 90° CW when displayed
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (51.0, 30.0, 0.0)
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    path = tmp_path / "IMG_0001.JPG"
    img.save(path, quality=95, exif=exif, icc_profile=icc)
    return path


@pytest.fixture
def photo_heic(tmp_path):
    from pillow_heif import register_heif_opener
    register_heif_opener()
    path = tmp_path / "IMG_0002.HEIC"
    _gradient((1200, 900)).save(path, quality=90)
    return path


@pytest.fixture
def alpha_png(tmp_path):
    img = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
    img.paste((30, 120, 220, 255), (50, 50, 350, 250))
    path = tmp_path / "logo.png"
    img.save(path)
    return path


@pytest.fixture
def animated_gif(tmp_path):
    frames = [Image.new("RGB", (120, 80), c) for c in [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]]
    path = tmp_path / "anim.gif"
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)
    return path
