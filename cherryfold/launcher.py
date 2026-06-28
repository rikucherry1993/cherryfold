"""Open a follow viewer beside the current shell.

Strategy (macOS-first, tmux for cross-platform), picked by environment:
  cmux            -> cmux new-split (native, mouse works)
  inside tmux     -> tmux split-window -h
  iTerm2 (macOS)  -> AppleScript split vertically
  other macOS     -> fallback: open a new Terminal.app window side by side
  non-macOS, no tmux -> print guidance to use tmux

`inner_cmd` is the argv that renders the viewer (e.g. the `view --follow` cli call);
it must use absolute paths so it does not depend on the new pane's cwd.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import subprocess


def _cmux_surface() -> str | None:
    """The cmux surface to split from, or None if we're not inside cmux.

    Prefer the injected env var; otherwise ask the cmux CLI (works even when the
    shell — e.g. a detached agent shell — didn't inherit CMUX_SURFACE_ID)."""
    s = os.environ.get("CMUX_SURFACE_ID")
    if s:
        return s
    try:
        out = subprocess.run(["cmux", "identify", "--json"],
                             capture_output=True, text=True, timeout=3)
        data = json.loads(out.stdout or "{}")
    except Exception:
        return None
    caller = data.get("caller") or {}
    focused = data.get("focused") or {}
    return caller.get("surface_ref") or focused.get("surface_ref")


def detect() -> str:
    cmux_bin = shutil.which("cmux")
    # explicit env var is definitive; otherwise confirm via the CLI (cmux renders
    # through ghostty) so a detached shell that lost CMUX_SURFACE_ID still works.
    if cmux_bin and os.environ.get("CMUX_SURFACE_ID"):
        return "cmux"
    if (cmux_bin and os.environ.get("TERM_PROGRAM") == "ghostty"
            and _cmux_surface() is not None):
        return "cmux"
    if os.environ.get("TMUX") and shutil.which("tmux"):
        return "tmux"
    if platform.system() == "Darwin":
        if os.environ.get("TERM_PROGRAM") == "iTerm.app":
            return "iterm2"
        return "macterm"          # fallback: new Terminal.app window
    return "none"


def launch(inner_cmd: list[str]) -> tuple[bool, str]:
    cmd_str = shlex.join(inner_cmd)
    target = detect()
    try:
        if target == "cmux":
            return _cmux(cmd_str)
        if target == "tmux":
            return _tmux(cmd_str)
        if target == "iterm2":
            return _iterm2(cmd_str)
        if target == "macterm":
            return _macterm(cmd_str)
        return (False,
                "This terminal can't be split programmatically. Run cherryfold "
                "inside tmux (then `cherryfold follow` splits the pane), or open "
                "another terminal and run: " + cmd_str)
    except Exception as e:  # never crash the caller's shell
        return (False, f"{target} launch failed: {e}\nRun manually: {cmd_str}")


def _cmux(cmd_str: str) -> tuple[bool, str]:
    args = ["cmux", "new-split", "right", "--focus", "false"]
    surface = _cmux_surface()
    if surface:
        args += ["--surface", surface]          # split from our surface, not a guess
    out = subprocess.run(args, capture_output=True, text=True)
    m = re.search(r"surface:\d+", out.stdout + out.stderr)
    if not m:
        return (False, f"cmux new-split gave no surface: {out.stdout}{out.stderr}")
    new = m.group(0)
    subprocess.run(["cmux", "send", "--surface", new, cmd_str + "\n"])
    return (True, f"Opened follow view in a cmux split ({new}). Mouse works.")


def _tmux(cmd_str: str) -> tuple[bool, str]:
    subprocess.run(["tmux", "split-window", "-h", cmd_str], check=True)
    subprocess.run(["tmux", "set", "mouse", "on"])   # needed for click/scroll
    subprocess.run(["tmux", "select-pane", "-L"])
    return (True, "Opened follow view in a tmux split (mouse enabled).")


def _as(s: str) -> str:
    """Escape a string for embedding inside an AppleScript double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _iterm2(cmd_str: str) -> tuple[bool, str]:
    script = f'''
    tell application "iTerm2"
        tell current session of current window
            set s to (split vertically with default profile)
        end tell
        tell s to write text "{_as(cmd_str)}"
    end tell
    '''
    subprocess.run(["osascript", "-e", script], check=True,
                   capture_output=True, text=True)
    return (True, "Opened follow view in an iTerm2 vertical split.")


def _macterm(cmd_str: str) -> tuple[bool, str]:
    script = f'''
    tell application "Terminal"
        activate
        do script "{_as(cmd_str)}"
    end tell
    '''
    subprocess.run(["osascript", "-e", script], check=True,
                   capture_output=True, text=True)
    return (True, "Terminal.app can't split; opened the follow view in a new "
                  "window beside this one.")
