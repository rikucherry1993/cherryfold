"""Parse Claude Code JSONL session logs into a tree of steps.

Data model (observed from $CLAUDE_CONFIG_DIR/projects/*/*.jsonl):
  - One JSON record per line. Relevant `type`: user / assistant (rest is meta).
  - Common fields: uuid / parentUuid / isSidechain / timestamp / message.
  - assistant.message.content: [ {type: thinking|text|tool_use} ... ]
  - user.message.content: str (human input) or [ {type: text|tool_result} ... ]
      A user record made only of tool_result is plumbing, not a step.

Output: Session.steps — one Step per human input on the main chain, each holding
the assistant's text / thinking / tool_use events (tool_use matched back to its
tool_result). Sidechain (sub-agent) records are flagged via isSidechain.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Event:
    """A collapsible unit inside a step."""
    kind: str            # "text" | "thinking" | "tool" | "subagent"
    title: str           # one-line header shown on the fold
    body: str            # expanded content (prose, may contain ``` fences)
    tool_name: str = ""
    command: str = ""    # tools: primary input (command/path), copyable
    result: str = ""     # tools: the tool_result output
    sidechain: bool = False


@dataclass
class Step:
    """One human input plus all the agent work that followed it."""
    index: int
    prompt: str          # cleaned / truncated human input for the outline
    raw_prompt: str
    timestamp: str
    uuid: str
    events: list[Event] = field(default_factory=list)

    @property
    def outline_label(self) -> str:
        return _one_line(self.prompt, 60) or "(empty input)"


@dataclass
class Session:
    path: Path
    steps: list[Step] = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.path.stem[:8]


# ---------- helpers ----------

def _one_line(s: str, limit: int = 80) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _clean_prompt(s: str) -> str:
    """Strip machine-injected wrapper tags, keep the human text."""
    s = s.strip()
    for tag in ("<bridge_context>", "<command-message>", "<command-name>",
                "<local-command-stdout>", "<system-reminder>"):
        if s.startswith(tag):
            end = s.find(">", s.find("</"))
            if end != -1:
                s = s[end + 1:].strip()
    return s


def _short_json(obj, limit: int = 70) -> str:
    try:
        return _one_line(json.dumps(obj, ensure_ascii=False), limit)
    except Exception:
        return _one_line(str(obj), limit)


def _tool_title(name: str, inp: dict) -> str:
    """A recognizable one-line header for a tool_use fold."""
    inp = inp or {}
    if name == "Bash":
        hint = inp.get("description") or inp.get("command", "")
    elif name in ("Read", "Edit", "Write"):
        hint = inp.get("file_path", "")
    elif name in ("Grep", "Glob"):
        hint = inp.get("pattern", "")
    elif name in ("Task", "Agent"):
        hint = inp.get("description", "")
    elif name == "Skill":
        hint = inp.get("skill", "")
    else:
        hint = _short_json(inp)
    return f"{name}  {_one_line(hint, 60)}".rstrip()


def _tool_command(name: str, inp: dict) -> str:
    """The primary thing worth copying from a tool call."""
    inp = inp or {}
    if name == "Bash":
        return inp.get("command", "")
    if name in ("Read", "Edit", "Write"):
        return inp.get("file_path", "")
    if name in ("Grep", "Glob"):
        return inp.get("pattern", "")
    return json.dumps(inp, ensure_ascii=False, indent=2)


def _result_to_text(result) -> str:
    """A tool_result's content may be str or [{type:text,text}]."""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        parts = []
        for b in result:
            if isinstance(b, dict):
                parts.append(b.get("text", "") or b.get("content", ""))
            else:
                parts.append(str(b))
        return "\n".join(p for p in parts if p)
    return str(result) if result is not None else ""


# ---------- main parse ----------

