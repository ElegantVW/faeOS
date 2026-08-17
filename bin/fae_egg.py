#!/usr/bin/env python3
"""Dragon egg — hatch state for the hidden familiar.

Pre-hatch: Sealed Leaf in Scroll; opaque vendor backends may exist.
Post-hatch: Kur page unlocked; rename cascade when possible.

Hatch only after a successful true-name speech at the shell — not from murmur.
Quest design is not documented here.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

EGG_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "faeos" / "eggs"
HATCH_FILE = EGG_DIR / "dragon.json"
FLAGS_FILE = EGG_DIR / "flags.json"

RENAME_MAP = (
    ("vendor/smoltide", "kur"),
    ("vendor/smoltide-d", "kur-server"),
    ("vendor/smoltide_voice.py", "kur_voice.py"),
)


def egg_dir() -> Path:
    EGG_DIR.mkdir(parents=True, exist_ok=True)
    return EGG_DIR


def _read_flags() -> dict:
    try:
        return json.loads(FLAGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _write_flags(data: dict) -> None:
    egg_dir()
    tmp = FLAGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(FLAGS_FILE)


def is_hatched() -> bool:
    try:
        data = json.loads(HATCH_FILE.read_text(encoding="utf-8"))
        return bool(data.get("hatched"))
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def note_murmur_visit(*, deep_turns: int = 0) -> None:
    """Boolean world flags only — no quest solutions stored."""
    f = _read_flags()
    f["visited_murmur"] = True
    f["murmur_visits"] = int(f.get("murmur_visits", 0)) + 1
    f["murmur_deep_turns"] = max(int(f.get("murmur_deep_turns", 0)), int(deep_turns))
    f["murmur_last"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        _write_flags(f)
    except OSError:
        pass


def murmur_visited() -> bool:
    return bool(_read_flags().get("visited_murmur"))


def murmur_deep() -> bool:
    """True if someone sat long enough for the glass to 'notice'."""
    return int(_read_flags().get("murmur_deep_turns", 0)) >= 8


def mark_hatched(*, source: str = "command") -> None:
    egg_dir()
    payload = {
        "hatched": True,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source,
    }
    tmp = HATCH_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(HATCH_FILE)
    try:
        cascade_rename()
    except OSError:
        pass


def cascade_rename() -> list[str]:
    done: list[str] = []
    homes = [Path.home() / "bin", Path.home() / "faeos" / "bin"]
    for base in homes:
        if not base.is_dir():
            continue
        for src_rel, dst_name in RENAME_MAP:
            src = base / src_rel
            dst = base / dst_name
            if src.is_file() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                done.append(f"{src} → {dst}")
            flat = base / Path(src_rel).name
            if flat.is_file() and flat.name.startswith("smoltide") and not dst.exists():
                shutil.move(str(flat), str(dst))
                done.append(f"{flat} → {dst}")
    unit_src = Path.home() / "faeos" / "systemd" / "smoltide.service"
    unit_dst = Path.home() / "faeos" / "systemd" / "kur-server.service"
    if unit_src.is_file() and not unit_dst.exists():
        text = unit_src.read_text(encoding="utf-8")
        text = text.replace("smoltide", "kur").replace("Smoltide", "Kur")
        unit_dst.write_text(text, encoding="utf-8")
        done.append(str(unit_dst))
    return done


def try_hatch_from_kur_success() -> bool:
    if is_hatched():
        return False
    mark_hatched(source="true-name-speech")
    return True
