#!/usr/bin/env python3
"""Check every link in the built site (_site/). Internal links and #anchors must resolve.

    python site/tools/check_links.py            # internal only
    python site/tools/check_links.py --external # also request external URLs (needs network)
"""
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urldefrag, urljoin, urlsplit

OUT = Path(__file__).resolve().parents[2] / "_site"


class Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for key in ("href", "src", "srcset"):
            if key in a and a[key] and tag not in ("meta", "base") and a.get("rel") != "canonical":
                self.links.append(a[key].split(" ")[0])


pages = {}
for f in OUT.rglob("*.html"):
    c = Collector()
    c.feed(f.read_text())
    pages[f] = c

errors, external = [], set()
for f, c in pages.items():
    base = "file://" + str(f)
    for link in c.links:
        if link.startswith(("mailto:", "data:")) or "{{" in link:
            continue
        if link.startswith(("http://", "https://")):
            external.add(link)
            continue
        target, frag = urldefrag(urljoin(base, link))
        path = Path(unquote(urlsplit(target).path))
        if f.name == "404.html":
            path = OUT / link.split("#")[0]
        if path.is_dir():
            path = path / "index.html"
        if not path.exists():
            errors.append(f"{f.relative_to(OUT)}: missing {link}")
        elif frag and path.suffix == ".html" and frag not in pages.get(path, Collector()).ids:
            errors.append(f"{f.relative_to(OUT)}: missing anchor {link}")

if "--external" in sys.argv:
    for url in sorted(external):
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "link-check"})
            code = urllib.request.urlopen(req, timeout=15).status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as e:  # noqa: BLE001
            code = type(e).__name__
        print(code, url)

print(f"{len(pages)} pages, {sum(len(c.links) for c in pages.values())} links, {len(external)} external")
for e in errors:
    print("ERROR", e)
sys.exit(1 if errors else 0)
