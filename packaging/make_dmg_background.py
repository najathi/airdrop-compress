"""Draws the .dmg window background (1x and @2x) - called by packaging/build.sh.

The layout must match packaging/dmg_settings.py: a 660x500 window, the app icon
at (165, 175), Applications at (495, 175) and the "How to open" guide at (330, 330).
It leaves room at the bottom for Finder's tab bar, which some people keep switched on.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 660, 500
APP, APPS, GUIDE = (165, 175), (495, 175), (330, 330)
FONT = "/System/Library/Fonts/SFNS.ttf"


def font(size: int, weight: str) -> ImageFont.FreeTypeFont:
    try:
        f = ImageFont.truetype(FONT, size)
        f.set_variation_by_name(weight)
        return f
    except (OSError, ValueError):
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)


def draw(scale: int) -> Image.Image:
    s = lambda v: round(v * scale)  # noqa: E731
    img = Image.new("RGB", (s(W), s(H)))
    # soft vertical gradient
    top, bottom = (250, 251, 255), (232, 238, 252)
    px = img.load()
    for y in range(s(H)):
        t = y / (s(H) - 1)
        c = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        for x in range(s(W)):
            px[x, y] = c

    # subtle glow behind the two drop targets
    glow = Image.new("L", img.size, 0)
    g = ImageDraw.Draw(glow)
    for cx, cy in (APP, APPS):
        g.ellipse([s(cx - 78), s(cy - 78), s(cx + 78), s(cy + 78)], fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(s(26)))
    img.paste(Image.new("RGB", img.size, (255, 255, 255)), mask=glow)

    d = ImageDraw.Draw(img)
    title = font(s(22), b"Semibold")
    body = font(s(13), b"Regular")
    small = font(s(12), b"Medium")
    ink, muted, accent = (29, 29, 31), (110, 110, 115), (10, 122, 255)

    d.text((s(W / 2), s(52)), "Drag AirDrop Compress to Applications", font=title, fill=ink, anchor="mm")
    d.text((s(W / 2), s(80)), "Then open it from your Applications folder.", font=body, fill=muted, anchor="mm")

    # arrow between the icons
    y = s(APP[1] - 8)
    x0, x1 = s(APP[0] + 82), s(APPS[0] - 82)
    d.line([(x0, y), (x1 - s(12), y)], fill=accent, width=s(5))
    d.polygon([(x1, y), (x1 - s(18), y - s(11)), (x1 - s(18), y + s(11))], fill=accent)

    # divider + first-launch hint above the guide icon
    d.line([(s(80), s(255)), (s(W - 80), s(255))], fill=(214, 220, 235), width=s(1))
    d.text((s(W / 2), s(275)), "Opening it for the first time? macOS will ask you to confirm - here's how:", font=small, fill=muted, anchor="mm")
    return img


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    draw(1).save(out / "background.png", dpi=(72, 72))
    draw(2).save(out / "background@2x.png", dpi=(144, 144))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build/dmg-assets")
