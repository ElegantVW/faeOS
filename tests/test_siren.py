"""Tests for siren (the Aether's music vessel).

Pure-logic coverage only — no real mpv, no real ~/Music, no TTY.
Isolated via SIREN_CONFIG_DIR / SIREN_CACHE_DIR / SIREN_SOCK env overrides.

Run:  python3 -m pytest tests/
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))

_TMP = Path(tempfile.mkdtemp(prefix="siren-test-"))
os.environ["SIREN_CONFIG_DIR"] = str(_TMP / "config")
os.environ["SIREN_CACHE_DIR"] = str(_TMP / "cache")
os.environ["SIREN_SOCK"] = str(_TMP / "siren-mpv.sock")
os.environ["NO_COLOR"] = "1"
os.environ["PIXIE_UNICODE"] = "1"

import importlib.util  # noqa: E402
import importlib.machinery  # noqa: E402

_loader = importlib.machinery.SourceFileLoader(  # noqa: E402
    "siren", str(Path(__file__).resolve().parent.parent / "bin" / "siren"))
_spec = importlib.util.spec_from_loader("siren", _loader)
siren = importlib.util.module_from_spec(_spec)
sys.modules["siren"] = siren
_spec.loader.exec_module(siren)


@pytest.fixture
def tmp_music(tmp_path: Path) -> Path:
    """A tiny fake library tree with a couple of audio files."""
    root = tmp_path / "Music"
    (root / "Album A").mkdir(parents=True)
    (root / "Album B").mkdir(parents=True)
    a1 = root / "Album A" / "Night Drive.flac"
    a2 = root / "Album A" / "Morning Light.mp3"
    b1 = root / "Album B" / "Deep Waters.wav"
    for f in (a1, a2, b1):
        f.write_bytes(b"\x00" * 128)
    (root / "notes.txt").write_text("not audio", encoding="utf-8")
    return root


# ── config round-trip ─────────────────────────────────────────────────

def test_config_defaults():
    cfg = siren.SirenConfig()
    assert cfg.default_volume == 75
    assert cfg.library_roots == ["~/Music"]
    assert cfg.fuzzy_search is True
    assert cfg.wave_bands == 16


def test_config_save_load_roundtrip(tmp_path):
    siren.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = siren.SirenConfig()
    cfg.default_volume = 120
    cfg.wave_bands = 32
    cfg.normalize = True
    cfg.save()
    reloaded = siren.SirenConfig.load()
    assert reloaded.default_volume == 120
    assert reloaded.wave_bands == 32
    assert reloaded.normalize is True
    assert reloaded.gapless is True


def test_config_load_sanitizes(tmp_path):
    cfg_file = siren.CONFIG_DIR / "config.json"
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(json.dumps({
        "default_volume": 999,
        "wave_bands": 5,
        "library_roots": [],
        "fuzzy_search": False,
    }), encoding="utf-8")
    cfg = siren.SirenConfig.load()
    assert cfg.default_volume == 75
    assert cfg.wave_bands == 16
    assert cfg.library_roots == ["~/Music"]
    assert cfg.fuzzy_search is False


def test_cli_set_config():
    ok, msg = siren.cli_set_config("default_volume", "42")
    assert ok and msg == "42"
    assert siren.CFG.default_volume == 42
    ok, msg = siren.cli_set_config("default_volume", "42")
    assert ok
    ok, msg = siren.cli_set_config("default_volume", "9999")
    assert not ok
    ok, msg = siren.cli_set_config("wave_bands", "32")
    assert ok
    ok, msg = siren.cli_set_config("wave_bands", "10")
    assert not ok
    ok, msg = siren.cli_set_config("fuzzy_search", "off")
    assert ok and msg == "off"
    assert siren.CFG.fuzzy_search is False
    ok, msg = siren.cli_set_config("nonsense", "x")
    assert not ok


# ── fuzzy scoring tiers ───────────────────────────────────────────────

@pytest.mark.parametrize("query,text,tier", [
    ("night drive", "night drive", 10),      # exact
    ("night", "night drive", 9),             # prefix
    ("drive", "night drive", 8),             # substring
    ("drive night", "night drive xx", 7),    # all tokens (any order)
    ("night drive zzz", "night drive", 6),   # ordered subsequence, one missing
    ("zzz", "night drive", 0),               # no match
    ("", "night drive", 0),                  # empty query
])
def test_fuzzy_tiers(query, text, tier):
    assert siren.fuzzy_score(query, text)[0] == tier


def test_fuzzy_exact_beats_prefix():
    a = siren.fuzzy_score("night", "night drive")
    b = siren.fuzzy_score("night", "night")
    assert a[0] == 9 and b[0] == 10
    assert a[0] < b[0]  # exact tiers above prefix


def test_fuzzy_ranked_order(tmp_music):
    siren.CFG.library_roots = [str(tmp_music)]
    hits = siren.resolve_library("night")
    assert hits
    assert hits[0].name == "Night Drive.flac"


def test_resolve_library_empty_query_returns_all(tmp_music):
    siren.CFG.library_roots = [str(tmp_music)]
    assert len(siren.resolve_library("")) == 3


def test_scan_library_filters_extensions(tmp_music):
    siren.CFG.library_roots = [str(tmp_music)]
    files = siren.scan_library()
    names = sorted(f.name for f in files)
    assert names == ["Deep Waters.wav", "Morning Light.mp3", "Night Drive.flac"]
    assert "notes.txt" not in names


# ── metadata cache ────────────────────────────────────────────────────

def test_meta_display_filename_fallback(tmp_path):
    f = tmp_path / "Some_Track-Edit.wav"
    f.write_bytes(b"\x00" * 64)
    siren.CFG.cache_meta = True
    siren._META.clear()
    siren._META_DIRTY = False
    assert siren.meta_display(str(f)) == "Some Track - Edit"
    assert str(f) in siren._META
    assert siren._META[str(f)]["d"] == "Some Track - Edit"
    siren._META_DIRTY = False
    assert siren.meta_display(str(f)) == "Some Track - Edit"
    assert siren._META_DIRTY is False


def test_meta_cache_persists(tmp_path):
    f = tmp_path / "Persist.flac"
    f.write_bytes(b"\x00" * 64)
    siren.CFG.cache_meta = True
    siren._META.clear()
    siren._META_DIRTY = False
    siren.meta_display(str(f))
    siren.meta_cache_save()
    siren._META.clear()
    siren.meta_cache_load()
    assert siren._META.get(str(f), {}).get("d") == "Persist"


def test_meta_display_stale_cache_invalidated(tmp_path):
    f = tmp_path / "Stale.mp3"
    f.write_bytes(b"\x00" * 64)
    siren.CFG.cache_meta = True
    siren._META.clear()
    siren._META_DIRTY = False
    first = siren.meta_display(str(f))
    siren._META[str(f)] = {"m": -1, "d": "Old Name"}
    assert siren.meta_display(str(f)) != "Old Name"


def test_meta_display_unknown_path():
    assert siren.meta_display("") == "Unknown Track"


# ── queue ─────────────────────────────────────────────────────────────

def test_queue_add_remove_clear(tmp_path):
    q = siren.Queue()
    f1 = tmp_path / "One.mp3"
    f2 = tmp_path / "Two.mp3"
    f1.write_bytes(b"\x00" * 64)
    f2.write_bytes(b"\x00" * 64)
    assert q.add(str(f1)) == 1
    assert q.add(str(f2)) == 2
    assert q.add(str(f2), prepend=True) == 3
    assert q.items[0].path == str(f2)
    assert len(q) == 3
    assert q.remove(0).path == str(f2)
    assert q.move(0, 1)
    assert q.items[-1].path == str(f1)
    q.clear()
    assert len(q) == 0


def test_queue_validate_drops_missing(tmp_path):
    q = siren.Queue()
    real = tmp_path / "Real.mp3"
    real.write_bytes(b"\x00" * 64)
    gone = tmp_path / "Gone.mp3"
    q.add(str(real))
    q.add(str(gone))
    removed = q.validate()
    assert len(removed) == 1
    assert removed[0][0].path == str(gone)
    assert len(q) == 1


def test_queue_metadata_snapshotted(tmp_path):
    q = siren.Queue()
    f = tmp_path / "Snap.mp3"
    f.write_bytes(b"\x00" * 64)
    q.add(str(f))
    assert q.items[0].display  # non-empty at add time


# ── playlists (JSON) ──────────────────────────────────────────────────

def test_playlist_save_load_list_remove(tmp_path):
    siren.PLAYLIST_DIR.mkdir(parents=True, exist_ok=True)
    f = tmp_path / "T.mp3"
    f.write_bytes(b"\x00" * 64)
    q = siren.Queue()
    q.add(str(f))
    assert siren.playlist_save("alpha", q.items)
    raw = json.loads((siren.PLAYLIST_DIR / "alpha.json").read_text(encoding="utf-8"))
    assert raw["name"] == "alpha"
    assert raw["tracks"][0]["path"] == str(f)
    assert "alpha" in siren.playlist_names()
    found = siren.playlist_find("alpha")
    assert found is not None
    assert siren.playlist_delete("alpha")
    assert "alpha" not in siren.playlist_names()


def test_playlist_delete_missing():
    siren.PLAYLIST_DIR.mkdir(parents=True, exist_ok=True)
    assert siren.playlist_delete("does-not-exist-xyz") is False


# ── resolve_play_args ─────────────────────────────────────────────────

def test_resolve_play_args_unknown_target_returns_empty(tmp_music):
    siren.CFG.library_roots = [str(tmp_music)]
    assert siren.resolve_play_args(["zzzz-nothing-matches"]) == []


def test_resolve_play_args_fuzzy(tmp_music):
    siren.CFG.library_roots = [str(tmp_music)]
    files = siren.resolve_play_args(["deep"])
    assert [f.name for f in files] == ["Deep Waters.wav"]


def test_resolve_play_args_existing_file(tmp_music):
    f = tmp_music / "Album B" / "Deep Waters.wav"
    assert siren.resolve_play_args([str(f)]) == [f]


# ── mpv client ────────────────────────────────────────────────────────

def test_player_alive_false_when_no_socket():
    siren.SOCK = os.environ["SIREN_SOCK"]
    p = siren.Player(siren.SOCK)
    if os.path.exists(siren.SOCK):
        os.unlink(siren.SOCK)
    assert p.alive() is False


def test_player_get_returns_default_when_dead():
    siren.SOCK = os.environ["SIREN_SOCK"]
    p = siren.Player(siren.SOCK)
    if os.path.exists(siren.SOCK):
        os.unlink(siren.SOCK)
    assert p.get("volume", 99) == 99


# ── misc ──────────────────────────────────────────────────────────────

def test_fmt_clock():
    assert siren.fmt_clock(0) == "0:00"
    assert siren.fmt_clock(125) == "2:05"
    assert siren.fmt_clock(3600) == "60:00"


def test_audio_ext_membership():
    assert ".wav" in siren.AUDIO_EXT
    assert ".mp3" in siren.AUDIO_EXT
    assert ".txt" not in siren.AUDIO_EXT
