"""The watcher: notices new files in the AirDrop folder and hands each one to a processor.

This is the v1 watcher (airdrop_compress.py) restructured: the detection,
completeness checks, AirDrop/web filter, duplicate protection and atomic
output handling are unchanged; conversion now goes through pluggable processors.
"""

from __future__ import annotations

import fcntl
import logging
import os
import queue
import re
import shutil
import tempfile
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import APP_NAME, PROCESS_STARTED, macos, paths
from .activity import Activity, ActivityLog
from .processors.base import Job, Output, Processor, SkipFile
from .processors.documents import DocumentProcessor
from .processors.images import ImageProcessor, human
from .settings import Settings, SettingsManager, resolve_output_folder, resolve_watch_folder
from .store import ProcessedStore, sha256

log = logging.getLogger("airdrop-compress")

RESCAN_SECONDS = 30            # safety-net rescan in case a file event was missed
LEGACY_OUTPUT_NAME = "Image Compressed"   # v1 output folder, renamed on start-up
PARTIAL_SUFFIXES = (".download", ".crdownload", ".part", ".tmp")  # unfinished downloads
AIRDROP_AGENTS = {"sharingd", "airdrop", "airdropui"}


def is_relevant(path: Path, watch_dir: Path) -> bool:
    """A visible, complete file directly inside the watched folder."""
    name = path.name
    return (not name.startswith(".") and not name.lower().endswith(PARTIAL_SUFFIXES)
            and path.parent == watch_dir)


def wait_until_complete(path: Path, stop: threading.Event, timeout: float = 300) -> str:
    """Wait until the file stops growing (AirDrop may still be writing it).
    Returns "ok", "gone", "empty" or "timeout"."""
    deadline = time.monotonic() + timeout
    last, stable = None, 0
    while time.monotonic() < deadline and not stop.is_set():
        try:
            st = path.stat()
        except FileNotFoundError:
            return "gone"
        sig = (st.st_size, st.st_mtime_ns)
        if sig == last:
            stable += 1
            if st.st_size > 0 and stable >= 2:
                return "ok"
            if st.st_size == 0 and stable >= 6:  # still empty after ~3 s: not being written
                return "empty"
        else:
            stable = 0
        last = sig
        time.sleep(0.5)
    return "timeout"


def friendly_error(e: Exception) -> str:
    """Turn library exceptions into messages people can act on."""
    from PIL import Image, UnidentifiedImageError
    if isinstance(e, UnidentifiedImageError):
        return "Not a valid image, or the file is damaged"
    if isinstance(e, Image.DecompressionBombError):
        return "The image is too large to process safely"
    if isinstance(e, MemoryError):
        return "Not enough memory to process this file"
    if isinstance(e, OSError) and "truncated" in str(e).lower():
        return "The image is incomplete or damaged"
    if isinstance(e, PermissionError):
        return "macOS didn't allow reading or saving this file"
    message = str(e).strip() or type(e).__name__
    return message[:1].upper() + message[1:]


MAX_NAME_BYTES = 255  # macOS file name limit


def fit_name(stem: str, suffix: str) -> str:
    """Shorten a stem so stem+suffix fits the file name limit (keeps whole characters)."""
    budget = MAX_NAME_BYTES - len(suffix.encode())
    encoded = stem.encode()
    if len(encoded) <= budget:
        return stem
    return encoded[:budget].decode(errors="ignore").rstrip() or "file"


def seo_slug(stem: str, fallback: str = "file") -> str:
    """'IMG_1286 Beach Day' -> 'img-1286-beach-day' (Google: short, descriptive, hyphenated)."""
    text = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:80].rstrip("-") or fallback


@dataclass
class QueueItem:
    path: Path
    force: bool = False        # manual "Convert files…": skip the AirDrop and duplicate checks


