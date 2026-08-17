"""Scroll encyclopedia + egg quest (no spoilers in asserts)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "bin"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))

import scroll_pages as pages  # noqa: E402
import fae_egg  # noqa: E402


REQUIRED = {
    "scroll", "summon", "siren", "pixie", "menagerie", "imp", "ether", "goblin",
    "magpie", "scry", "spellbook", "tome", "grimoire", "faectl", "eye", "vault",
    "alchemy", "abacus", "quests", "hourglass", "almanac", "bulwark", "imbue",
    "reflection", "zen", "fairy", "tick", "wisp", "seal", "hearth", "rift",
}

# Phrases that would hand-hold the hermetic quest
_BANNED_HERMETIC = (
    "first letter",
    "first letters",
    "initials",
    "take the first",
)


def test_all_required_pages_present():
    ids = {p.id for p in pages.PAGES}
    assert not (REQUIRED - ids)


def test_static_no_kur_token():
    pages.assert_no_kur_in_static()


def test_curriculum_covers_static_pages():
    assert set(pages.CURRICULUM) == {p.id for p in pages.PAGES}


def test_hermetic_names_murmur_and_menagerie_not_handhold():
    h = pages.hermetic_page()
    blob = " ".join([h.tagline, *h.intro, *h.how] + [c for c, _ in h.cli]).lower()
    assert "murmur" in blob
    assert "menagerie" in blob
    assert "egg" in blob
    for bad in _BANNED_HERMETIC:
        assert bad not in blob
    # no true-name command table
    assert "kur" not in blob.split()


def test_each_page_has_structure():
    for p in pages.PAGES:
        assert p.tagline.strip() and p.intro and p.how and p.cli


def test_egg_hatch_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(fae_egg, "EGG_DIR", tmp_path)
    monkeypatch.setattr(fae_egg, "HATCH_FILE", tmp_path / "dragon.json")
    monkeypatch.setattr(fae_egg, "FLAGS_FILE", tmp_path / "flags.json")
    assert not fae_egg.is_hatched()
    fae_egg.mark_hatched(source="test")
    assert fae_egg.is_hatched()


def test_murmur_world_flags_tint_hermetic(tmp_path, monkeypatch):
    monkeypatch.setattr(fae_egg, "EGG_DIR", tmp_path)
    monkeypatch.setattr(fae_egg, "HATCH_FILE", tmp_path / "dragon.json")
    monkeypatch.setattr(fae_egg, "FLAGS_FILE", tmp_path / "flags.json")

    base = pages.hermetic_page()
    assert "has not hatched" in base.tagline.lower() or "egg" in base.tagline.lower()

    fae_egg.note_murmur_visit(deep_turns=2)
    mid = pages.hermetic_page()
    mid_blob = " ".join(mid.intro).lower()
    assert "sat with the glass" in mid_blob or "chair" in mid_blob

    fae_egg.note_murmur_visit(deep_turns=10)
    deep = pages.hermetic_page()
    assert fae_egg.murmur_deep()
    deep_blob = " ".join(deep.how).lower() + " " + deep.tagline.lower()
    assert "notice" in deep_blob or "lean" in deep_blob
    for bad in _BANNED_HERMETIC:
        assert bad not in deep_blob
    assert "kur" not in deep_blob.split()
