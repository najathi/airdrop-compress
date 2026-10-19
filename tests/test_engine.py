import shutil
import subprocess
import time

import pytest

from airdrop_compress.activity import ActivityLog
from airdrop_compress.engine import Engine, seo_slug
from airdrop_compress.settings import SettingsManager
from airdrop_compress.store import ProcessedStore


@pytest.fixture
def env(tmp_path, monkeypatch):
    watch = tmp_path / "AirDrop"
    watch.mkdir()
    monkeypatch.setenv("AIRDROP_DIR", str(watch))
    sm = SettingsManager(tmp_path / "settings.json")
    sm.update({"general": {"notifications": False}})
    engine = Engine(sm, None, ActivityLog(None), ProcessedStore(tmp_path / "processed.json"))
    yield engine, watch, watch / "airdrop-compress"
    engine.stop()


def wait_for(cond, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.2)
    return False


def start(engine):
    engine.start()
    assert wait_for(lambda: engine.state == "running"), engine.message


def test_new_files_are_converted_and_originals_untouched(env, photo_jpeg, alpha_png, monkeypatch):
    engine, watch, out = env
    shutil.copy(alpha_png, watch / "old.png")  # existed before the app started -> left alone
    time.sleep(2.5)
    monkeypatch.setattr("airdrop_compress.engine.PROCESS_STARTED", time.time())
    start(engine)
    dst = watch / photo_jpeg.name
    shutil.copy(photo_jpeg, dst)
    (watch / "notes.txt").write_text("hello")
    (watch / "movie.mov").write_bytes(b"x")
    before = dst.read_bytes()
    assert wait_for(lambda: (out / "IMG_0001.webp").exists() and (out / "notes.md").exists())
    assert dst.read_bytes() == before
    assert not (out / "old.webp").exists()
    statuses = {i["name"]: i["status"] for i in engine.activity.snapshot()}
    assert statuses["movie.mov"] == "skipped" and statuses["IMG_0001.JPG"] == "done"


def test_duplicates_and_name_collisions(env, photo_jpeg, alpha_png):
    engine, watch, out = env
    start(engine)
    shutil.copy(photo_jpeg, watch / "a.jpg")
    assert wait_for(lambda: (out / "a.webp").exists())
    shutil.copy(photo_jpeg, watch / "copy-of-a.jpg")       # same content -> skipped
    shutil.copy(alpha_png, watch / "a.png")                 # same stem, different file -> a-1.webp
    assert wait_for(lambda: (out / "a-1.webp").exists())
    time.sleep(2)
    assert not (out / "copy-of-a.webp").exists()


def test_web_downloads_are_skipped(env, photo_jpeg):
    engine, watch, out = env
    start(engine)
    staged = watch.parent / "dl.jpg"
    shutil.copy(photo_jpeg, staged)
    subprocess.run(["xattr", "-w", "com.apple.quarantine", "0081;6ad5b83d;Chrome;X", str(staged)], check=True)
    subprocess.run(["ditto", str(staged), str(watch / "dl.jpg")], check=True)  # ditto keeps the tag
    assert wait_for(lambda: any(i["name"] == "dl.jpg" and i["status"] == "skipped" for i in engine.activity.snapshot()))
    assert not (out / "dl.webp").exists()


def test_seo_names_and_legacy_folder(env, photo_jpeg):
    engine, watch, out = env
    legacy = watch / "Image Compressed"
    legacy.mkdir()
    (legacy / "earlier.webp").write_bytes(b"x")
    engine.settings.update({"images": {"seo_filenames": True}})
    start(engine)
    assert (out / "earlier.webp").exists() and not legacy.exists()
    shutil.copy(photo_jpeg, watch / "IMG_9 Beach Day.JPG")
    assert wait_for(lambda: (out / "img-9-beach-day.webp").exists())


def test_pause_resume(env, photo_jpeg):
    engine, watch, out = env
    start(engine)
    engine.pause()
    assert wait_for(lambda: engine.state == "paused")
    shutil.copy(photo_jpeg, watch / "while-paused.jpg")
    time.sleep(1)
    engine.resume()
    assert wait_for(lambda: engine.state == "running")
    time.sleep(3)
    assert not (out / "while-paused.webp").exists()  # arrived while paused = not new


def test_only_one_engine_at_a_time(env, tmp_path):
    engine, watch, out = env
    start(engine)
    other = Engine(engine.settings, None, ActivityLog(None), ProcessedStore(tmp_path / "p2.json"))
    other.start()
    assert wait_for(lambda: other.state == "locked")
    other.stop()


def test_convert_now_ignores_dedupe(env, photo_jpeg):
    engine, watch, out = env
    start(engine)
    assert engine.convert_now([photo_jpeg, photo_jpeg.parent / "missing.jpg"]) == 1
    assert wait_for(lambda: (out / "IMG_0001.webp").exists())
    engine.convert_now([photo_jpeg])
    assert wait_for(lambda: (out / "IMG_0001-1.webp").exists())


def test_seo_slug():
    assert seo_slug("IMG_1286 Beach Day") == "img-1286-beach-day"
    assert seo_slug("Café Menü – 2026!") == "cafe-menu-2026"
    assert seo_slug("###") == "file"


def test_empty_files_are_skipped_quickly(env):
    engine, watch, out = env
    start(engine)
    (watch / "empty.jpg").write_bytes(b"")
    assert wait_for(lambda: any(i["name"] == "empty.jpg" and i["status"] == "skipped"
                                for i in engine.activity.snapshot()), timeout=10)
    engine._rescan()  # the periodic rescan must not report it again
    time.sleep(1)
    assert sum(i["name"] == "empty.jpg" for i in engine.activity.snapshot()) == 1


def test_symlinks_are_never_followed(env, tmp_path):
    engine, watch, out = env
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    start(engine)
    (watch / "link.txt").symlink_to(secret)
    time.sleep(3)
    assert not (out / "link.md").exists()


def test_output_folder_cannot_be_the_watch_folder(env):
    engine, watch, out = env
    engine.settings.update({"general": {"output_folder": str(watch)}})
    engine.start()
    assert wait_for(lambda: engine.state == "error")
    assert "can't be the AirDrop folder" in engine.message


def test_long_names_and_quarantine_are_kept(env, photo_jpeg):
    engine, watch, out = env
    start(engine)
    long_name = "x" * 250 + ".jpg"
    staged = watch.parent / long_name
    shutil.copy(photo_jpeg, staged)
    subprocess.run(["xattr", "-w", "com.apple.quarantine", "0081;6ad5b83d;sharingd;X", str(staged)], check=True)
    subprocess.run(["ditto", str(staged), str(watch / long_name)], check=True)
    assert wait_for(lambda: any(p.suffix == ".webp" for p in out.glob("x*")))
    made = next(out.glob("x*.webp"))
    assert len(made.name.encode()) <= 255
    tag = subprocess.run(["xattr", "-p", "com.apple.quarantine", str(made)], capture_output=True, text=True)
    assert "sharingd" in tag.stdout


def test_damaged_image_gets_a_clear_message(env):
    engine, watch, out = env
    start(engine)
    (watch / "broken.jpg").write_bytes(b"not really a jpeg")
    assert wait_for(lambda: any(i["name"] == "broken.jpg" and i["status"] == "failed"
                                for i in engine.activity.snapshot()))
    item = next(i for i in engine.activity.snapshot() if i["name"] == "broken.jpg")
    assert item["message"] == "Not a valid image, or the file is damaged"
