"""User config: theme, display density, and customizable glyphs.

Stored as JSON at ~/.config/cherryfold/config.json. Missing keys fall back to
DEFAULTS, so partial / hand-edited files are fine.

Note on font size: a terminal TUI cannot set its own font size — that is the
terminal emulator's job (Cmd/Ctrl +/- to zoom). What we offer instead is a
display *density* (comfortable vs compact spacing).
"""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "cherryfold"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS: dict = {
    "theme": "textual-dark",
    "density": "comfortable",          # comfortable | compact
    "follow_interval": 1.5,
    "icons": {
        "text": "💬",
        "thinking": "🧠",
        "tool": "🔧",
        "subagent": "🤖",
        "prompt": "📨",
        "copy": "📋",
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        raw = {}
    return _merge(DEFAULTS, raw)


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                           encoding="utf-8")