def load_session(path: Path) -> Session:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    session = Session(path=path)
    current: Step | None = None
    tool_index: dict[str, Event] = {}   # tool_use_id -> Event awaiting its result
    step_n = 0

    for rec in records:
        rtype = rec.get("type")
        if rtype not in ("user", "assistant"):
            continue
        msg = rec.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        sidechain = bool(rec.get("isSidechain"))

        if rtype == "user":
            human = _extract_human_prompt(content)
            if human is not None and not sidechain:
                step_n += 1
                current = Step(
                    index=step_n,
                    prompt=_clean_prompt(human),
                    raw_prompt=human,
                    timestamp=rec.get("timestamp", ""),
                    uuid=rec.get("uuid", ""),
                )
                session.steps.append(current)
            else:
                _attach_results(content, tool_index)
            continue

        # assistant
        if current is None:
            step_n += 1
            current = Step(step_n, "(session start)", "", rec.get("timestamp", ""), "")
            session.steps.append(current)

        if isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "text":
                    txt = b.get("text", "").strip()
                    if txt:
                        current.events.append(Event(
                            kind="text",
                            title=_one_line(txt, 58),
                            body=txt,
                            sidechain=sidechain,
                        ))
                elif bt == "thinking":
                    th = b.get("thinking", "").strip()
                    if th:
                        current.events.append(Event(
                            kind="thinking",
                            title="thinking · " + _one_line(th, 48),
                            body=th,
                            sidechain=sidechain,
                        ))
                elif bt == "tool_use":
                    name = b.get("name", "?")
                    inp = b.get("input", {})
                    command = _tool_command(name, inp)
                    ev = Event(
                        kind="tool",
                        title=_tool_title(name, inp),
                        body=command,
                        tool_name=name,
                        command=command,
                        sidechain=sidechain,
                    )
                    current.events.append(ev)
                    tid = b.get("id")
                    if tid:
                        tool_index[tid] = ev

    return session


def _extract_human_prompt(content) -> str | None:
    """Return the human text if this user record is a real prompt, else None."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        has_tool_result = any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
        if texts and not has_tool_result:
            return "\n".join(t for t in texts if t)
    return None


def _attach_results(content, tool_index: dict[str, Event]) -> None:
    if not isinstance(content, list):
        return
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_result":
            ev = tool_index.get(b.get("tool_use_id"))
            if ev is not None:
                text = _result_to_text(b.get("content")) or "(empty)"
                ev.result = ev.result + "\n" + text if ev.result else text


# ---------- session discovery ----------

def projects_dir() -> Path:
    """Where Claude Code keeps session logs: $CLAUDE_CONFIG_DIR/projects, or
    ~/.claude/projects by default. Mirrors Claude Code's own config resolution,
    so it works for everyone without hard-coding any personal path."""
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(base).expanduser() if base else Path.home() / ".claude"
    return base / "projects"


def _slug(p: Path) -> str:
    # Claude Code names a project dir after its launch cwd, with "/" and "." -> "-".
    return str(p).replace("/", "-").replace(".", "-")


def project_dir_for(cwd: Path, root: Path | None = None) -> Path | None:
    """The project dir owning cwd, or its nearest ancestor (walk up)."""
    root = root or projects_dir()
    if not root.is_dir():
        return None
    cur = Path(cwd)
    for d in [cur, *cur.parents]:
        cand = root / _slug(d)
        if cand.is_dir():
            return cand
    return None


def find_sessions(cwd: Path | None = None, all_projects: bool = False) -> list[Path]:
    """Session files, newest first. By default scoped to the project owning cwd
    (or its nearest ancestor up the tree); all_projects=True lists everything."""
    root = projects_dir()
    if not root.is_dir():
        return []
    if all_projects:
        candidates = list(root.glob("*/*.jsonl"))
    elif cwd is None:
        return []
    else:
        proj = project_dir_for(cwd, root)
        candidates = list(proj.glob("*.jsonl")) if proj else []
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)


def latest_session(cwd: Path | None = None) -> Path | None:
    s = find_sessions(cwd)
    return s[0] if s else None
