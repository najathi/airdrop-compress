#!/usr/bin/env python3
"""
AirDrop -> WebP auto-compressor for macOS.

Watches the AirDrop folder (~/Downloads, or ~/Desktop/AirDrop if it exists), and every time a new image arrives
(HEIC, HEIF, JPEG, PNG, TIFF, GIF, BMP, AVIF) it writes a compressed WebP copy
to an "Image Compressed" folder inside it. The original file is never modified.

Run in the foreground:   .venv/bin/python airdrop_compress.py
Backfill existing files: .venv/bin/python airdrop_compress.py --scan-existing  (one-off)
Normally it is run in the background by the LaunchAgent that
`./airdrop-compress install` sets up.
"""

from __future__ import annotations

import time

# Captured before the (slow) image-library imports so files that arrive while
# the service is starting up still count as new.
PROCESS_STARTED = time.time()

import argparse
import fcntl
import hashlib
import json
import logging
import os
import queue
import signal
import subprocess
import sys
import threading
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

register_heif_opener()

# --------------------------------------------------------------------------- #
# Settings - edit these to taste, then run `./airdrop-compress restart`.
# --------------------------------------------------------------------------- #

# AirDrop saves to ~/Downloads. If you use a Folder Action (e.g. "airdropSorter") that
# moves AirDrop files into ~/Desktop/AirDrop, that folder is watched instead.
# The AIRDROP_DIR environment variable overrides both.
_SORTED_AIRDROP_DIR = Path("~/Desktop/AirDrop").expanduser()
WATCH_DIR = Path(os.environ.get(
    "AIRDROP_DIR", _SORTED_AIRDROP_DIR if _SORTED_AIRDROP_DIR.is_dir() else "~/Downloads",
)).expanduser()
OUTPUT_DIR = WATCH_DIR / "Image Compressed"

WEBP_QUALITY = 80        # 0-100. 75-85 looks the same as the original for photos.
WEBP_METHOD = 6          # 0 (fast) - 6 (slowest, smallest file).
WEBP_MAX_SIDE = 16383    # Hard limit of the WebP format (very wide panoramas get scaled).
MAX_DIMENSION = None     # e.g. 3000 to shrink the long edge to 3000px; None = keep size.
KEEP_METADATA = True     # Keep EXIF (date, camera, GPS) and colour profile.

# Browser/app downloads carry a quarantine tag naming the app (Chrome, Firefox...);
# AirDrop files are tagged "sharingd" or not at all. This skips the web ones.
SKIP_WEB_DOWNLOADS = True

NOTIFY = True            # macOS notification after each batch.
WORKERS = 2              # Images converted in parallel.
RESCAN_SECONDS = 30      # Safety-net rescan in case a file event was missed.

STATE_DIR = Path("~/Library/Application Support/AirDropCompress").expanduser()
STATE_FILE = STATE_DIR / "processed.json"

CANDIDATE_EXTS = {
    ".heic", ".heif", ".hif", ".jpg", ".jpeg", ".png",
    ".tif", ".tiff", ".bmp", ".gif", ".avif",
}
# Only the formats this Pillow build can actually read.
SUPPORTED_EXTS = CANDIDATE_EXTS & set(Image.registered_extensions())

# Incomplete download names from browsers - never touch these.
PARTIAL_SUFFIXES = (".download", ".crdownload", ".part", ".tmp")
AIRDROP_AGENTS = {"sharingd", "airdrop", "airdropui"}

log = logging.getLogger("airdrop-compress")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def human(n: float) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def notify(title: str, message: str) -> None:
    if not NOTIFY:
        return
    script = f"display notification {json.dumps(message)} with title {json.dumps(title)}"
    subprocess.run(["osascript", "-e", script], capture_output=True)


