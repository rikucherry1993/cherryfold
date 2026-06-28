"""cherryfold TUI — render a Claude Code session as vertical collapsible blocks
plus a left outline, for reading back (or live-following) long agent output.

Pain points addressed:
  1. Walls of output -> every segment is a collapsible block (text expanded,
     thinking / tool calls collapsed by default).
  2. Losing the original steps after the chat branches -> the left outline lists
     each human input (step); click to jump back; events hang under each step.

Extras: '/' search, 'y' copy (focused command/code, or the current selection),
native mouse drag-select for arbitrary text, and --follow incremental tailing.
"""
from __future__ import annotations

import re

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Collapsible, Footer, Header, Input, Markdown, OptionList, Static, Tree,
)
from rich.text import Text

from . import config
from .parser import Session, Step, Event

# Glyphs are configurable; populated from user config when the app starts.
ICONS = dict(config.DEFAULTS["icons"])
_FENCE = re.compile(r"```(?P<lang>\w*)\n(?P<code>.*?)```", re.DOTALL)
_TOOL_LANG = {"Bash": "bash"}


class CopyButton(Static):
    """A small clickable label that copies a fixed payload to the clipboard."""

    def __init__(self, payload: str) -> None:
        super().__init__(f"{ICONS['copy']} copy", classes="cb-copy")
        self._payload = payload

    def on_click(self, event) -> None:
        event.stop()
        self.app.copy_to_clipboard(self._payload)
        self.app.notify(f"Copied {len(self._payload)} chars")


class CodeBlock(Vertical):
    """A code/command block with its own copy button."""

    def __init__(self, code: str, lang: str = "") -> None:
        super().__init__(classes="codeblock")
        self.code = code
        self.lang = lang

    def compose(self) -> ComposeResult:
        with Horizontal(classes="cb-bar"):
            yield Static(self.lang or "code", classes="cb-lang")
            yield CopyButton(self.code)
        yield Static(self.code, classes="cb-code", markup=False)


def render_body(body: str):
    """Split prose from ``` fenced code; prose -> Markdown, code -> CodeBlock."""
    out, pos = [], 0
    for m in _FENCE.finditer(body or ""):
        pre = body[pos:m.start()]
        if pre.strip():
            out.append(Markdown(pre))
        out.append(CodeBlock(m.group("code").rstrip(), m.group("lang")))
        pos = m.end()
    tail = (body or "")[pos:]
    if tail.strip() or not out:
        out.append(Markdown(tail if (tail.strip() or not body) else (body or "")))
    return out


def build_event(step_index: int, j: int, ev: Event) -> Collapsible:
    """A collapsible block for one event (text expanded, others collapsed)."""
    classes = ev.kind + (" sidechain" if ev.sidechain else "")
    if ev.kind in ("text", "thinking"):
        children = render_body(ev.body)
    else:  # tool: copyable command, then the result
        children = [CodeBlock(ev.command or "(no command)",
                              _TOOL_LANG.get(ev.tool_name, ""))]
        if ev.result:
            children.append(Static(ev.result, classes="toolbody", markup=False))
    title = f"{ICONS.get(ev.kind, '·')} {ev.title}"
    coll = Collapsible(
        *children, title=title, collapsed=(ev.kind != "text"),
        id=f"ev-{step_index}-{j}", classes=classes,
    )
    coll.ev = ev  # attached for 'y' copy fallback
    return coll


def event_leaf_label(ev: Event) -> Text:
    icon = ICONS.get(ev.kind, "·")
    tag = "  sub " if ev.sidechain else ""
    return Text(f"{icon}{tag} {ev.title[:34]}")


def copy_payload(ev: Event) -> str:
    """What to copy for an event: tool command, else first code fence, else body."""
    if ev.kind == "tool" and ev.command:
        return ev.command
    m = _FENCE.search(ev.body or "")
    return m.group(1).rstrip() if m else (ev.body or "")


