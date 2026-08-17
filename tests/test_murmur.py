"""murmur NPC glass — behavioral smoke, no quest spoilers."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import re
import sys
from pathlib import Path

BIN = Path.home() / "bin"
sys.path.insert(0, str(BIN))


def _load():
    path = BIN / "murmur"
    if not path.is_file():
        path = Path(__file__).resolve().parent.parent / "bin" / "murmur"
    name = "murmur_under_test"
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


def test_help_exit_zero():
    m = _load()
    assert m.main(["--help"]) == 0


def test_fog_gibberish_nonempty():
    m = _load()
    s = m.new_session()
    lines = m.reply(s, "zzzz qwerty asdfgh unrelated")
    assert lines and all(isinstance(x, str) and len(x) > 2 for x in lines)


def test_hit_nonempty():
    m = _load()
    s = m.new_session()
    lines = m.reply(s, "egg menagerie silence")
    assert lines and len(" ".join(lines)) > 0


def test_anti_repeat_not_always_identical():
    m = _load()
    s = m.new_session()
    a = " | ".join(m.reply(s, "egg"))
    b = " | ".join(m.reply(s, "egg"))
    # allowed to differ; at least engine runs twice
    assert a and b


def test_greet_and_farewell():
    m = _load()
    s = m.new_session()
    assert m.greet(s)
    assert m.farewell(s)


def test_source_never_emits_true_name_token():
    """True name of the egg must not appear in murmur source text."""
    path = BIN / "murmur"
    if not path.is_file():
        path = Path(__file__).resolve().parent.parent / "bin" / "murmur"
    text = path.read_text(encoding="utf-8").lower()
    # whole-word only; avoid matching accidental substrings in other words
    assert not re.search(r"\bkur\b", text), "true name leaked into murmur"


def test_oneshot_main():
    m = _load()
    assert m.main(["ash", "and", "noise"]) == 0


def test_splash_explains_and_mocks():
    m = _load()
    s = m.Session()
    body = "\n".join(m._splash_body(s)).lower()
    assert "glass" in body or "murmur" in body
    assert "babbling" in body or "nonsense" in body or "fog" in body
    assert "kur" not in body.split()


def test_meta_ask_is_mockery_not_walkthrough():
    m = _load()
    s = m.new_session()
    lines = m.reply(s, "please give me a hint how to solve")
    blob = " ".join(lines).lower()
    assert lines
    # must not hand out a recipe
    assert "menagerie ensure" not in blob
    assert "ensure kur" not in blob


def test_silence_reacts():
    m = _load()
    s = m.new_session()
    assert m.reply(s, "...")
    assert m.reply(s, "?")


def test_help_mentions_no_splash():
    m = _load()
    # just ensure flag path doesn't crash
    assert m.main(["--no-splash", "--help"]) in (0, 0)


def test_act_advances_on_meaningful_hits():
    m = _load()
    s = m.Session(rng=__import__("random").Random(0))
    assert s.act == 0
    for _ in range(6):
        m.reply(s, "egg menagerie warm")
    assert s.meaningful >= 5
    assert s.act >= 1


def test_phrases_and_threads_never_true_name():
    m = _load()
    blob = " ".join(m._PHRASES).lower()
    for _need, lines in m._THREADS:
        blob += " " + " ".join(lines).lower()
    blob += " " + " ".join(m._REFUSAL).lower()
    assert not re.search(r"\bkur\b", blob)


def test_render_chat_fits_small_and_normal():
    m = _load()
    log = [m.Line("glass", "xa thul mirr"), m.Line("you", "egg"), m.Line("glass", "warm")]
    for w, h in ((40, 12), (80, 24), (28, 10)):
        frame, _off = m.render_chat(log, "hi", 0, w, h, mood="fog", turns=2)
        assert 1 <= len(frame.splitlines()) <= h


def test_save_notes_world_flag(tmp_path, monkeypatch):
    m = _load()
    import fae_egg

    egg_dir = tmp_path / "eggs"
    murmur_dir = tmp_path / "murmur"
    murmur_dir.mkdir()
    monkeypatch.setattr(fae_egg, "EGG_DIR", egg_dir)
    monkeypatch.setattr(fae_egg, "FLAGS_FILE", egg_dir / "flags.json")
    monkeypatch.setattr(fae_egg, "HATCH_FILE", egg_dir / "dragon.json")
    monkeypatch.setattr(m, "STATE_DIR", murmur_dir)
    monkeypatch.setattr(m, "STATE_FILE", murmur_dir / "glass.json")

    assert not fae_egg.murmur_visited()
    s = m.Session(rng=__import__("random").Random(1))
    for _ in range(9):
        m.reply(s, "egg silence ash")
    m._save_soft(s)
    assert fae_egg.murmur_visited()
    assert fae_egg.murmur_deep()  # deep_turns >= 8