def quarantine_agent(path: Path) -> str | None:
    """Return the app that quarantined the file, or None if it has no quarantine tag."""
    result = subprocess.run(
        ["/usr/bin/xattr", "-p", "com.apple.quarantine", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    parts = result.stdout.strip().split(";")
    return parts[2] if len(parts) > 2 else ""


def is_candidate(path: Path) -> bool:
    name = path.name
    return (
        not name.startswith(".")
        and not name.lower().endswith(PARTIAL_SUFFIXES)
        and path.suffix.lower() in SUPPORTED_EXTS
        and path.parent == WATCH_DIR
    )


def wait_until_complete(path: Path, timeout: float = 300) -> bool:
    """Wait until the file stops growing (AirDrop may still be writing it)."""
    deadline = time.monotonic() + timeout
    last, stable = None, 0
    while time.monotonic() < deadline:
        try:
            st = path.stat()
        except FileNotFoundError:
            return False
        sig = (st.st_size, st.st_mtime_ns)
        if sig == last and st.st_size > 0:
            stable += 1
            if stable >= 2:
                return True
        else:
            stable = 0
        last = sig
        time.sleep(0.5)
    return False


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_to_webp(src: Path, dst: Path) -> None:
    tmp = dst.with_name(f".{dst.name}.tmp")
    with Image.open(src) as im:
        icc = im.info.get("icc_profile")
        xmp = im.info.get("xmp")
        opts: dict = {"format": "WEBP", "quality": WEBP_QUALITY, "method": WEBP_METHOD}

        if getattr(im, "n_frames", 1) > 1 and im.format == "GIF":
            # Keep animated GIFs animated.
            opts.update(save_all=True, loop=im.info.get("loop", 0))
            im.save(tmp, **opts)
        else:
            img = ImageOps.exif_transpose(im)  # bake rotation into pixels
            has_alpha = "A" in img.getbands() or "transparency" in img.info
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if has_alpha else "RGB")
            limit = min(MAX_DIMENSION or WEBP_MAX_SIDE, WEBP_MAX_SIDE)
            if max(img.size) > limit:
                img.thumbnail((limit, limit), Image.Resampling.LANCZOS)
            if KEEP_METADATA:
                exif = img.getexif()
                if exif:
                    opts["exif"] = exif.tobytes()
                if icc:
                    opts["icc_profile"] = icc
                if xmp:
                    opts["xmp"] = xmp
            img.save(tmp, **opts)
    os.replace(tmp, dst)  # atomic: never leaves a half-written .webp behind


def convert_safely(src: Path, dst: Path) -> None:
    try:
        convert_to_webp(src, dst)
    except BaseException:
        dst.with_name(f".{dst.name}.tmp").unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- #
# State (duplicate protection)
# --------------------------------------------------------------------------- #

class ProcessedStore:
    """Remembers images by content hash, so the same photo is only converted once."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.in_progress: set[str] = set()

    def _load(self) -> dict[str, dict]:
        try:
            return json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def claim(self, digest: str) -> str | None:
        """Reserve a hash for processing. Returns why it should be skipped, or None."""
        with self.lock:
            if digest in self.in_progress:
                return "already being processed"
            # Read from disk each time: a `scan` run may have added records.
            entry = self._load().get(digest)
            if entry and (OUTPUT_DIR / entry["output"]).exists():
                return f"already converted to {entry['output']}"
            self.in_progress.add(digest)
            return None

    def finish(self, digest: str, src: Path, dst: Path | None) -> None:
        with self.lock:
            self.in_progress.discard(digest)
            if dst is None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # File lock so the service and a `scan` run never overwrite each other's records.
            with open(self.path.with_suffix(".lock"), "w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                data = self._load()
                data[digest] = {
                    "source": src.name,
                    "output": dst.name,
                    "converted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, indent=1))
                os.replace(tmp, self.path)


# --------------------------------------------------------------------------- #
# Batch notifications
# --------------------------------------------------------------------------- #

class BatchNotifier:
    """Collects results and sends a single notification once a batch goes quiet."""

    def __init__(self, delay: float = 4.0):
        self.delay = delay
        self.lock = threading.Lock()
        self.timer: threading.Timer | None = None
        self.count = self.before = self.after = self.failed = 0

    def add(self, before: int = 0, after: int = 0, failed: bool = False) -> None:
        with self.lock:
            if failed:
                self.failed += 1
            else:
                self.count += 1
                self.before += before
                self.after += after
            if self.timer:
                self.timer.cancel()
            self.timer = threading.Timer(self.delay, self.flush)
            self.timer.daemon = True
            self.timer.start()

    def flush(self) -> None:
        with self.lock:
            count, before, after, failed = self.count, self.before, self.after, self.failed
            self.count = self.before = self.after = self.failed = 0
            if self.timer:
                self.timer.cancel()
        parts = []
        if count:
            saved = 100 - (after / before * 100) if before else 0
            noun = "image" if count == 1 else "images"
            parts.append(f"{count} {noun}: {human(before)} -> {human(after)} ({saved:.0f}% smaller)")
        if failed:
            parts.append(f"{failed} failed - see log")
        if parts:
            notify("AirDrop Compress", ". ".join(parts))


# --------------------------------------------------------------------------- #
# Watcher
# --------------------------------------------------------------------------- #

class Compressor:
    def __init__(self, scan_existing: bool = False):
        self.scan_existing = scan_existing
        self.queue: queue.Queue[Path] = queue.Queue()
        self.pending: set[Path] = set()
        self.seen: dict[Path, tuple[int, int]] = {}  # path -> (size, mtime) handled this run
        self.pending_lock = threading.Lock()
        self.reserved_names: set[str] = set()
        self.names_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.store = ProcessedStore(STATE_FILE)
        self.notifier = BatchNotifier()
        # Images already in the folder when we start are "old" and left alone
        # (unless backfilling). Anything else that shows up is new.
        self.old_files: dict[str, int] = {} if scan_existing else self.snapshot()

    @staticmethod
    def snapshot() -> dict[str, int]:
        """name -> inode of the files already in the folder.

        File dates can't tell us when something arrived (AirDrop sets them to when the
        photo was taken), and macOS sometimes reports an in-place edit as "created".
        A file copied or moved in always has a different inode, so name+inode is
        reliable. ctime reflects arrival, so files that landed in the seconds before
        start-up (while we were loading) still count as new.
        """
        old = {}
        try:
            for entry in os.scandir(WATCH_DIR):
                if entry.is_file():
                    st = entry.stat()
                    if st.st_ctime < PROCESS_STARTED - 5:
                        old[entry.name] = st.st_ino
        except OSError:
            pass  # no access yet - wait_for_folder_access() reports it
        return old

    # -- queueing --------------------------------------------------------- #

    def enqueue(self, path: Path) -> None:
        if not is_candidate(path):
            return
        try:
            st = path.stat()
        except FileNotFoundError:
            return
        if self.old_files.get(path.name) == st.st_ino:
            return  # was here before we started (e.g. an old photo being edited)
        # Already handled, unless the content changed.
        if self.seen.get(path) == (st.st_size, st.st_mtime_ns):
            return
        with self.pending_lock:
            if path in self.pending:
                return
            self.pending.add(path)
        self.queue.put(path)

    def rescan(self) -> None:
        """Pick up any new image in the folder that no event told us about."""
        try:
            entries = list(os.scandir(WATCH_DIR))
        except OSError as e:
            log.warning("Rescan failed: %s", e)
            return
        for entry in entries:
            if entry.is_file():
                self.enqueue(Path(entry.path))

    def reserve_output_path(self, src: Path) -> Path:
        """Pick a free name in the output folder (IMG_1.HEIC and IMG_1.JPG -> IMG_1-1.webp)."""
        with self.names_lock:
            out, n = OUTPUT_DIR / f"{src.stem}.webp", 1
            while out.exists() or out.name in self.reserved_names:
                out, n = OUTPUT_DIR / f"{src.stem}-{n}.webp", n + 1
            self.reserved_names.add(out.name)
            return out

    # -- processing ------------------------------------------------------- #

    def worker(self) -> None:
        while not self.stop_event.is_set():
            try:
                path = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.process(path)
            except Exception:
                log.exception("Unexpected error with %s", path.name)
            finally:
                with self.pending_lock:
                    self.pending.discard(path)
                self.queue.task_done()

    def process(self, src: Path) -> None:
        if not wait_until_complete(src):
            log.info("Skipped %s (disappeared or never finished copying)", src.name)
            return
        st = src.stat()
        self.seen[src] = (st.st_size, st.st_mtime_ns)

        if SKIP_WEB_DOWNLOADS:
            agent = quarantine_agent(src)
            if agent is not None and agent.lower() not in AIRDROP_AGENTS:
                log.info("Skipped %s (downloaded by %s, not AirDrop)", src.name, agent or "an app")
                return

        digest = sha256(src)
        reason = self.store.claim(digest)
        if reason:
            log.info("Skipped %s (%s)", src.name, reason)
            return

        dst = None
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            dst = self.reserve_output_path(src)
            for attempt in range(3):
                try:
                    convert_safely(src, dst)
                    break
                except OSError:
                    # Truncated/locked file - give AirDrop a moment and retry.
                    if attempt == 2:
                        raise
                    time.sleep(2)
            before, after = st.st_size, dst.stat().st_size
            log.info("Converted %s -> %s (%s -> %s)", src.name, dst.name, human(before), human(after))
            self.notifier.add(before, after)
        except Exception as e:
            log.error("Failed to convert %s: %s", src.name, e)
            self.notifier.add(failed=True)
            if dst:
                with self.names_lock:
                    self.reserved_names.discard(dst.name)
            dst = None
        finally:
            self.store.finish(digest, src, dst)

    # -- lifecycle -------------------------------------------------------- #

    def wait_for_folder_access(self) -> bool:
        """macOS privacy protection can block background access to the watched folder."""
        warned = False
        while not self.stop_event.is_set():
            try:
                os.listdir(WATCH_DIR)
                if warned:
                    log.info("Access to %s granted - continuing.", WATCH_DIR)
                return True
            except PermissionError:
                if not warned:
                    log.error(
                        "macOS is blocking access to %s. Open System Settings > Privacy & Security > "
                        "Full Disk Access and enable: %s  (run `./airdrop-compress permissions`). "
                        "Will retry every 30 seconds.", WATCH_DIR, sys.executable,
                    )
                    notify("AirDrop Compress", f"Needs permission to read {WATCH_DIR.name} - see Full Disk Access.")
                    warned = True
                self.stop_event.wait(30)
            except FileNotFoundError:
                log.error("Folder %s does not exist.", WATCH_DIR)
                return False
        return False

    def run(self) -> int:
        if not self.wait_for_folder_access():
            return 1
        if not self.scan_existing and not self.old_files:
            self.old_files = self.snapshot()  # access was only just granted
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        threads = [threading.Thread(target=self.worker, daemon=True) for _ in range(WORKERS)]
        for t in threads:
            t.start()

        if self.scan_existing:
            # One-off backfill: convert what's already there, then exit.
            log.info("Scanning existing images in %s ...", WATCH_DIR)
            self.rescan()
            while self.queue.unfinished_tasks and not self.stop_event.is_set():
                time.sleep(0.2)
            self.stop_event.set()
            for t in threads:
                t.join(timeout=30)
            self.notifier.flush()
            log.info("Scan finished.")
            return 0

        handler = _EventHandler(self)
        observer = Observer()
        observer.schedule(handler, str(WATCH_DIR), recursive=False)
        observer.start()
        log.info(
            "Watching %s -> %s (quality %d, formats: %s)",
            WATCH_DIR, OUTPUT_DIR, WEBP_QUALITY, " ".join(sorted(SUPPORTED_EXTS)),
        )

        self.rescan()  # catch files that landed while we were starting up
        try:
            while not self.stop_event.wait(RESCAN_SECONDS):
                self.rescan()
        finally:
            log.info("Stopping...")
            observer.stop()
            observer.join(timeout=5)
            self.stop_event.set()
            for t in threads:
                t.join(timeout=30)
            self.notifier.flush()
            log.info("Stopped.")
        return 0


class _EventHandler(FileSystemEventHandler):
    def __init__(self, compressor: Compressor):
        self.c = compressor

    def on_created(self, event):
        if not event.is_directory:
            self.c.enqueue(Path(os.fsdecode(event.src_path)))

    def on_moved(self, event):  # files moved in by the Folder Action, or renamed temp files
        if not event.is_directory:
            self.c.enqueue(Path(os.fsdecode(event.dest_path)))

    def on_modified(self, event):
        if not event.is_directory:
            self.c.enqueue(Path(os.fsdecode(event.src_path)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert images received via AirDrop to compressed WebP.")
    parser.add_argument("--scan-existing", action="store_true",
                        help="convert images already in the folder once, then exit "
                             "(skips ones converted before)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    compressor = Compressor(scan_existing=args.scan_existing)

    def stop(signum, _frame):
        compressor.stop_event.set()

    signal.signal(signal.SIGTERM, stop)  # launchctl stop / bootout
    signal.signal(signal.SIGINT, stop)   # Ctrl+C
    return compressor.run()


if __name__ == "__main__":
    sys.exit(main())