class StepCard(Vertical):
    """One step: human-input header plus its collapsible events."""

    def __init__(self, step: Step) -> None:
        super().__init__(id=f"step-{step.index}", classes="stepcard")
        self.step = step

    def compose(self) -> ComposeResult:
        st = self.step
        yield Static(f"▌ #{st.index}  {st.outline_label}", classes="stephead",
                     markup=False)
        if st.raw_prompt.strip():
            yield Collapsible(Markdown(st.raw_prompt),
                              title=f"{ICONS['prompt']} your input",
                              collapsed=True, classes="prompt")
        for j, ev in enumerate(st.events):
            yield build_event(st.index, j, ev)

    def append_event(self, j: int, ev: Event) -> None:
        self.mount(build_event(self.step.index, j, ev))


class AgentView(App):
    CSS = """
    Screen { layers: base; }
    #outline {
        width: 38; min-width: 24; border-right: solid $accent;
        background: $panel;
    }
    #outline > Tree { padding: 0 1; }
    #content { padding: 0 1; }
    .stepcard { height: auto; margin: 1 0 0 0; border-top: heavy $accent; }
    .stephead { text-style: bold; color: $accent; padding: 0 1; background: $boost; }
    Collapsible { margin: 0 0 0 1; border: none; }
    Collapsible.thinking > CollapsibleTitle { color: $text-muted; text-style: italic; }
    Collapsible.tool > CollapsibleTitle { color: $warning; }
    Collapsible.text > CollapsibleTitle { color: $success; }
    Collapsible.sidechain { margin-left: 4; border-left: solid $primary; }
    .match { background: $warning 30%; }
    .toolbody { color: $text-muted; }
    .codeblock { height: auto; margin: 0 1 1 1; border: round $surface-lighten-2; }
    .cb-bar { height: 1; background: $surface; }
    .cb-lang { width: 1fr; color: $text-muted; padding: 0 1; }
    .cb-copy { width: auto; padding: 0 1; color: $accent; }
    .cb-copy:hover { background: $accent; color: $background; }
    .cb-code { padding: 0 1; color: $text; }
    #search { dock: bottom; border: tall $accent; }
    .compact .stepcard { margin: 0; border-top: solid $accent; }
    .compact Collapsible { margin: 0; }
    .compact .codeblock { margin: 0 1; }
    SettingsScreen { align: center middle; }
    #settings {
        width: 62; height: auto; max-height: 90%; padding: 1 2;
        background: $panel; border: thick $accent;
    }
    .settings-title { text-style: bold; color: $accent; }
    .settings-hint { color: $text-muted; }
    #theme-list { height: 14; border: solid $surface-lighten-2; margin: 1 0; }
    """

    BINDINGS = [
        Binding("slash", "search", "search"),
        Binding("n", "next_match", "next", show=False),
        Binding("N", "prev_match", "prev", show=False),
        Binding("y", "copy", "copy"),
        Binding("c", "collapse_all", "fold"),
        Binding("e", "expand_all", "unfold"),
        Binding("t", "toggle_thinking", "thinking"),
        Binding("f", "toggle_tail", "tail"),
        Binding("s", "open_settings", "settings"),
        Binding("g", "go_top", "top"),
        Binding("G", "go_bottom", "bottom"),
        Binding("escape", "close_search", "", show=False),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, session: Session, follow: bool = False,
                 cfg: dict | None = None) -> None:
        super().__init__()
        self.cfg = cfg or config.load()
        ICONS.update(self.cfg.get("icons", {}))   # apply configured glyphs
        self.session = session
        self.follow = follow
        self.follow_tail = follow
        self._thinking_hidden = False
        self._cards: dict[int, StepCard] = {}
        self._tree_nodes: dict[int, object] = {}
        self._rendered: dict[int, int] = {}
        self._mtime = 0.0
        self._matches: list[str] = []
        self._match_idx = -1

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="outline"):
                yield Tree("outline", id="tree")
            with VerticalScroll(id="content"):
                for step in self.session.steps:
                    yield StepCard(step)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "cherryfold"
        self.apply_theme(self.cfg.get("theme", "textual-dark"))
        if self.cfg.get("density") == "compact":
            self.query_one("#content").add_class("compact")
        tree = self.query_one("#tree", Tree)
        tree.root.expand()
        for card in self.query(StepCard):
            self._cards[card.step.index] = card
        for step in self.session.steps:
            self._add_outline_node(tree, step)
            self._rendered[step.index] = len(step.events)
        tree.focus()
        self._update_subtitle()
        if self.follow and self.session.path:
            try:
                self._mtime = self.session.path.stat().st_mtime
            except OSError:
                self._mtime = 0.0
            self.set_interval(float(self.cfg.get("follow_interval", 1.5)), self._poll)

    def _add_outline_node(self, tree: Tree, step: Step):
        node = tree.root.add(
            Text(f"#{step.index} {step.outline_label}"),
            data=("step", step.index, 0),
        )
        for j, ev in enumerate(step.events):
            node.add_leaf(event_leaf_label(ev), data=("ev", step.index, j))
        self._tree_nodes[step.index] = node
        return node

    def _update_subtitle(self) -> None:
        n = len(self.session.steps)
        suffix = " · following" if self.follow else ""
        self.sub_title = f"{self.session.title} · {n} steps{suffix}"

    # ---- follow: poll the log for new content ----
    def _poll(self) -> None:
        path = self.session.path
        try:
            m = path.stat().st_mtime
        except OSError:
            return
        if m == self._mtime:
            return
        self._mtime = m
        try:
            from .parser import load_session
            new = load_session(path)
        except Exception:
            return
        self._sync(new)

    def _sync(self, new: Session) -> None:
        content = self.query_one("#content", VerticalScroll)
        tree = self.query_one("#tree", Tree)
        added = False
        for step in new.steps:
            if step.index not in self._cards:
                card = StepCard(step)
                content.mount(card)
                self._cards[step.index] = card
                self._add_outline_node(tree, step)
                self._rendered[step.index] = len(step.events)
                added = True
            else:
                old = self._rendered.get(step.index, 0)
                if len(step.events) > old:
                    card = self._cards[step.index]
                    node = self._tree_nodes[step.index]
                    for j in range(old, len(step.events)):
                        ev = step.events[j]
                        card.append_event(j, ev)
                        node.add_leaf(event_leaf_label(ev), data=("ev", step.index, j))
                    self._rendered[step.index] = len(step.events)
                    added = True
        self.session = new
        self._update_subtitle()
        if added and self.follow_tail:
            content.scroll_end(animate=False)

    # ---- outline jump ----
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not data:
            return
        kind, sidx, j = data
        target_id = f"#step-{sidx}" if kind == "step" else f"#ev-{sidx}-{j}"
        try:
            w = self.query_one(target_id)
        except Exception:
            return
        if kind == "ev":
            self.query_one(target_id, Collapsible).collapsed = False
        self.follow_tail = False
        w.scroll_visible(top=True, animate=True)

    # ---- search ----
    def action_search(self) -> None:
        if self.query("#search"):
            self.query_one("#search", Input).focus()
            return
        inp = Input(placeholder="search… (Enter jump, n/N cycle, Esc close)", id="search")
        self.mount(inp)
        inp.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "search":
            return
        self._run_search(event.value.strip())
        # move focus off the input so n/N cycle matches (Esc still closes search)
        self.query_one("#tree", Tree).focus()

    def _run_search(self, query: str) -> None:
        self._clear_highlight()
        self._matches = []
        if not query:
            return
        q = query.lower()
        for step in self.session.steps:
            if q in step.prompt.lower():
                self._matches.append(f"step-{step.index}")
            for j, ev in enumerate(step.events):
                if (q in ev.title.lower() or q in ev.body.lower()
                        or q in ev.result.lower()):
                    self._matches.append(f"ev-{step.index}-{j}")
        if not self._matches:
            self.notify(f"No match for {query!r}", severity="warning")
            return
        self._match_idx = -1
        self.notify(f"{len(self._matches)} matches")
        self.action_next_match()

    def _goto_match(self) -> None:
        if not self._matches:
            return
        self._clear_highlight()
        wid = self._matches[self._match_idx]
        try:
            w = self.query_one(f"#{wid}")
        except Exception:
            return
        if isinstance(w, Collapsible):
            w.collapsed = False
        w.add_class("match")
        self.follow_tail = False
        w.scroll_visible(top=True, animate=True)
        self.sub_title = f"match {self._match_idx + 1}/{len(self._matches)}"

    def _clear_highlight(self) -> None:
        for w in self.query(".match"):
            w.remove_class("match")

    def action_next_match(self) -> None:
        if not self._matches:
            return
        self._match_idx = (self._match_idx + 1) % len(self._matches)
        self._goto_match()

    def action_prev_match(self) -> None:
        if not self._matches:
            return
        self._match_idx = (self._match_idx - 1) % len(self._matches)
        self._goto_match()

    def action_close_search(self) -> None:
        for inp in self.query("#search"):
            inp.remove()
        self._clear_highlight()
        self.query_one("#tree", Tree).focus()

    # ---- copy ----
    def action_copy(self) -> None:
        sel = self.screen.get_selected_text() if self.screen else None
        if sel:
            self.copy_to_clipboard(sel)
            self.notify(f"Copied selection ({len(sel)} chars)")
            return
        coll = None
        if self.focused is not None:
            for w in self.focused.ancestors_with_self:
                if isinstance(w, Collapsible):
                    coll = w
                    break
        ev = getattr(coll, "ev", None) if coll else None
        if ev is None:
            self.notify("Focus a block (or drag-select text) first", severity="warning")
            return
        text = copy_payload(ev)
        self.copy_to_clipboard(text)
        label = "command" if ev.kind == "tool" else "text"
        self.notify(f"Copied {label} ({len(text)} chars)")

    # ---- fold ops ----
    def action_collapse_all(self) -> None:
        for c in self.query(Collapsible):
            c.collapsed = True

    def action_expand_all(self) -> None:
        for c in self.query(Collapsible):
            c.collapsed = False

    def action_toggle_thinking(self) -> None:
        self._thinking_hidden = not self._thinking_hidden
        for c in self.query("Collapsible.thinking"):
            c.display = not self._thinking_hidden

    def action_toggle_tail(self) -> None:
        self.follow_tail = not self.follow_tail
        if self.follow_tail:
            self.query_one("#content", VerticalScroll).scroll_end(animate=False)

    # ---- settings ----
    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def apply_theme(self, name: str) -> None:
        try:
            self.theme = name
        except Exception:
            self.theme = "textual-dark"
            name = "textual-dark"
        self.cfg["theme"] = self.theme
        config.save(self.cfg)

    def set_density(self, value: str) -> None:
        self.cfg["density"] = value
        content = self.query_one("#content")
        content.set_class(value == "compact", "compact")
        config.save(self.cfg)

    def action_go_top(self) -> None:
        self.follow_tail = False
        self.query_one("#content", VerticalScroll).scroll_home(animate=False)

    def action_go_bottom(self) -> None:
        self.query_one("#content", VerticalScroll).scroll_end(animate=False)


