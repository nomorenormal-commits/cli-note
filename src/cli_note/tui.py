"""Interactive Textual TUI for cli-note.

Layout: search bar on top, note list on the left, Markdown preview on the
right, tag bar at the bottom. Keys: n new, e edit, d delete, t tag filter,
r refresh, / focus search, q quit.
"""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Markdown, Static

from .search import BM25Index
from .store import Vault


class NoteApp(App):
    CSS = """
    #search { dock: top; margin: 0 1; }
    #main { height: 1fr; }
    #sidebar { width: 34; border-right: solid $primary; }
    #note-list { height: 1fr; }
    #preview { width: 1fr; padding: 0 2; }
    #tagbar { dock: bottom; height: 1; padding: 0 1; background: $surface; }
    #status { dock: bottom; height: 1; padding: 0 1; color: $text-muted; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("n", "new_note", "New"),
        Binding("e", "edit_note", "Edit"),
        Binding("d", "delete_note", "Delete"),
        Binding("t", "filter_tag", "Tag"),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "focus_search", "Search"),
        Binding("escape", "clear_search", "Clear"),
    ]

    def __init__(self, vault_root: Path):
        super().__init__()
        self.vault = Vault(vault_root)
        self.tag_filter: str | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Input(placeholder="Search (BM25)…  / to focus, Esc to clear", id="search")
        with Horizontal(id="main"):
            with Vertical(id="sidebar"):
                yield ListView(id="note-list")
            yield Markdown("", id="preview")
        yield Static("", id="tagbar")
        yield Static("", id="status")
        yield Footer()

    async def on_mount(self) -> None:
        self.title = "cli-note"
        self.sub_title = str(self.vault.root)
        await self.reload()

    # ------------------------------------------------------------- helpers

    def _note_ids(self) -> list[str]:
        lst = self.query_one("#note-list", ListView)
        return [item.id or "" for item in lst.children]

    async def reload(self, select: str | None = None) -> None:
        query = self.query_one("#search", Input).value
        notes = self.vault.list(tag=self.tag_filter)
        if query.strip():
            notes = [n for n, _ in BM25Index(notes).search(query, limit=100)]
        lst = self.query_one("#note-list", ListView)
        await lst.clear()
        items = []
        for note in notes:
            label = note.title
            if note.all_tags:
                label += "  [dim]#" + " #".join(note.all_tags) + "[/dim]"
            items.append(ListItem(Label(label), id=note.id))
        if items:
            await lst.extend(items)
        tags = self.vault.tags()
        bar = "  ".join(f"#{t}({c})" for t, c in list(tags.items())[:8])
        if self.tag_filter:
            bar = f"[bold]#{self.tag_filter}[/bold] (t to clear)  |  " + bar
        self.query_one("#tagbar", Static).update(bar or "no tags yet — press n to create a note")
        self.query_one("#status", Static).update(f"{len(notes)} note(s)")
        if notes:
            ids = self._note_ids()
            target = select if select in ids else notes[0].id
            lst.index = ids.index(target)
            self._show(target)
        else:
            self.query_one("#preview", Markdown).update("")

    def _show(self, note_id: str) -> None:
        try:
            note = self.vault.get(note_id)
        except Exception:
            return
        header = f"# {note.title}\n\n`{note.id}` · {note.modified[:19]}"
        if note.all_tags:
            header += " · " + " ".join(f"#{t}" for t in note.all_tags)
        self.query_one("#preview", Markdown).update(f"{header}\n\n---\n\n{note.content}")

    def _selected_id(self) -> str | None:
        lst = self.query_one("#note-list", ListView)
        if lst.highlighted_child is not None:
            return lst.highlighted_child.id
        return None

    # -------------------------------------------------------------- events

    @on(ListView.Highlighted, "#note-list")
    def preview_highlight(self, event: ListView.Highlighted) -> None:
        if event.item and event.item.id:
            self._show(event.item.id)

    @on(Input.Changed, "#search")
    async def live_search(self, _: Input.Changed) -> None:
        await self.reload()

    # -------------------------------------------------------------- actions

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    async def action_clear_search(self) -> None:
        inp = self.query_one("#search", Input)
        if inp.value:
            inp.value = ""
        elif self.tag_filter:
            self.tag_filter = None
            await self.reload()

    async def action_refresh(self) -> None:
        self.vault = Vault(self.vault.root)
        await self.reload()

    async def action_filter_tag(self) -> None:
        if self.tag_filter:
            self.tag_filter = None
        else:
            tags = list(self.vault.tags())
            if tags:
                self.tag_filter = tags[0]  # most-used tag; repeat to clear
        await self.reload()

    def action_new_note(self) -> None:
        self.push_screen(NewNoteScreen(), self._on_new_note)

    async def _on_new_note(self, result: tuple[str, list[str]] | None) -> None:
        if not result:
            return
        title, tags = result
        try:
            note = self.vault.create(title, "", tags)
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        await self.reload(select=note.id)
        self.notify(f"created {note.id} — press e to edit")

    async def action_edit_note(self) -> None:
        note_id = self._selected_id()
        if not note_id:
            return
        try:
            note = self.vault.get(note_id)
            content = self._external_edit(note.content + "\n")
            self.vault.update(note_id, content=content)
            self.vault = Vault(self.vault.root)
            await self.reload(select=note_id)
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def _external_edit(self, initial: str) -> str:
        import os
        import subprocess
        import sys
        import tempfile

        editor = os.environ.get("EDITOR") or ("notepad" if sys.platform == "win32" else "vi")
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(initial)
            path = f.name
        with self.suspend():
            subprocess.call([editor, path])
        with open(path, encoding="utf-8") as f:
            content = f.read().strip()
        os.unlink(path)
        return content

    async def action_delete_note(self) -> None:
        note_id = self._selected_id()
        if not note_id:
            return
        try:
            self.vault.delete(note_id)
            await self.reload()
            self.notify(f"deleted {note_id}")
        except Exception as exc:
            self.notify(str(exc), severity="error")


class NewNoteScreen(Screen):
    """Modal screen: title + tags input; dismisses with (title, tags) or None."""

    CSS = """
    NewNoteScreen { align: center middle; }
    #box { width: 60; height: auto; border: solid $primary; padding: 1 2; background: $surface; }
    #box Input { margin-bottom: 1; }
    """

    def compose(self) -> ComposeResult:
        with Container(id="box"):
            yield Label("New note — Enter in Tags to save, Esc to cancel")
            yield Input(placeholder="Title", id="title")
            yield Input(placeholder="Tags (comma separated)", id="tags")

    def on_mount(self) -> None:
        self.query_one("#title", Input).focus()

    @on(Input.Submitted, "#title")
    def to_tags(self) -> None:
        self.query_one("#tags", Input).focus()

    @on(Input.Submitted, "#tags")
    def save(self) -> None:
        title = self.query_one("#title", Input).value.strip()
        tags = [t.strip().lstrip("#") for t in self.query_one("#tags", Input).value.split(",") if t.strip()]
        self.dismiss((title, tags) if title else None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


def run_tui(vault_root: Path) -> None:
    NoteApp(vault_root).run()