class BatchNotifier:
    """Collects results and sends a single notification once a batch goes quiet."""

    def __init__(self, enabled, delay: float = 4.0):
        self.enabled = enabled
        self.delay = delay
        self.lock = threading.Lock()
        self.timer: threading.Timer | None = None
        self._reset()

    def _reset(self):
        self.images = self.documents = self.other = self.before = self.after = self.failed = 0

    def add(self, kind: str = "", before: int = 0, after: int = 0, failed: bool = False) -> None:
        with self.lock:
            if failed:
                self.failed += 1
            elif kind == "image":
                self.images += 1
                self.before += before
                self.after += after
            elif kind == "document":
                self.documents += 1
            else:
                self.other += 1
            if self.timer:
                self.timer.cancel()
            self.timer = threading.Timer(self.delay, self.flush)
            self.timer.daemon = True
            self.timer.start()

    def flush(self) -> None:
        with self.lock:
            images, documents, other = self.images, self.documents, self.other
            before, after, failed = self.before, self.after, self.failed
            self._reset()
            if self.timer:
                self.timer.cancel()
        parts = []
        if images:
            saved = 100 - (after / before * 100) if before else 0
            noun = "image" if images == 1 else "images"
            parts.append(f"{images} {noun}: {human(before)} → {human(after)} ({saved:.0f}% smaller)")
        if documents:
            parts.append(f"{documents} document{'s' if documents != 1 else ''} converted to Markdown")
        if other:
            parts.append(f"{other} file{'s' if other != 1 else ''} processed by plugins")
        if failed:
            parts.append(f"{failed} failed - see the dashboard")
        if parts and self.enabled():
            macos.notify(APP_NAME, ". ".join(parts))


