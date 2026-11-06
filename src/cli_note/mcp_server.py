"""Built-in MCP server: expose the vault to any MCP client (DSH, Claude, …).

Runs over stdio. Register it with e.g.:

    claude mcp add cli-note -- cli-note mcp

or point any MCP client at `cli-note mcp` / `python -m cli_note.mcp_server`.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import __version__
from .models import serialize
from .search import BM25Index, highlight
from .store import DuplicateNote, NoteNotFound, Vault


def _note_brief(note) -> dict:
    return {
        "id": note.id,
        "title": note.title,
        "tags": note.all_tags,
        "created": note.created,
        "modified": note.modified,
        "summary": note.summary(120),
        "path": note.path,
    }


def build_server(vault_root: Path) -> FastMCP:
    vault = Vault(vault_root)
    mcp = FastMCP("cli-note", instructions=(
        "Read and manage the user's local Markdown note vault "
        f"({vault_root}). Notes are Obsidian-compatible .md files with YAML "
        "frontmatter; search uses BM25 ranked full-text matching."
    ))

    @mcp.tool()
    def list_notes(tag: str | None = None, limit: int = 50) -> str:
        """List notes in the vault, newest first. Optionally filter by tag."""
        notes = vault.list(tag=tag)[:limit]
        return json.dumps([_note_brief(n) for n in notes], ensure_ascii=False, indent=2)

    @mcp.tool()
    def read_note(note: str, raw: bool = False) -> str:
        """Read one note by id or title. raw=true returns the exact Markdown
        file (frontmatter included) as stored on disk."""
        n = vault.get(note)
        return serialize(n) if raw else json.dumps(
            {**_note_brief(n), "content": n.content, "links": n.links},
            ensure_ascii=False, indent=2,
        )

    @mcp.tool()
    def search_notes(query: str, limit: int = 10, tag: str | None = None) -> str:
        """BM25 full-text search over titles, tags and bodies. Returns ranked
        results with a score and a matched snippet."""
        notes = vault.list(tag=tag)
        hits = BM25Index(notes).search(query, limit=limit)
        return json.dumps(
            [
                {
                    "id": n.id,
                    "title": n.title,
                    "tags": n.all_tags,
                    "score": round(score, 3),
                    "snippet": highlight(n.content, query, 160),
                }
                for n, score in hits
            ],
            ensure_ascii=False,
            indent=2,
        )

    @mcp.tool()
    def create_note(title: str, content: str = "", tags: list[str] | None = None) -> str:
        """Create a new Markdown note. `tags` is a list like ["ideas", "ml"]."""
        try:
            n = vault.create(title, content, tags or [])
        except DuplicateNote as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps({"created": _note_brief(n)}, ensure_ascii=False)

    @mcp.tool()
    def update_note(
        note: str,
        content: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        append: bool = False,
    ) -> str:
        """Update a note by id/title. append=true appends content instead of
        replacing the body."""
        try:
            if append and content is not None:
                old = vault.get(note)
                content = (old.content.rstrip("\n") + "\n\n" + content).strip("\n")
            n = vault.update(note, title=title, content=content, tags=tags)
        except (NoteNotFound, DuplicateNote) as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps({"updated": _note_brief(n)}, ensure_ascii=False)

    @mcp.tool()
    def delete_note(note: str) -> str:
        """Delete a note by id or title."""
        try:
            n = vault.delete(note)
        except NoteNotFound as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps({"deleted": n.id})

    @mcp.tool()
    def list_tags() -> str:
        """List all tags with the number of notes using each."""
        return json.dumps(vault.tags(), ensure_ascii=False, indent=2)

    # ---------------------------------------------------------- resources

    @mcp.resource("notes://index")
    def index_resource() -> str:
        """Vault index: every note with metadata."""
        return json.dumps([_note_brief(n) for n in vault.list()], ensure_ascii=False, indent=2)

    @mcp.resource("note://{note_id}")
    def note_resource(note_id: str) -> str:
        """Raw Markdown for one note."""
        from urllib.parse import unquote

        return serialize(vault.get(unquote(note_id)))

    return mcp


def run_server(vault_root: Path) -> None:
    build_server(vault_root).run()  # stdio transport


def run_from_cli() -> None:
    """Entry point for the `cli-note-mcp` script: `cli-note-mcp [vault]`."""
    import sys

    root = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else None
    run_server(Vault(root).root)


if __name__ == "__main__":
    run_from_cli()
