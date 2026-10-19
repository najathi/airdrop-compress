#!/usr/bin/env python3
"""Build the website into _site/ (see docs/DEPLOYMENT.md).

    python site/build.py            # SITE_URL defaults to the GitHub Pages address

- copies site/ (landing page, assets) to _site/ and fills in {{placeholders}};
- renders the Markdown documentation into _site/docs/*.html;
- writes sitemap.xml, robots.txt and JSON-LD structured data.
"""

from __future__ import annotations

import html
import json
import os
import posixpath
import re
import shutil
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import markdown

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
OUT = ROOT / "_site"
REPO = "najathi/airdrop-compress"
REPO_URL = f"https://github.com/{REPO}"
SITE_URL = (os.environ.get("SITE_URL") or "https://najathi.github.io/airdrop-compress/").rstrip("/") + "/"
DMG_URL = f"{REPO_URL}/releases/latest/download/AirDrop-Compress-arm64.dmg"
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "airdrop_compress/__init__.py").read_text()).group(1)

# (source file, slug, nav title, group)
PAGES = [
    ("docs/INSTALL.md", "install", "Install", "Using the app"),
    ("docs/USER_GUIDE.md", "user_guide", "User guide", "Using the app"),
    ("docs/FORMATS.md", "formats", "Formats & options", "Using the app"),
    ("docs/TROUBLESHOOTING.md", "troubleshooting", "Troubleshooting", "Using the app"),
    ("docs/FAQ.md", "faq", "FAQ", "Using the app"),
    ("docs/PLUGINS.md", "plugins", "Plugin guide", "Developers"),
    ("docs/ARCHITECTURE.md", "architecture", "Architecture", "Developers"),
    ("CONTRIBUTING.md", "contributing", "Contributing", "Developers"),
    ("docs/RELEASING.md", "releasing", "Building & releasing", "Developers"),
    ("docs/DEPLOYMENT.md", "deployment", "Website deployment", "Developers"),
    ("SECURITY.md", "security", "Security policy", "Project"),
    ("docs/SECURITY_AUDIT.md", "security_audit", "Security audit", "Project"),
    ("CHANGELOG.md", "changelog", "Changelog", "Project"),
]
SOURCE_TO_SLUG = {src: slug for src, slug, _, _ in PAGES}
EXCLUDE = {"build.py", "tools", "docs_template.html", "__pycache__", ".DS_Store"}


def fill(text: str, **extra: str) -> str:
    values = {"SITE_URL": SITE_URL, "VERSION": VERSION, "DMG_URL": DMG_URL,
              "RELEASES_URL": f"{REPO_URL}/releases", "SITE_PATH": urlsplit(SITE_URL).path, **extra}
    return re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: values.get(m.group(1), m.group(0)), text)


def rewrite_links(body: str, source: str) -> str:
    """Point links at other docs to their .html pages, and other repo files to GitHub."""
    base = posixpath.dirname(source)

    def fix(m: re.Match) -> str:
        attr, url = m.group(1), html.unescape(m.group(2))
        if re.match(r"^[a-z][a-z0-9+.-]*:|^#|^//", url):
            return m.group(0)
        path, _, fragment = url.partition("#")
        target = posixpath.normpath(posixpath.join(base, path)) if path else source
        if target in SOURCE_TO_SLUG:
            new = f"{SOURCE_TO_SLUG[target]}.html"
        elif target.startswith(".."):
            return m.group(0)
        else:
            kind = "tree" if (ROOT / target).is_dir() else "blob"
            new = f"{REPO_URL}/{kind}/main/{target}"
        if fragment:
            new += f"#{fragment}"
        return f'{attr}="{html.escape(new, quote=True)}"'

    return re.sub(r'(href|src)="([^"]*)"', fix, body)


def render_markdown(text: str) -> tuple[str, str]:
    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists", "toc"],
                           extension_configs={"toc": {"permalink": "#", "permalink_title": "Link to this section"}})
    return md.convert(text), md.toc


def docs_nav(current: str) -> str:
    parts, group = ['<a href="./"' + (' aria-current="page"' if current == "index" else "") + ">Overview</a>"], None
    for _, slug, title, g in PAGES:
        if g != group:
            parts.append(f"<h4>{html.escape(g)}</h4>")
            group = g
        cur = ' aria-current="page"' if slug == current else ""
        parts.append(f'<a href="{slug}.html"{cur}>{html.escape(title)}</a>')
    return "\n".join(parts)


def first_paragraph(body: str) -> str:
    m = re.search(r"<p>(.*?)</p>", body, re.S)
    text = re.sub(r"<[^>]+>", "", m.group(1)) if m else ""
    return html.unescape(" ".join(text.split()))[:155]


