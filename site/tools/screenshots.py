#!/usr/bin/env python3
"""Capture the app screenshots used on the website (site/assets/img/app-*.webp).

Runs the real app UI from source with a throw-away profile and generated demo files
(no personal data), lets the engine convert them, then captures each page in light
and dark mode and saves WebP files. macOS only; the windows appear briefly on screen.

    .venv/bin/python site/tools/screenshots.py
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "assets" / "img"


def make_demo_files(folder: Path) -> None:
    from openpyxl import Workbook
    from PIL import Image, ImageDraw, ImageFilter
    from pillow_heif import register_heif_opener
    register_heif_opener()
    random.seed(7)

    def scene(w, h, hue):
        img = Image.new("RGB", (w, h))
        d = ImageDraw.Draw(img)
        for y in range(h):
            t = y / h
            d.line([(0, y), (w, y)], fill=(int(60 + 150 * (1 - t) * hue[0]),
                                           int(110 + 100 * (1 - t) * hue[1]), int(170 + 70 * (1 - t))))
        for _ in range(400):
            x, y, r = random.randint(0, w), random.randint(h // 3, h), random.randint(10, h // 6)
            d.ellipse([x - r, y - r, x + r, y + r],
                      fill=(random.randint(20, 120), random.randint(70, 170), random.randint(30, 100)))
        noise = Image.effect_noise((w, h), 60).convert("RGB")
        return Image.blend(img.filter(ImageFilter.GaussianBlur(1)), noise, 0.2)  # compresses like a real photo

    scene(4032, 3024, (0.9, 0.8)).save(folder / "IMG_2041.HEIC", quality=92)
    scene(3024, 4032, (0.6, 0.9)).save(folder / "IMG_2042.HEIC", quality=92)
    scene(4032, 3024, (1.0, 0.6)).save(folder / "IMG_2043.HEIC", quality=92)
    shot = Image.new("RGB", (1290, 2796), (245, 245, 247))
    dd = ImageDraw.Draw(shot)
    for i in range(12):
        dd.rounded_rectangle([60, 200 + i * 210, 1230, 360 + i * 210], 30, fill=(255, 255, 255))
    shot.save(folder / "Screenshot 2026-10-19 at 09.14.png")
    (folder / "Meeting notes.txt").write_text("Project kickoff\n\n- Agree scope\n- Share designs by Friday\n")
    (folder / "logo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg">\n  <!-- exported -->\n'
                                     '  <circle cx="50.123456" cy="50.98765" r="40"/>\n</svg>\n')
    wb = Workbook()
    wb.active.append(["Product", "Units"])
    wb.active.append(["Phone case", 120])
    wb.save(folder / "Sales Q3.xlsx")


def capture(mode: str, demo: Path, inbox: Path, tmp: Path) -> None:
    import AppKit
    import Quartz
    import webview
    import webview.platforms.cocoa  # noqa: F401
    from PIL import Image

    from airdrop_compress import paths
    from airdrop_compress.ui import app as appmod
    from airdrop_compress.ui import menubar

    appearance = "NSAppearanceNameDarkAqua" if mode == "dark" else "NSAppearanceNameAqua"
    AppKit.NSApplication.sharedApplication().setAppearance_(AppKit.NSAppearance.appearanceNamed_(appearance))
    app = appmod.App(False)
    app.legacy_service = False
    app.window = webview.create_window("AirDrop Compress", url=str(paths.resource("ui/web/index.html")),
                                       js_api=app.api, width=1100, height=760, text_select=False)
    loaded = threading.Event()
    app.window.events.loaded += lambda: loaded.set()
    menubar.install(app)

    def js(code, wait=0.8):
        result = app.window.evaluate_js(code)
        time.sleep(wait)
        return result

    def shot(name):
        """Capture the window; retry while WebKit hasn't drawn it (background windows can stay blank)."""
        from PIL import ImageStat
        for attempt in range(6):
            app.show_window()  # bring to front so WebKit renders it
            time.sleep(1.0 + attempt)
            wins = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID)
            wid = next(w["kCGWindowNumber"] for w in wins
                       if w.get("kCGWindowOwnerPID") == os.getpid() and w.get("kCGWindowName") == "AirDrop Compress")
            png = tmp / f"{name}-{mode}.png"
            subprocess.run(["screencapture", "-x", "-o", "-l", str(wid), str(png)], check=True)
            img = Image.open(png).convert("RGB")
            content = img.convert("L").crop((240, 60, img.width - 20, img.height - 20))
            if ImageStat.Stat(content).stddev[0] > 8:
                img.save(tmp / f"app-{name}-{mode}.webp", "WEBP", quality=82, method=6)
                return
        raise SystemExit(f"Capture of {name} ({mode}) stayed blank - is the screen awake and unlocked?")

    def run():
        app._after_start()
        loaded.wait(20)
        time.sleep(2)
        # Background windows pause CSS animations; turn them off so pages render immediately.
        js("const s = document.createElement('style'); s.textContent = '.page{animation:none!important}';"
           " document.head.append(s); 1")
        for f in sorted(demo.iterdir()):
            subprocess.run(["ditto", str(f), str(inbox / f.name)], check=True)
            time.sleep(0.4)
        end = time.time() + 180
        while time.time() < end and (app.engine.activity.stats()["busy"] or len(app.engine.activity.snapshot()) < 7):
            time.sleep(1)
        time.sleep(2)
        js("for (let i = 1; i < 99; i++) clearInterval(i);"
           " document.getElementById('hero-folder').textContent = '~/Desktop/AirDrop';"
           " document.getElementById('content').scrollTop = 0", 1.2)
        shot("dashboard")
        for page in ("images", "plugins"):
            js(f"showPage('{page}')", 1.2)
            shot(page)
        js("showPage('about')", 1)
        js("document.getElementById('about-support').textContent = '~/Library/Application Support/AirDropCompress';"
           " document.getElementById('about-log').textContent = '~/Library/Logs/AirDropCompress/airdrop-compress.log'; 1")
        js("document.getElementById('build-with-us').scrollIntoView()", 0.8)
        shot("about-build")
        app.quit()

    webview.start(lambda: threading.Thread(target=run, daemon=True).start())


