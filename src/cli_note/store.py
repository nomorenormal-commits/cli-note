"""Vault: a directory of Obsidian-compatible Markdown notes."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .models import Note, parse_note, serialize, slugify, utcnow_iso

DEFAULT_VAULT = Path.home() / ".cli-note" / "vault"


class VaultError(Exception):
    pass


class NoteNotFound(VaultError):
    pass


class DuplicateNote(VaultError):
    pass


def resolve_vault(path: str | None = None) -> Path:
    """Vault resolution order: explicit arg > $CLI_NOTE_VAULT > default."""
    p = path or os.environ.get("CLI_NOTE_VAULT")
    return Path(p).expanduser().resolve() if p else DEFAULT_VAULT


class Vault:
    def __init__(self, root: str | Path | None = None, create: bool = True):
        self.root = Path(root) if root else resolve_vault()
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
        elif not self.root.is_dir():
            raise VaultError(f"vault not found: {self.root}")

    # ------------------------------------------------------------------ I/O

    def _path_for(self, note_id: str) -> Path:
        # Guard against path traversal; ids are filename stems only.
        safe = re.sub(r"[\\/:*?\"<>|]", "", note_id).strip()
        if not safe or safe.startswith("."):
            raise VaultError(f"invalid note id: {note_id!r}")
        return self.root / f"{safe}.md"

    def _scan(self) -> list[Path]:
        return sorted(
            p for p in self.root.rglob("*.md")
            if p.is_file()
            and not any(part.startswith(".") for part in p.relative_to(self.root).parts)
        )

    def _load_path(self, path: Path) -> Note:
        note = parse_note(path.stem, path.read_text(encoding="utf-8"), str(path))
        if not note.created:
            note.created = utcnow_iso()
        if not note.modified:
            note.modified = note.created
        return note

    # ----------------------------------------------------------------- CRUD

    def list(self, tag: str | None = None) -> list[Note]:
        notes = [self._load_path(p) for p in self._scan()]
        if tag:
            notes = [n for n in notes if tag in n.all_tags]
        return sorted(notes, key=lambda n: n.modified, reverse=True)

    def get(self, query: str) -> Note:
        """Fetch by exact id, then by case-insensitive title, then unique prefix."""
        path = self._path_for(query)
        if path.exists():
            return self._load_path(path)
        notes = self.list()
        lowered = query.lower()
        for n in notes:
            if n.title.lower() == lowered:
                return n
        matches = [n for n in notes if n.id.lower().startswith(lowered)]
        if len(matches) == 1:
            return matches[0]
        raise NoteNotFound(f"note not found: {query}")

    def create(self, title: str, content: str = "", tags: list[str] | None = None) -> Note:
        note_id = slugify(title)
        path = self._path_for(note_id)
        if path.exists():
            raise DuplicateNote(f"note already exists: {note_id}")
        now = utcnow_iso()
        note = Note(id=note_id, title=title, content=content,
                    tags=list(tags or []), created=now, modified=now, path=str(path))
        path.write_text(serialize(note), encoding="utf-8")
        return note

    def update(self, query: str, *, title: str | None = None,
               content: str | None = None, tags: list[str] | None = None) -> Note:
        note = self.get(query)
        if title is not None and title != note.title:
            new_id = slugify(title)
            new_path = self._path_for(new_id)
            if new_path != Path(note.path) and new_path.exists():
                raise DuplicateNote(f"note already exists: {new_id}")
            Path(note.path).unlink()
            note.id, note.title, note.path = new_id, title, str(new_path)
        if content is not None:
            note.content = content
        if tags is not None:
            note.tags = list(tags)
        note.modified = utcnow_iso()
        Path(note.path).write_text(serialize(note), encoding="utf-8")
        return note

    def delete(self, query: str) -> Note:
        note = self.get(query)
        Path(note.path).unlink()
        return note

    # ----------------------------------------------------------------- tags

    def tags(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for note in self.list():
            for t in note.all_tags:
                counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    # -------------------------------------------------------------- links

    def backlinks(self, query: str) -> list[Note]:
        target = self.get(query)
        names = {target.id.lower(), target.title.lower()}
        return [n for n in self.list()
                if n.id != target.id and any(l.lower() in names for l in n.links)]
