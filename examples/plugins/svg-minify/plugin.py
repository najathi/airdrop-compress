"""SVG Minifier - an example AirDrop Compress plugin.

Removes comments, editor metadata (Inkscape, Illustrator, Sketch), and extra
whitespace, and rounds long decimal numbers. Pure Python, no permissions needed.
"""

import re

EDITOR_NAMESPACES = ("inkscape", "sodipodi", "sketch", "illustrator", "serif")


def minify(svg: str, keep_comments: bool, precision: int) -> str:
    if not keep_comments:
        svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
    svg = re.sub(r"<metadata\b.*?</metadata>", "", svg, flags=re.S | re.I)
    for ns in EDITOR_NAMESPACES:
        svg = re.sub(rf"<{ns}:[^>]*/>", "", svg)
        svg = re.sub(rf"<{ns}:.*?</{ns}:[^>]*>", "", svg, flags=re.S)
        svg = re.sub(rf'\s{ns}:[\w-]+="[^"]*"', "", svg)
        svg = re.sub(rf'\sxmlns:{ns}="[^"]*"', "", svg)
    svg = re.sub(r"\d+\.\d{%d,}" % (precision + 1),
                 lambda m: f"{float(m.group()):.{precision}f}".rstrip("0").rstrip("."), svg)
    svg = re.sub(r">\s+<", "><", svg)
    svg = re.sub(r"\s{2,}", " ", svg)
    return svg.strip() + "\n"


def process(ctx):
    original = ctx.input.read_text(encoding="utf-8")
    if "<svg" not in original:
        ctx.skip("not an SVG document")
    result = minify(original, ctx.settings.get("keep_comments", False), ctx.settings.get("precision", 2))
    ctx.output(".svg", label="Minified SVG").write_text(result, encoding="utf-8")
    ctx.log(f"{len(original)} -> {len(result)} bytes")
