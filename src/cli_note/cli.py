"""Command-line interface for cli-note."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

from . import __version__
from .search import BM25Index, highlight
from .store import DuplicateNote, NoteNotFound, Vault, VaultError, resolve_vault


def _vault(args: argparse.Namespace, create: bool = True) -> Vault:
    return Vault(resolve_vault(args.vault), create=create)


def _split_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [t.strip().lstrip("#") for t in raw.replace("，", ",").split(",") if t.strip()]


def _open_editor(initial: str = "") -> str:
    editor = os.environ.get("EDITOR") or ("notepad" if sys.platform == "win32" else "vi")
    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(initial)
        path = f.name
    try:
        subprocess.call([editor, path])
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    finally:
        os.unlink(path)


# ---------------------------------------------------------------- commands


def cmd_init(args: argparse.Namespace) -> int:
    root = resolve_vault(args.vault)
    root.mkdir(parents=True, exist_ok=True)
    print(f"Vault ready at {root}")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    vault = _vault(args)
    content = args.content
    if content is None and not args.no_editor and not sys.stdin.isatty():
        content = sys.stdin.read().strip()
    if content is None and not args.no_editor:
        content = _open_editor(f"# {args.title}\n\n")
    note = vault.create(args.title, content or "", _split_tags(args.tags))
    print(f"Created [{note.id}] {note.title}" + (f"  tags: {', '.join(note.tags)}" if note.tags else ""))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    notes = _vault(args).list(tag=args.tag)
    if not notes:
        print("No notes." + (f" (tag: {args.tag})" if args.tag else ""))
        return 0
    width = max((len(n.id) for n in notes), default=0)
    for n in notes:
        tags = f"  #{' #'.join(n.all_tags)}" if n.all_tags else ""
        print(f"{n.id:<{width}}  {n.title}{tags}  ({n.modified[:10]})")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    vault = _vault(args)
    note = vault.get(args.note)
    if args.path_only:
        print(note.path)
        return 0
    tags = f"  #{' #'.join(note.all_tags)}" if note.all_tags else ""
    print(f"# {note.title}{tags}\n")
    print(note.content)
    backs = vault.backlinks(args.note)
    if backs:
        print("\n---\nLinked from: " + ", ".join(b.id for b in backs))
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    vault = _vault(args)
    note = vault.get(args.note)
    content = args.content
    if content is None:
        content = _open_editor(note.content + "\n")
    tags = _split_tags(args.tags) if args.tags is not None else None
    updated = vault.update(args.note, title=args.title, content=content, tags=tags)
    print(f"Updated [{updated.id}] {updated.title}")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    vault = _vault(args)
    note = vault.get(args.note)
    if not args.yes:
        answer = input(f"Delete [{note.id}] {note.title}? [y/N] ")
        if answer.lower() not in ("y", "yes"):
            print("Aborted.")
            return 1
    vault.delete(args.note)
    print(f"Deleted [{note.id}]")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    vault = _vault(args)
    notes = vault.list(tag=args.tag)
    results = BM25Index(notes).search(args.query, limit=args.limit)
    if not results:
        print(f"No results for {args.query!r}.")
        return 0
    for note, score in results:
        print(f"{score:6.2f}  {note.id:<20}  {note.title}")
        if args.verbose:
            print(f"         {highlight(note.content, args.query)}")
    return 0


def cmd_tags(args: argparse.Namespace) -> int:
    counts = _vault(args).tags()
    if not counts:
        print("No tags.")
        return 0
    for tag, count in counts.items():
        print(f"#{tag:<20} {count}")
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    from .tui import run_tui

    run_tui(resolve_vault(args.vault))
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    from .mcp_server import run_server

    run_server(resolve_vault(args.vault))
    return 0


# ------------------------------------------------------------------ parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cli-note",
        description="Local Markdown notes with tags, BM25 search, TUI and a built-in MCP server.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--vault", help="vault directory (default: $CLI_NOTE_VAULT or ~/.cli-note/vault)")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="create the vault directory")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("new", help="create a note")
    sp.add_argument("title")
    sp.add_argument("-t", "--tags", help="comma-separated tags")
    sp.add_argument("-c", "--content", help="inline Markdown body")
    sp.add_argument("--no-editor", action="store_true", help="never open $EDITOR")
    sp.set_defaults(func=cmd_new)

    sp = sub.add_parser("list", aliases=["ls"], help="list notes")
    sp.add_argument("-t", "--tag", help="filter by tag")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("show", help="print a note")
    sp.add_argument("note")
    sp.add_argument("--path", dest="path_only", action="store_true", help="print file path only")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("edit", help="edit a note ($EDITOR or -c)")
    sp.add_argument("note")
    sp.add_argument("--title", help="rename")
    sp.add_argument("-t", "--tags", help="replace tags (comma-separated)")
    sp.add_argument("-c", "--content", help="replace body inline")
    sp.set_defaults(func=cmd_edit)

    sp = sub.add_parser("delete", aliases=["rm"], help="delete a note")
    sp.add_argument("note")
    sp.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    sp.set_defaults(func=cmd_delete)

    sp = sub.add_parser("search", aliases=["s"], help="BM25 full-text search")
    sp.add_argument("query")
    sp.add_argument("-n", "--limit", type=int, default=10)
    sp.add_argument("-t", "--tag", help="restrict to a tag")
    sp.add_argument("-v", "--verbose", action="store_true", help="show snippets")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("tags", help="list tags with note counts")
    sp.set_defaults(func=cmd_tags)

    sp = sub.add_parser("tui", help="interactive terminal UI")
    sp.set_defaults(func=cmd_tui)

    sp = sub.add_parser("mcp", help="run the MCP server over stdio")
    sp.set_defaults(func=cmd_mcp)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (NoteNotFound, DuplicateNote, VaultError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