def main() -> None:
    if len(sys.argv) > 1:  # child process: capture one appearance
        capture(sys.argv[1], Path(sys.argv[2]), Path(os.environ["AIRDROP_DIR"]), Path(sys.argv[3]))
        return
    tmp = Path(tempfile.mkdtemp(prefix="adc-shots-"))
    demo = tmp / "demo"
    demo.mkdir()
    make_demo_files(demo)
    for mode in ("light", "dark"):
        home, inbox = tmp / f"home-{mode}", tmp / f"inbox-{mode}"
        (home / "plugins").mkdir(parents=True)
        inbox.mkdir()
        shutil.copytree(ROOT / "examples/plugins/svg-minify", home / "plugins/svg-minify")
        (home / "settings.json").write_text('{"general":{"notifications":false,"check_for_updates":false},'
                                            '"images":{"metadata":"no_location","responsive_widths":[800]}}')
        env = {**os.environ, "AIRDROP_COMPRESS_HOME": str(home), "AIRDROP_DIR": str(inbox), "PYTHONPATH": str(ROOT)}
        subprocess.run([sys.executable, "-c", "from airdrop_compress.settings import SettingsManager;"
                        "from airdrop_compress.plugins.manager import PluginManager;"
                        "PluginManager(SettingsManager()).enable('svg-minify')"], env=env, check=True)
        subprocess.run([sys.executable, __file__, mode, str(demo), str(tmp)], env=env, check=True)
    # Only replace the published images once every capture succeeded.
    for f in tmp.glob("app-*.webp"):
        shutil.copy(f, OUT / f.name)
    shutil.rmtree(tmp, ignore_errors=True)
    print("Saved screenshots to", OUT)


if __name__ == "__main__":
    main()