class Engine:
    def __init__(self, settings: SettingsManager, plugins=None, activity: ActivityLog | None = None,
                 store: ProcessedStore | None = None):
        self.settings = settings
        self.plugins = plugins
        self.activity = activity or ActivityLog(paths.ACTIVITY_FILE)
        self.store = store or ProcessedStore(paths.STATE_FILE)
        self.builtins: list[Processor] = [ImageProcessor(), DocumentProcessor()]
        self.notifier = BatchNotifier(lambda: self.settings.current.general.notifications)

        self.state = "stopped"     # stopped | starting | running | paused | waiting_access | locked | error
        self.message = ""
        self.watch_dir = resolve_watch_folder(settings.current)
        self.output_dir = resolve_output_folder(settings.current)

        self.queue: queue.Queue[QueueItem] = queue.Queue()
        self.pending: set[Path] = set()
        self.pending_lock = threading.Lock()
        self.seen: dict[Path, tuple[int, int]] = {}
        self.unsupported_logged: set[str] = set()
        self.reserved_names: set[str] = set()
        self.names_lock = threading.Lock()
        self.old_files: dict[str, int] = {}

        self.stop_event = threading.Event()
        self._first_start = True
        self._thread: threading.Thread | None = None
        self._lock_file = None
        self._control = threading.Lock()
        settings.subscribe(self._on_settings_changed)

    # ===================================================================== #
    # Control
    # ===================================================================== #

    def start(self, scan_existing: bool = False) -> None:
        """Start watching in a background thread (no-op if already running)."""
        with self._control:
            if self._thread and self._thread.is_alive():
                return
            self.stop_event = threading.Event()
            self._thread = threading.Thread(target=self._run, args=(scan_existing, False),
                                            name="engine", daemon=True)
            self._thread.start()

    def run_blocking(self, scan_existing: bool = False, once: bool = False) -> int:
        """Watch in the current thread until stop() (or until the scan finishes, with once)."""
        self.stop_event = threading.Event()
        return self._run(scan_existing, once)

    def stop(self) -> None:
        with self._control:
            self.stop_event.set()
            t = self._thread
        if t and t is not threading.current_thread():
            t.join(timeout=40)

    def restart(self) -> None:
        self.stop()
        if not self.settings.current.general.paused:
            self.start()

    def pause(self) -> None:
        self.settings.update({"general": {"paused": True}})   # listener stops the engine

    def resume(self) -> None:
        self.settings.update({"general": {"paused": False}})  # listener starts the engine

    def scan_existing(self) -> int:
        """Queue the files already in the AirDrop folder (duplicates are still skipped)."""
        count = 0
        try:
            entries = list(os.scandir(self.watch_dir))
        except OSError:
            return 0
        for entry in entries:
            path = Path(entry.path)
            if entry.is_file() and is_relevant(path, self.watch_dir) and self.route(path):
                self.old_files.pop(path.name, None)
                self.seen.pop(path, None)
                count += self._enqueue(path)
        return count

    def convert_now(self, files: list[Path]) -> int:
        """Convert files the user picked or dropped, wherever they are."""
        count = 0
        for f in files:
            if f.is_file():
                count += self._enqueue(f, force=True)
        return count

    def status(self) -> dict:
        return {
            "state": self.state, "message": self.message,
            "watch_folder": str(self.watch_dir), "output_folder": str(self.output_dir),
            "queued": self.queue.unfinished_tasks,
        }

    def _on_settings_changed(self, old: Settings, new: Settings) -> None:
        g_old, g_new = old.general, new.general
        if g_old.paused != g_new.paused:
            if g_new.paused:
                self.stop()
                self.state, self.message = "paused", "Paused - new files aren't processed."
            else:
                self.start()
        elif (g_old.watch_folder, g_old.output_folder, g_old.workers) != \
                (g_new.watch_folder, g_new.output_folder, g_new.workers):
            if self._thread and self._thread.is_alive():
                threading.Thread(target=self.restart, daemon=True).start()
            else:
                self.watch_dir = resolve_watch_folder(new)
                self.output_dir = resolve_output_folder(new)

    # ===================================================================== #
    # Main loop
    # ===================================================================== #

    def _acquire_lock(self) -> bool:
        """Only one watcher (app or command line) may process files at a time."""
        paths.ENGINE_LOCK.parent.mkdir(parents=True, exist_ok=True)
        f = open(paths.ENGINE_LOCK, "a+")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            f.seek(0)
            owner = f.read().strip()
            f.close()
            self.state = "locked"
            self.message = ("Another copy of AirDrop Compress is already processing files"
                            + (f" (process {owner})" if owner else "") + ".")
            return False
        f.seek(0)
        f.truncate()
        f.write(str(os.getpid()))
        f.flush()
        self._lock_file = f
        return True

    def _release_lock(self) -> None:
        if self._lock_file:
            self._lock_file.close()
            self._lock_file = None

    def _run(self, scan_existing: bool, once: bool) -> int:
        self.state, self.message = "starting", ""
        # First start: anything that arrived since the process launched is new. After a
        # pause or restart, only files arriving from now on are (paused means paused).
        started = PROCESS_STARTED - 2 if self._first_start else time.time()
        self._first_start = False
        while not self._acquire_lock():
            log.warning(self.message)
            if once or self.stop_event.wait(5):
                return 1
        try:
            s = self.settings.current
            self.watch_dir = resolve_watch_folder(s)
            self.output_dir = resolve_output_folder(s)
            if not self._wait_for_folder_access():
                return 1
            self.old_files = {} if scan_existing else self._snapshot(started)
            self.seen.clear()
            self.unsupported_logged.clear()
            if self.output_dir.resolve() == self.watch_dir.resolve():
                # Outputs would land in the watched folder and be converted again, forever.
                self.state = "error"
                self.message = ("The output folder can't be the AirDrop folder itself. "
                                "Choose a folder name in Settings › General.")
                log.error(self.message)
                return 1
            self._migrate_output_folder()
            self.output_dir.mkdir(parents=True, exist_ok=True)

            workers = [threading.Thread(target=self._worker, daemon=True, name=f"worker-{i}")
                       for i in range(s.general.workers)]
            for t in workers:
                t.start()

            if once:
                log.info("Scanning existing files in %s ...", self.watch_dir)
                self.scan_existing()
                while self.queue.unfinished_tasks and not self.stop_event.is_set():
                    time.sleep(0.2)
                self.stop_event.set()
                for t in workers:
                    t.join(timeout=30)
                self.notifier.flush()
                log.info("Scan finished.")
                return 0

            observer = Observer()
            observer.schedule(_EventHandler(self), str(self.watch_dir), recursive=False)
            observer.start()
            self.state = "running"
            self.message = f"Watching {self.watch_dir}"
            log.info("Watching %s -> %s", self.watch_dir, self.output_dir)
            self._rescan()  # catch files that landed while we were starting up
            try:
                while not self.stop_event.wait(RESCAN_SECONDS):
                    self.settings.reload_if_changed()
                    self._rescan()
            finally:
                log.info("Stopping...")
                observer.stop()
                observer.join(timeout=5)
                for t in workers:
                    t.join(timeout=30)
                self.notifier.flush()
                log.info("Stopped.")
            return 0
        except Exception as e:
            log.exception("Watcher crashed")
            self.state, self.message = "error", f"Something went wrong: {e}"
            return 1
        finally:
            self._release_lock()
            if self.state not in ("error", "locked"):
                paused = self.settings.current.general.paused
                self.state = "paused" if paused else "stopped"
                self.message = "Paused - new files aren't processed." if paused else ""

    def _wait_for_folder_access(self) -> bool:
        """macOS privacy protection can block access to Desktop/Downloads."""
        warned = False
        while not self.stop_event.is_set():
            try:
                os.listdir(self.watch_dir)
                if warned:
                    log.info("Access to %s granted - continuing.", self.watch_dir)
                return True
            except PermissionError:
                self.state = "waiting_access"
                self.message = (f"macOS is blocking access to {self.watch_dir}. Allow it in System Settings "
                                "› Privacy & Security › Files and Folders (or Full Disk Access).")
                if not warned:
                    log.error("%s Will retry every 10 seconds.", self.message)
                    warned = True
                self.stop_event.wait(10)
            except FileNotFoundError:
                self.state = "error"
                self.message = f"The folder {self.watch_dir} doesn't exist. Choose another in Settings › General."
                log.error(self.message)
                return False
        return False

    def _snapshot(self, started: float) -> dict[str, int]:
        """name -> inode of files already in the folder ("old", left alone).

        File dates can't tell when something arrived (AirDrop sets them to when the
        photo was taken). A file copied or moved in always has a new inode, so
        name+inode is reliable; ctime reflects arrival, so files that landed while
        we were starting still count as new (see _run)."""
        old = {}
        try:
            for entry in os.scandir(self.watch_dir):
                if entry.is_file():
                    st = entry.stat()
                    if st.st_ctime < started:
                        old[entry.name] = st.st_ino
        except OSError:
            pass
        return old

    def _migrate_output_folder(self) -> None:
        """Rename the v1 "Image Compressed" folder to the current output folder."""
        legacy = self.watch_dir / LEGACY_OUTPUT_NAME
        if not legacy.is_dir() or legacy == self.output_dir:
            return
        if not self.output_dir.exists():
            legacy.rename(self.output_dir)
            log.info("Renamed %s -> %s", legacy.name, self.output_dir.name)
            return
        for item in legacy.iterdir():
            if not (self.output_dir / item.name).exists():
                item.rename(self.output_dir / item.name)
        try:
            legacy.rmdir()
        except OSError:
            log.warning("Left %s in place: some files already exist in %s", legacy, self.output_dir)

    # ===================================================================== #
    # Queueing
    # ===================================================================== #

    def route(self, path: Path) -> Processor | None:
        """Enabled plugins get first pick of their file types, then the built-ins."""
        s = self.settings.current
        candidates = (self.plugins.processors() if self.plugins else []) + self.builtins
        return next((p for p in candidates if p.handles(path, s)), None)

    def _enqueue(self, path: Path, force: bool = False) -> int:
        with self.pending_lock:
            if path in self.pending:
                return 0
            self.pending.add(path)
        self.queue.put(QueueItem(path, force))
        return 1

    def notice(self, path: Path) -> None:
        """Called for every file event and rescan hit."""
        if not is_relevant(path, self.watch_dir):
            return
        try:
            if path.is_symlink():
                # Never follow links: one could point at a private file elsewhere on the Mac.
                if path.name not in self.unsupported_logged:
                    self.unsupported_logged.add(path.name)
                    log.info("Skipped %s (symbolic link)", path.name)
                return
            st = path.stat()
        except (FileNotFoundError, OSError):
            return
        if self.old_files.get(path.name) == st.st_ino:
            return  # was here before we started (e.g. an old photo being edited)
        if self.seen.get(path) == (st.st_size, st.st_mtime_ns):
            return  # already handled, and unchanged
        if self.route(path) is None:
            if path.name not in self.unsupported_logged:
                self.unsupported_logged.add(path.name)
                ext = path.suffix.lower() or "extension-less"
                item = self.activity.start(path.name, "other")
                self.activity.update(item, status="skipped", message=f"No converter for {ext} files")
                log.info("Skipped %s (no converter for %s files)", path.name, ext)
            return
        self._enqueue(path)

    def _rescan(self) -> None:
        try:
            entries = list(os.scandir(self.watch_dir))
        except OSError as e:
            log.warning("Rescan failed: %s", e)
            return
        for entry in entries:
            if entry.is_file(follow_symlinks=False):
                self.notice(Path(entry.path))
        # Forget files that are gone, so long-running sessions don't grow without bound.
        present = {Path(e.path) for e in entries}
        for gone in [p for p in self.seen if p not in present]:
            self.seen.pop(gone, None)

    # ===================================================================== #
    # Processing
    # ===================================================================== #

    def _worker(self) -> None:
        while not self.stop_event.is_set():
            try:
                item = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.process(item.path, force=item.force)
            except Exception:
                log.exception("Unexpected error with %s", item.path.name)
            finally:
                with self.pending_lock:
                    self.pending.discard(item.path)
                self.queue.task_done()

    def process(self, src: Path, force: bool = False) -> Activity | None:
        processor = self.route(src)
        if processor is None:
            return None
        item = self.activity.start(src.name, processor.kind)
        ready = wait_until_complete(src, self.stop_event)
        if ready != "ok":
            reason = {"gone": "Removed before it could be converted", "empty": "The file is empty",
                      "timeout": "Never finished copying"}[ready]
            try:  # remember it, so the periodic rescan doesn't report it again unless it changes
                st = src.stat()
                if not force:
                    self.seen[src] = (st.st_size, st.st_mtime_ns)
            except FileNotFoundError:
                pass
            self.activity.update(item, status="skipped", message=reason)
            log.info("Skipped %s (%s)", src.name, reason.lower())
            return item
        st = src.stat()
        if not force:
            self.seen[src] = (st.st_size, st.st_mtime_ns)
        settings = self.settings.current

        if settings.general.skip_web_downloads and not force:
            agent = macos.quarantine_agent(src)
            if agent and agent.lower() not in AIRDROP_AGENTS:
                self.activity.update(item, status="skipped", message=f"Downloaded by {agent}, not AirDrop")
                log.info("Skipped %s (downloaded by %s, not AirDrop)", src.name, agent)
                return item

        digest = sha256(src)
        reason = None if force else self.store.claim(digest, self.output_dir)
        if reason:
            self.activity.update(item, status="skipped", message=reason.capitalize())
            log.info("Skipped %s (%s)", src.name, reason)
            return item
        if force:
            self.store.in_progress.add(digest)

        self.activity.update(item, status="processing", processor=processor.name, before=st.st_size)
        placed: list[Path] = []
        self.output_dir.mkdir(parents=True, exist_ok=True)
        workdir = Path(tempfile.mkdtemp(dir=self.output_dir, prefix=".work-"))
        try:
            for attempt in range(3):
                try:
                    result = processor.process(Job(src, workdir, settings))
                    break
                except OSError:
                    # Truncated/locked file - give AirDrop a moment and retry.
                    if attempt == 2:
                        raise
                    time.sleep(2)
                    for leftover in workdir.iterdir():
                        shutil.rmtree(leftover) if leftover.is_dir() else leftover.unlink()
            stem = seo_slug(src.stem) if processor.kind == "image" and settings.images.seo_filenames else src.stem
            placed = self._place(stem, result.outputs)
            # Keep macOS's "downloaded from elsewhere" tag on everything made from this file.
            macos.copy_quarantine(src, placed)
            # Savings compare the original with the main output; extra sizes/fallbacks are bonuses.
            after = placed[0].stat().st_size
            self.activity.update(item, status="done", after=after, outputs=[p.name for p in placed],
                                 message=result.note)
            log.info("Converted %s -> %s (%s -> %s)%s", src.name, ", ".join(p.name for p in placed),
                     human(st.st_size), human(after), f" [{result.note}]" if result.note else "")
            self.notifier.add(processor.kind, st.st_size, after)
        except SkipFile as e:
            self.activity.update(item, status="skipped", message=str(e)[:1].upper() + str(e)[1:])
            log.info("Skipped %s (%s)", src.name, e)
        except Exception as e:
            message = friendly_error(e)
            self.activity.update(item, status="failed", message=message)
            log.error("Failed to convert %s: %s", src.name, message)
            self.notifier.add(failed=True)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
            self.store.finish(digest, src, placed or None)
        return item

    def _place(self, stem: str, outputs: list[Output]) -> list[Path]:
        """Give outputs unique final names (IMG_1.HEIC + IMG_1.JPG -> IMG_1-1.webp) and move them
        into the output folder atomically (same disk, so a rename)."""
        suffixes, seen = [], set()
        for o in outputs:
            suffix = o.suffix
            while suffix in seen:  # two outputs asked for the same name
                suffix = f"-{len(seen)}{suffix}"
            seen.add(suffix)
            suffixes.append(suffix)
        longest = max(suffixes, key=lambda x: len(x.encode()))
        stem = fit_name(stem, f"-9999{longest}")
        with self.names_lock:
            candidate, n = stem, 1
            while any((self.output_dir / f"{candidate}{s}").exists()
                      or f"{candidate}{s}" in self.reserved_names for s in suffixes):
                candidate, n = f"{stem}-{n}", n + 1
            names = [f"{candidate}{s}" for s in suffixes]
            self.reserved_names.update(names)
        placed = []
        try:
            for o, name in zip(outputs, names):
                dst = self.output_dir / name
                os.replace(o.path, dst)
                placed.append(dst)
        finally:
            with self.names_lock:
                self.reserved_names.difference_update(names)
        return placed


class _EventHandler(FileSystemEventHandler):
    def __init__(self, engine: Engine):
        self.engine = engine

    def on_created(self, event):
        if not event.is_directory:
            self.engine.notice(Path(os.fsdecode(event.src_path)))

    def on_moved(self, event):  # files moved in by a Folder Action, or renamed temp files
        if not event.is_directory:
            self.engine.notice(Path(os.fsdecode(event.dest_path)))

    def on_modified(self, event):
        if not event.is_directory:
            self.engine.notice(Path(os.fsdecode(event.src_path)))
