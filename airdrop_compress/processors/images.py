"""Image conversion to WebP, AVIF or JPEG, following Google's image guidance:

- pick a modern format (WebP/AVIF), but keep JPEG available for compatibility;
  "auto" encodes each suitable format and keeps the smallest, because no single
  format wins for every image;
- size images for the web (max dimension, optional srcset widths, target size);
- keep colours right (ICC profile or convert to sRGB), drop metadata you don't need;
- descriptive, crawlable file names (lowercase-hyphenated) when SEO names are on.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageCms, ImageOps
from pillow_heif import register_heif_opener

from ..settings import ImageSettings, Settings
from .base import Job, Output, Result, SkipFile

register_heif_opener()

CANDIDATE_IMAGE_EXTS = {
    ".heic", ".heif", ".hif", ".jpg", ".jpeg", ".png",
    ".tif", ".tiff", ".bmp", ".gif", ".avif", ".webp",
}
# Only the formats this Pillow build can actually read.
IMAGE_EXTS = CANDIDATE_IMAGE_EXTS & set(Image.registered_extensions())
# Formats browsers already display - only for these can "skip if larger" keep the original.
WEB_NATIVE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}

FORMATS = {
    "webp": {"ext": ".webp", "label": "WebP", "pil": "WEBP", "alpha": True, "animation": True, "max_side": 16383},
    "avif": {"ext": ".avif", "label": "AVIF", "pil": "AVIF", "alpha": True, "animation": True, "max_side": 65536},
    "jpeg": {"ext": ".jpg", "label": "JPEG", "pil": "JPEG", "alpha": False, "animation": False, "max_side": 65500},
}
# Compression effort: WebP "method" (0-6, higher = smaller/slower), AVIF "speed" (0-10, lower = smaller/slower).
WEBP_METHOD = {"fast": 4, "balanced": 6, "best": 6}
AVIF_SPEED = {"fast": 8, "balanced": 6, "best": 3}
MIN_TARGET_QUALITY = 30   # below this, shrink the image instead of ruining its quality
GPS_IFD = 0x8825
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))


@dataclass
class Prepared:
    img: Image.Image
    has_alpha: bool
    exif: bytes | None
    icc: bytes | None
    xmp: bytes | None
    notes: list[str]


def quality_for(fmt: str, s: ImageSettings) -> int:
    return {"webp": s.webp_quality, "avif": s.avif_quality, "jpeg": s.jpeg_quality}[fmt]


def flatten(img: Image.Image, background=(255, 255, 255)) -> Image.Image:
    if img.mode == "RGB":
        return img
    rgba = img.convert("RGBA")
    base = Image.new("RGB", rgba.size, background)
    base.paste(rgba, mask=rgba.getchannel("A"))
    return base


def prepare(im: Image.Image, s: ImageSettings) -> Prepared:
    """Orientation, colour, size and metadata - everything before encoding."""
    notes: list[str] = []
    icc = im.info.get("icc_profile")
    xmp = im.info.get("xmp")
    if isinstance(xmp, str):
        xmp = xmp.encode()

    img = ImageOps.exif_transpose(im)  # bake the iPhone rotation into the pixels
    has_alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
    if img.mode not in ("RGB", "RGBA") or (has_alpha and img.mode != "RGBA"):
        img = img.convert("RGBA" if has_alpha else "RGB")
    if has_alpha and img.getchannel("A").getextrema() == (255, 255):
        img, has_alpha = img.convert("RGB"), False  # alpha channel that's fully opaque

    if s.color == "srgb" and icc:
        try:
            img = ImageCms.profileToProfile(
                img, ImageCms.ImageCmsProfile(io.BytesIO(icc)), SRGB, outputMode=img.mode)
            icc = None  # untagged images are treated as sRGB by browsers
            notes.append("converted to sRGB")
        except (ImageCms.PyCMSError, OSError):
            pass  # unreadable profile - keep it as is

    if s.max_dimension and max(img.size) > s.max_dimension:
        img.thumbnail((s.max_dimension, s.max_dimension), Image.Resampling.LANCZOS)
        notes.append(f"resized to {img.width}×{img.height}")

    exif_obj = img.getexif()
    if s.metadata == "strip":
        exif = xmp = None
    else:
        if s.metadata == "no_location":
            if GPS_IFD in exif_obj:
                del exif_obj[GPS_IFD]
            xmp = None  # XMP can also carry the location
        exif = exif_obj.tobytes() if len(exif_obj) else None
    return Prepared(img, has_alpha, exif, icc, xmp, notes)


def encode(img: Image.Image, fmt: str, quality: int, s: ImageSettings, p: Prepared,
           lossless: bool = False) -> bytes:
    info = FORMATS[fmt]
    if max(img.size) > info["max_side"]:
        img = img.copy()
        img.thumbnail((info["max_side"], info["max_side"]), Image.Resampling.LANCZOS)
    opts: dict = {}
    if fmt == "jpeg":
        img = flatten(img)
        opts = {"quality": quality, "optimize": True, "progressive": s.jpeg_progressive,
                # 4:4:4 chroma at high quality keeps red/blue edges crisp
                "subsampling": 0 if quality >= 90 else 2}
    elif fmt == "webp":
        opts = {"quality": quality, "method": WEBP_METHOD[s.effort], "lossless": lossless}
    elif fmt == "avif":
        opts = {"quality": quality, "speed": AVIF_SPEED[s.effort]}
    if p.exif:
        opts["exif"] = p.exif
    if p.icc:
        opts["icc_profile"] = p.icc
    if p.xmp:
        opts["xmp"] = p.xmp
    buf = io.BytesIO()
    img.save(buf, info["pil"], **opts)
    return buf.getvalue()


def fit_to_size(img: Image.Image, fmt: str, s: ImageSettings, p: Prepared, target: int,
                max_quality: int) -> tuple[bytes, int, Image.Image, bool]:
    """Highest quality that fits in `target` bytes; shrinks the image if even
    quality 30 is too big. Returns (data, quality, image used, reached target)."""
    data = encode(img, fmt, max_quality, s, p)
    if len(data) <= target:
        return data, max_quality, img, True
    smallest = (data, max_quality, img)
    for _ in range(6):
        lo, hi, best = MIN_TARGET_QUALITY, max_quality, None
        while lo <= hi:
            mid = (lo + hi) // 2
            d = encode(img, fmt, mid, s, p)
            if len(d) <= target:
                best, lo = (d, mid), mid + 1
            else:
                hi = mid - 1
                if len(d) < len(smallest[0]):
                    smallest = (d, mid, img)
        if best:
            return best[0], best[1], img, True
        if min(img.size) < 64:
            break
        # Shrink by the square root of how far off we are (file size ~ pixel count).
        ratio = max(0.5, (target / len(smallest[0])) ** 0.5 * 0.95)
        img = img.resize((max(1, round(img.width * ratio)), max(1, round(img.height * ratio))),
                         Image.Resampling.LANCZOS)
    return smallest[0], smallest[1], smallest[2], False


def human(n: float) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def candidate_formats(s: ImageSettings, has_alpha: bool) -> list[str]:
    if s.format != "auto":
        return [s.format]
    return ["webp", "avif"] if has_alpha else ["webp", "avif", "jpeg"]


def encode_best(p: Prepared, src: Path, s: ImageSettings) -> tuple[str, bytes, int, Image.Image, list[str]]:
    """Encode in the chosen format (or every candidate for auto). Returns
    (format, data, quality, image used, notes)."""
    notes = list(p.notes)
    results: dict[str, tuple[bytes, int, Image.Image]] = {}
    for fmt in candidate_formats(s, p.has_alpha):
        q = quality_for(fmt, s)
        lossless = s.png_lossless and fmt == "webp" and src.suffix.lower() == ".png"
        if s.target_size_kb and not lossless:
            data, q, used, ok = fit_to_size(p.img, fmt, s, p, s.target_size_kb * 1024, q)
            if not ok:
                notes.append(f"couldn't reach {s.target_size_kb} KB")
            elif used is not p.img:
                notes.append(f"shrunk to {used.width}×{used.height} to fit {s.target_size_kb} KB")
        else:
            data, used = encode(p.img, fmt, q, s, p, lossless=lossless), p.img
            if lossless:
                notes.append("lossless")
        results[fmt] = (data, q, used)
    best = min(results, key=lambda f: len(results[f][0]))
    if len(results) > 1:
        ranking = " < ".join(f"{FORMATS[f]['label']} {human(len(results[f][0]))}"
                             for f in sorted(results, key=lambda f: len(results[f][0])))
        notes.insert(0, f"Auto: {ranking}")
    if s.format == "jpeg" and p.has_alpha:
        notes.append("transparency flattened onto white")
    data, q, used = results[best]
    return best, data, q, used, notes


class ImageProcessor:
    id = "builtin.images"
    name = "Image converter"
    kind = "image"

    def handles(self, path: Path, settings: Settings) -> bool:
        return settings.images.enabled and path.suffix.lower() in IMAGE_EXTS

    def process(self, job: Job) -> Result:
        s = job.settings.images
        src_size = job.src.stat().st_size
        with Image.open(job.src) as im:
            if getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1:
                return self._animated(im, job, s)
            p = prepare(im, s)
        fmt, data, quality, used, notes = encode_best(p, job.src, s)

        if s.skip_if_larger and job.src.suffix.lower() in WEB_NATIVE_EXTS and len(data) >= src_size:
            raise SkipFile(f"the original ({human(src_size)}) is already smaller than "
                           f"the {FORMATS[fmt]['label']} result ({human(len(data))})")

        ext = FORMATS[fmt]["ext"]
        outputs = [self._write(job, f"main{ext}", data, ext, FORMATS[fmt]["label"])]

        for width in s.responsive_widths:
            if width >= used.width:
                continue
            height = max(1, round(used.height * width / used.width))
            resized = used.resize((width, height), Image.Resampling.LANCZOS)
            outputs.append(self._write(job, f"{width}w{ext}", encode(resized, fmt, quality, s, p),
                                       f"-{width}w{ext}", f"{width}w"))

        if s.jpeg_fallback and fmt != "jpeg":
            outputs.append(self._write(job, "fallback.jpg", encode(used, "jpeg", s.jpeg_quality, s, p),
                                       ".jpg", "JPEG fallback"))
        return Result(outputs, note=", ".join(notes))

    def _animated(self, im: Image.Image, job: Job, s: ImageSettings) -> Result:
        # Animation survives in WebP and AVIF only; "auto" and JPEG fall back to WebP.
        fmt = s.format if s.format in ("webp", "avif") else "webp"
        opts: dict = {"save_all": True, "quality": quality_for(fmt, s), "loop": im.info.get("loop", 0)}
        if fmt == "webp":
            opts["method"] = WEBP_METHOD[s.effort]
        else:
            opts["speed"] = AVIF_SPEED[s.effort]
        buf = io.BytesIO()
        im.save(buf, FORMATS[fmt]["pil"], **opts)
        ext = FORMATS[fmt]["ext"]
        note = "animated" + ("" if s.format == fmt else f" (kept as {FORMATS[fmt]['label']} - "
                                                        f"{FORMATS.get(s.format, {}).get('label', 'Auto')} "
                                                        "can't animate)")
        return Result([self._write(job, f"main{ext}", buf.getvalue(), ext, FORMATS[fmt]["label"])], note=note)

    @staticmethod
    def _write(job: Job, name: str, data: bytes, suffix: str, label: str) -> Output:
        path = job.workdir / name
        path.write_bytes(data)
        return Output(path, suffix, label)


def compare_formats(src: Path, settings: Settings) -> dict:
    """Encode one image in every format with the current settings, for the
    "Compare formats" tool. Nothing is written to disk."""
    s = settings.images
    with Image.open(src) as im:
        animated = getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1
        p = prepare(im, s)
    rows = []
    for fmt, info in FORMATS.items():
        if fmt == "jpeg" and p.has_alpha:
            note = "no transparency (flattened)"
        elif animated and not info["animation"]:
            note = "no animation (first frame only)"
        else:
            note = ""
        q = quality_for(fmt, s)
        start = time.perf_counter()
        if s.target_size_kb:
            data, q, used, ok = fit_to_size(p.img, fmt, s, p, s.target_size_kb * 1024, q)
            if not ok:
                note = (note + "; " if note else "") + "target not reached"
        else:
            data = encode(p.img, fmt, q, s, p)
        rows.append({"format": fmt, "label": info["label"], "size": len(data), "quality": q,
                     "ms": round((time.perf_counter() - start) * 1000), "note": note})
    best = min(r["size"] for r in rows)
    for r in rows:
        r["best"] = r["size"] == best
    return {"name": src.name, "original": src.stat().st_size, "width": p.img.width,
            "height": p.img.height, "has_alpha": p.has_alpha, "animated": animated, "rows": rows}