def build_docs(template: str) -> list[str]:
    (OUT / "docs").mkdir(parents=True, exist_ok=True)
    urls = []
    for source, slug, title, group in PAGES:
        body, _toc = render_markdown((ROOT / source).read_text())
        body = rewrite_links(body, source)
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
        page_title = re.sub(r"<[^>]+>", "", h1.group(1)).replace("#", "").strip() if h1 else title
        page = fill(template, TITLE=html.escape(page_title), DESCRIPTION=html.escape(first_paragraph(body) or title),
                    NAV=docs_nav(slug), CONTENT=body, CANONICAL=f"{SITE_URL}docs/{slug}.html",
                    EDIT_URL=f"{REPO_URL}/edit/main/{source}")
        (OUT / "docs" / f"{slug}.html").write_text(page)
        urls.append(f"docs/{slug}.html")

    # Docs home: cards grouped like the sidebar.
    groups: dict[str, list[str]] = {}
    for source, slug, title, group in PAGES:
        body, _ = render_markdown((ROOT / source).read_text())
        blurb = html.escape(first_paragraph(body))
        groups.setdefault(group, []).append(
            f'<a class="support-card" href="{slug}.html"><h3>{html.escape(title)}</h3><p>{blurb}</p></a>')
    content = ("<h1>Documentation</h1><p class=\"lead\">Everything about installing, using and extending "
               "AirDrop Compress.</p>" + "".join(
                   f"<h2>{html.escape(g)}</h2><div class=\"docs-cards\">{''.join(cards)}</div>"
                   for g, cards in groups.items()))
    page = fill(template, TITLE="Documentation", NAV=docs_nav("index"), CONTENT=content,
                DESCRIPTION="Install, user guide, supported formats, troubleshooting, FAQ and developer documentation for AirDrop Compress.",
                CANONICAL=f"{SITE_URL}docs/", EDIT_URL=f"{REPO_URL}/tree/main/docs")
    (OUT / "docs" / "index.html").write_text(page)
    return ["docs/"] + urls


def json_ld(index_html: str) -> str:
    app = {
        "@context": "https://schema.org", "@type": "SoftwareApplication",
        "name": "AirDrop Compress", "operatingSystem": "macOS 12 or later",
        "applicationCategory": "UtilitiesApplication", "softwareVersion": VERSION,
        "description": "Automatically converts photos and documents received via AirDrop into compressed WebP, AVIF or JPEG images and Markdown.",
        "url": SITE_URL, "downloadUrl": DMG_URL, "image": f"{SITE_URL}assets/img/og-image.png",
        "license": "https://opensource.org/licenses/MIT", "isAccessibleForFree": True,
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        "author": {"@type": "Person", "name": "Najathi", "url": "https://github.com/najathi",
                   "sameAs": ["https://github.com/najathi", "https://www.linkedin.com/in/najathi/",
                              "https://stackoverflow.com/users/9181204/najathi"]},
    }
    faq_section = re.search(r'<section[^>]*id="faq".*?</section>', index_html, re.S).group(0)
    qa = []
    for q, a in re.findall(r"<details><summary>(.*?)</summary><p>(.*?)</p></details>", faq_section, re.S):
        clean = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s)).strip()  # noqa: E731
        qa.append({"@type": "Question", "name": clean(q), "acceptedAnswer": {"@type": "Answer", "text": clean(a)}})
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": qa}
    blocks = [json.dumps(x, ensure_ascii=False).replace("</", "<\\/") for x in (app, faq)]
    return "\n".join(f'<script type="application/ld+json">{b}</script>' for b in blocks)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE, OUT, ignore=lambda d, names: [n for n in names if n in EXCLUDE])

    index = (OUT / "index.html").read_text()
    (OUT / "index.html").write_text(fill(index, JSONLD=json_ld(index)))
    for page in ("404.html",):
        if (OUT / page).exists():
            (OUT / page).write_text(fill((OUT / page).read_text()))

    urls = [""] + build_docs((SITE / "docs_template.html").read_text())
    today = date.today().isoformat()
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{SITE_URL}{u}</loc><lastmod>{today}</lastmod></url>\n" for u in urls)
        + "</urlset>\n")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n")
    (OUT / ".nojekyll").write_text("")

    leftovers = [str(p.relative_to(OUT)) for p in OUT.rglob("*.html") if re.search(r"\{\{[A-Z_]+\}\}", p.read_text())]
    if leftovers:
        raise SystemExit(f"Unfilled placeholders in: {', '.join(leftovers)}")
    print(f"Built {len(urls)} pages into {OUT} for {SITE_URL} (version {VERSION})")


if __name__ == "__main__":
    main()
