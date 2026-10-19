import pytest
from PIL import Image

from airdrop_compress.processors.base import Job, SkipFile
from airdrop_compress.processors.images import ImageProcessor, compare_formats
from airdrop_compress.settings import from_dict


def run(src, tmp_path, **image_settings):
    settings = from_dict({"images": image_settings}, strict=True)
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    for f in work.iterdir():
        f.unlink()
    return ImageProcessor().process(Job(src, work, settings))


@pytest.mark.parametrize("fmt,pil,ext", [("webp", "WEBP", ".webp"), ("avif", "AVIF", ".avif"), ("jpeg", "JPEG", ".jpg")])
def test_each_format(photo_jpeg, tmp_path, fmt, pil, ext):
    result = run(photo_jpeg, tmp_path, format=fmt)
    out = result.outputs[0]
    assert out.suffix == ext
    with Image.open(out.path) as im:
        assert im.format == pil
        assert im.size == (1200, 1600)  # orientation 6 baked in: portrait
    assert out.path.stat().st_size < photo_jpeg.stat().st_size


def test_heic_to_webp(photo_heic, tmp_path):
    out = run(photo_heic, tmp_path).outputs[0]
    with Image.open(out.path) as im:
        assert im.format == "WEBP" and im.size == (1200, 900)


def test_metadata_keep_location_strip(photo_jpeg, tmp_path):
    def exif_of(**kw):
        with Image.open(run(photo_jpeg, tmp_path, **kw).outputs[0].path) as im:
            return im.getexif(), im.info.get("icc_profile")

    exif, icc = exif_of(metadata="keep")
    assert exif.get(0x0110) == "iPhone 17 Pro" and 0x8825 in exif and icc
    exif, icc = exif_of(metadata="no_location")
    assert exif.get(0x0110) == "iPhone 17 Pro" and 0x8825 not in exif and icc
    exif, icc = exif_of(metadata="strip")
    assert len(exif) == 0 and icc  # colour profile is always kept unless converted to sRGB


def test_srgb_conversion_drops_profile(photo_jpeg, tmp_path):
    result = run(photo_jpeg, tmp_path, color="srgb")
    with Image.open(result.outputs[0].path) as im:
        assert "icc_profile" not in im.info
    assert "sRGB" in result.note


def test_max_dimension(photo_jpeg, tmp_path):
    with Image.open(run(photo_jpeg, tmp_path, max_dimension=800).outputs[0].path) as im:
        assert max(im.size) == 800


@pytest.mark.parametrize("fmt", ["webp", "avif", "jpeg"])
def test_target_size_is_met(photo_jpeg, tmp_path, fmt):
    result = run(photo_jpeg, tmp_path, format=fmt, target_size_kb=60)
    assert result.outputs[0].path.stat().st_size <= 60 * 1024


def test_target_size_shrinks_when_quality_isnt_enough(photo_jpeg, tmp_path):
    result = run(photo_jpeg, tmp_path, format="jpeg", target_size_kb=8)
    out = result.outputs[0].path
    assert out.stat().st_size <= 8 * 1024
    with Image.open(out) as im:
        assert max(im.size) < 1600
    assert "shrunk" in result.note


def test_auto_picks_smallest(photo_jpeg, tmp_path):
    result = run(photo_jpeg, tmp_path, format="auto")
    assert result.note.startswith("Auto:")
    sizes = {}
    for fmt in ("webp", "avif", "jpeg"):
        sizes[fmt] = run(photo_jpeg, tmp_path, format=fmt).outputs[0].path.stat().st_size
    best = min(sizes, key=sizes.get)
    assert result.outputs[0].suffix == {"webp": ".webp", "avif": ".avif", "jpeg": ".jpg"}[best]


def test_auto_never_picks_jpeg_for_transparency(alpha_png, tmp_path):
    result = run(alpha_png, tmp_path, format="auto")
    assert result.outputs[0].suffix in (".webp", ".avif")
    with Image.open(result.outputs[0].path) as im:
        assert im.mode == "RGBA"


def test_jpeg_flattens_transparency(alpha_png, tmp_path):
    result = run(alpha_png, tmp_path, format="jpeg")
    with Image.open(result.outputs[0].path) as im:
        assert im.mode == "RGB" and im.getpixel((5, 5)) == (255, 255, 255)
    assert "flattened" in result.note


def test_responsive_widths_and_fallback(photo_jpeg, tmp_path):
    result = run(photo_jpeg, tmp_path, responsive_widths=[480, 800, 4000], jpeg_fallback=True)
    suffixes = [o.suffix for o in result.outputs]
    assert suffixes == [".webp", "-480w.webp", "-800w.webp", ".jpg"]  # 4000 > image width: skipped
    with Image.open(result.outputs[1].path) as im:
        assert im.width == 480
    with Image.open(result.outputs[3].path) as im:
        assert im.format == "JPEG"


def test_animated_gif_stays_animated(animated_gif, tmp_path):
    for fmt in ("webp", "jpeg", "auto"):
        result = run(animated_gif, tmp_path, format=fmt)
        with Image.open(result.outputs[0].path) as im:
            assert im.format == "WEBP" and im.n_frames == 4
    assert "can't animate" in result.note


def test_png_lossless(alpha_png, tmp_path):
    result = run(alpha_png, tmp_path, png_lossless=True)
    with Image.open(result.outputs[0].path) as im, Image.open(alpha_png) as orig:
        assert im.convert("RGBA").tobytes() == orig.convert("RGBA").tobytes()


def test_skip_if_larger(tmp_path):
    tiny = tmp_path / "dot.png"
    Image.new("RGB", (1, 1)).save(tiny, optimize=True)
    with pytest.raises(SkipFile):
        run(tiny, tmp_path, skip_if_larger=True, format="jpeg")


def test_compare_formats(photo_jpeg, settings):
    res = compare_formats(photo_jpeg, settings)
    assert [r["format"] for r in res["rows"]] == ["webp", "avif", "jpeg"]
    assert sum(r["best"] for r in res["rows"]) >= 1
    assert res["original"] == photo_jpeg.stat().st_size
