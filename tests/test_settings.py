import json

import pytest

from airdrop_compress.settings import (Settings, SettingsManager, ValidationError, describe, from_dict,
                                       resolve_output_folder, resolve_watch_folder)


def test_defaults_match_v1_behaviour():
    s = Settings()
    assert s.images.format == "webp" and s.images.webp_quality == 80
    assert s.images.metadata == "keep" and s.images.color == "keep"
    assert s.general.output_folder == "airdrop-compress"
    assert s.general.skip_web_downloads and s.documents.enabled and s.documents.max_size_mb == 100


def test_partial_update_persists(settings_mgr):
    settings_mgr.update({"images": {"format": "avif", "avif_quality": 55}})
    again = SettingsManager(settings_mgr.path)
    assert again.current.images.format == "avif"
    assert again.current.images.avif_quality == 55
    assert again.current.images.webp_quality == 80  # untouched


@pytest.mark.parametrize("patch", [
    {"images": {"format": "gif"}},
    {"images": {"webp_quality": 0}},
    {"images": {"webp_quality": 101}},
    {"images": {"webp_quality": "high"}},
    {"images": {"seo_filenames": "yes"}},
    {"images": {"responsive_widths": [5]}},
    {"general": {"workers": 99}},
    {"images": {"nope": 1}},
])
def test_invalid_values_are_rejected(settings_mgr, patch):
    with pytest.raises(ValidationError):
        settings_mgr.update(patch)
    assert settings_mgr.current == Settings()  # nothing changed


def test_lenient_load_keeps_good_values(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"images": {"format": "bogus", "jpeg_quality": 70}, "general": "x"}))
    s = SettingsManager(path).current
    assert s.images.format == "webp" and s.images.jpeg_quality == 70


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert SettingsManager(path).current == Settings()


def test_responsive_widths_are_sorted_and_unique(settings_mgr):
    settings_mgr.update({"images": {"responsive_widths": [800, 480, 800]}})
    assert settings_mgr.current.images.responsive_widths == [480, 800]


def test_reset_section_keeps_others(settings_mgr):
    settings_mgr.update({"images": {"format": "jpeg"}, "documents": {"max_size_mb": 10}})
    settings_mgr.reset("images")
    assert settings_mgr.current.images.format == "webp"
    assert settings_mgr.current.documents.max_size_mb == 10


def test_listeners_see_old_and_new(settings_mgr):
    seen = []
    settings_mgr.subscribe(lambda old, new: seen.append((old.images.format, new.images.format)))
    settings_mgr.update({"images": {"format": "auto"}})
    assert seen == [("webp", "auto")]


def test_reload_picks_up_external_edit(settings_mgr):
    other = SettingsManager(settings_mgr.path)
    other.update({"general": {"notifications": False}})
    import os, time
    os.utime(settings_mgr.path, (time.time() + 5, time.time() + 5))
    assert settings_mgr.reload_if_changed()
    assert settings_mgr.current.general.notifications is False


def test_folders(tmp_path, monkeypatch):
    s = from_dict({"general": {"watch_folder": str(tmp_path), "output_folder": "out"}})
    assert resolve_watch_folder(s) == tmp_path
    assert resolve_output_folder(s) == tmp_path / "out"
    s = from_dict({"general": {"watch_folder": str(tmp_path), "output_folder": str(tmp_path / "abs")}})
    assert resolve_output_folder(s) == tmp_path / "abs"
    monkeypatch.setenv("AIRDROP_DIR", "/tmp/elsewhere")
    assert str(resolve_watch_folder(s)) == "/tmp/elsewhere"


def test_describe_exposes_choices():
    d = describe()
    assert d["images"]["format"]["choices"] == ["auto", "webp", "avif", "jpeg"]
    assert d["images"]["webp_quality"]["min"] == 1