class SettingsScreen(ModalScreen):
    """Theme picker + density toggle. Icons are edited in the config file."""

    BINDINGS = [
        Binding("escape", "close", "close"),
        Binding("d", "toggle_density", "density"),
    ]

    def compose(self) -> ComposeResult:
        self._themes = sorted(self.app.available_themes.keys())
        with Vertical(id="settings"):
            yield Static("⚙  Settings", classes="settings-title")
            yield Static("Theme — ↑/↓ then Enter to apply:", classes="settings-hint")
            yield OptionList(*self._themes, id="theme-list")
            yield Static(self._density_line(), id="density-line")
            yield Static("Glyphs: edit ~/.config/cherryfold/config.json",
                         classes="settings-hint")
            yield Static("[d] toggle density   [Esc] close", classes="settings-hint")

    def on_mount(self) -> None:
        ol = self.query_one("#theme-list", OptionList)
        cur = self.app.theme
        if cur in self._themes:
            ol.highlighted = self._themes.index(cur)
        ol.focus()

    def _density_line(self) -> str:
        return f"Density: {self.app.cfg.get('density', 'comfortable')}"

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        name = self._themes[event.option_index]
        self.app.apply_theme(name)
        self.app.notify(f"Theme: {name}")

    def action_toggle_density(self) -> None:
        cur = self.app.cfg.get("density", "comfortable")
        self.app.set_density("comfortable" if cur == "compact" else "compact")
        self.query_one("#density-line", Static).update(self._density_line())

    def action_close(self) -> None:
        self.dismiss()
