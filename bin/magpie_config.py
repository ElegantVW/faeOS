#!/usr/bin/env python3
"""magpie_config — Magpie's settings: file, validation, env, wizard.

One JSON file, one schema, shared by the CLI and the TUI so they can never
disagree. Precedence: CLI flags > env vars > config file > builtins.

Config file: ~/.config/magpie/config.json (or $MAGPIE_CONFIG dir).
Env overrides: MAGPIE_ENGINE, MAGPIE_RESULTS, MAGPIE_TOR, MAGPIE_JS,
               MAGPIE_HOMEPAGE, MAGPIE_AI_BAR, MAGPIE_AI (on/off).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from magpie_fetch import config_dir


CONFIG_NAME = "config.json"

DEFAULTS: dict[str, object] = {
    "search.engine": "auto",
    "search.results": 8,
    "search.tor": False,
    "browse.js": "ask",
    "browse.homepage": "magpie:start",
    "browse.ai_bar": "right",
    "ai.enabled": True,
    "media.image_cap_mb": 12,
    "media.video_cap_mb": 12,
    "media.inline_images": 8,
}

ENGINES = ("auto", "ddg", "ddg-html", "marginalia")
JS_MODES = ("ask", "on", "off")
BAR_SIDES = ("left", "right")

ENV_MAP = {
    "MAGPIE_ENGINE": "search.engine",
    "MAGPIE_RESULTS": "search.results",
    "MAGPIE_TOR": "search.tor",
    "MAGPIE_JS": "browse.js",
    "MAGPIE_HOMEPAGE": "browse.homepage",
    "MAGPIE_AI_BAR": "browse.ai_bar",
    "MAGPIE_AI": "ai.enabled",
}

SECTIONS: list[tuple[str, list[str]]] = [
    ("search", ["search.engine", "search.results", "search.tor"]),
    ("browse", ["browse.js", "browse.homepage", "browse.ai_bar"]),
    ("ai", ["ai.enabled"]),
    ("media", ["media.image_cap_mb", "media.video_cap_mb", "media.inline_images"]),
]

HELP: dict[str, str] = {
    "search.engine": "search backend: auto chain, ddg, ddg-html, marginalia",
    "search.results": "results per search (1-25)",
    "search.tor": "route searches via Tor by default (needs torsocks)",
    "browse.js": "page scripts: ask per site, on, or off",
    "browse.homepage": "where bare magpie lands",
    "browse.ai_bar": "pixie bar side: left or right",
    "ai.enabled": "local pixie answers (menagerie picks the model)",
    "media.image_cap_mb": "max MB fetched per inline image",
    "media.video_cap_mb": "max MB fetched per video poster",
    "media.inline_images": "images auto-loaded per page (rest load on i)",
}


class ConfigError(Exception):
    """Human-readable settings failure."""


def config_path() -> Path:
    return config_dir() / CONFIG_NAME


def config_exists() -> bool:
    return config_path().is_file()


def _coerce(key: str, value: object) -> object:
    if key == "search.engine":
        v = str(value).strip().lower()
        if v not in ENGINES:
            raise ConfigError(f"engine must be one of: {', '.join(ENGINES)}")
        return v
    if key == "search.results":
        try:
            n = int(str(value).strip())
        except (TypeError, ValueError):
            raise ConfigError("results must be a whole number (1-25)")
        if not 1 <= n <= 25:
            raise ConfigError("results must be between 1 and 25")
        return n
    if key in ("search.tor", "ai.enabled"):
        return parse_bool(key, value)
    if key == "browse.js":
        v = str(value).strip().lower()
        if v not in JS_MODES:
            raise ConfigError(f"js mode must be one of: {', '.join(JS_MODES)}")
        return v
    if key == "browse.homepage":
        v = str(value).strip()
        if not v:
            raise ConfigError("homepage cannot be empty")
        return v
    if key == "browse.ai_bar":
        v = str(value).strip().lower()
        if v not in BAR_SIDES:
            raise ConfigError("ai bar side must be left or right")
        return v
    if key in ("media.image_cap_mb", "media.video_cap_mb", "media.inline_images"):
        try:
            n = int(str(value).strip())
        except (TypeError, ValueError):
            raise ConfigError(f"{key} must be a whole number")
        lo, hi = (1, 512) if key != "media.inline_images" else (1, 64)
        if not lo <= n <= hi:
            raise ConfigError(f"{key} must be between {lo} and {hi}")
        return n
    raise ConfigError(f"unknown setting: {key}")


def parse_bool(key: str, value: object) -> bool:
    if isinstance(value, bool):
        return value
    v = str(value).strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    raise ConfigError(f"{key} must be on/off (true/false, 1/0, yes/no)")


def load_file() -> dict[str, object]:
    """Read the JSON file (sanitized); missing/corrupt file → defaults."""
    cfg = dict(DEFAULTS)
    path = config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return cfg
    except (OSError, ValueError):
        return cfg
    if not isinstance(raw, dict):
        return cfg
    for key, value in raw.items():
        if key not in DEFAULTS:
            continue
        try:
            cfg[key] = _coerce(key, value)
        except ConfigError:
            continue
    return cfg


def save_file(cfg: dict[str, object]) -> None:
    """Validate + atomically write the full settings dict."""
    clean = {key: _coerce(key, cfg.get(key, DEFAULTS[key])) for key in DEFAULTS}
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def effective() -> dict[str, object]:
    """Defaults < file < env. Always returns a complete, valid dict."""
    cfg = load_file()
    for env_key, key in ENV_MAP.items():
        raw = os.environ.get(env_key, "")
        if raw.strip():
            try:
                cfg[key] = _coerce(key, raw)
            except ConfigError:
                continue
    return cfg


def get(key: str) -> object:
    if key not in DEFAULTS:
        raise ConfigError(f"unknown setting: {key} (try: magpie config list)")
    return effective()[key]


def set_key(key: str, value: str) -> object:
    if key not in DEFAULTS:
        raise ConfigError(f"unknown setting: {key} (try: magpie config list)")
    cfg = load_file()
    cfg[key] = _coerce(key, value)
    save_file(cfg)
    return cfg[key]


def reset() -> None:
    save_file(dict(DEFAULTS))


# ── wizard ───────────────────────────────────────────────────────────────

def _prompt(key: str, current: object) -> object:
    hint = HELP.get(key, "")
    while True:
        try:
            raw = input(f"  {key} [{current}]  {hint}\n  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raise ConfigError("wizard cancelled — nothing saved")
        if not raw:
            return current
        try:
            return _coerce(key, raw)
        except ConfigError as e:
            print(f"  magpie: {e} — try again")


def run_wizard(*, sections: list[str] | None = None) -> dict[str, object]:
    """Interactive setup. Returns the saved config. Raises ConfigError on cancel."""
    import sys
    if not sys.stdin.isatty():
        raise ConfigError("wizard needs a real terminal (not a pipe)")
    cfg = load_file()
    wanted = sections or [name for name, _ in SECTIONS]
    print("magpie setup — Enter keeps what's in [brackets].")
    for name, keys in SECTIONS:
        if name not in wanted:
            continue
        print(f"\n[{name}]")
        for key in keys:
            cfg[key] = _prompt(key, cfg.get(key, DEFAULTS[key]))
    try:
        keep = input("\nSave these settings? [Y/n] > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        raise ConfigError("wizard cancelled — nothing saved")
    if keep not in ("", "y", "yes"):
        raise ConfigError("wizard cancelled — nothing saved")
    save_file(cfg)
    print(f"magpie: settings saved to {config_path()}")
    return cfg


def offer_first_run() -> bool:
    """Ask once whether to run the wizard. True = ran (or already set up)."""
    import sys
    if config_exists() or not sys.stdin.isatty():
        return False
    try:
        answer = input("magpie: first visit — run the quick setup? [Y/n] > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if answer not in ("", "y", "yes"):
        return False
    try:
        run_wizard()
    except ConfigError as e:
        print(f"magpie: {e}")
        return False
    return True
