"""Round-trip and CRUD tests for the Obsidian-compatible vault."""

import pytest

from cli_note.models import parse_note, serialize
from cli_note.store import DuplicateNote, NoteNotFound, Vault


@pytest.fixture()
def vault(tmp_path):
    return Vault(tmp_path)


# ------------------------------------------------------------- frontmatter


def test_frontmatter_round_trip():
    from cli_note.models import Note

    note = Note(id="x", title="Hello: World", content="body **text**",
                tags=["a", "b c"], created="2026-01-01T00:00:00+00:00",
                modified="2026-01-02T00:00:00+00:00")
    parsed = parse_note("x", serialize(note))
    assert parsed.title == "Hello: World"
    assert parsed.tags == ["a", "b c"]
    assert parsed.content == "body **text**"
    assert parsed.created.startswith("2026-01-01")


def test_parse_list_style_tags():
    raw = "---\ntitle: T\ntags:\n  - alpha\n  - beta\n---\nbody"
    note = parse_note("t", raw)
    assert note.tags == ["alpha", "beta"]
    assert note.content == "body"


def test_parse_plain_markdown_without_frontmatter():
    note = parse_note("raw", "# Just markdown\n")
    assert note.title == "raw"
    assert "Just markdown" in note.content


# -------------------------------------------------------------------- CRUD


def test_create_and_get(vault):
    vault.create("My First Note", "hello world", ["intro"])
    note = vault.get("My First Note")  # by title
    assert note.id == "My-First-Note"
    assert note.tags == ["intro"]
    assert (vault.root / "My-First-Note.md").exists()


def test_duplicate_create_raises(vault):
    vault.create("dup")
    with pytest.raises(DuplicateNote):
        vault.create("dup")


def test_missing_note_raises(vault):
    with pytest.raises(NoteNotFound):
        vault.get("nope")


def test_update_rename_moves_file(vault):
    vault.create("old name", "x")
    note = vault.update("old name", title="new name", content="y", tags=["t2"])
    assert note.id == "new-name"
    assert note.content == "y"
    assert not (vault.root / "old-name.md").exists()
    assert (vault.root / "new-name.md").exists()


def test_delete(vault):
    vault.create("gone")
    vault.delete("gone")
    assert vault.list() == []


def test_tags_and_inline_tags(vault):
    vault.create("a", "mentions #inline tag", ["x"])
    vault.create("b", "", ["x", "y"])
    counts = vault.tags()
    assert counts == {"x": 2, "inline": 1, "y": 1}
    assert [n.id for n in vault.list(tag="y")] == ["b"]


def test_wikilinks_and_backlinks(vault):
    vault.create("target", "nothing")
    vault.create("source", "see [[target]] and [[target|alias]]")
    source = vault.get("source")
    assert source.links == ["target", "target"]
    assert [n.id for n in vault.backlinks("target")] == ["source"]


def test_cjk_slug_preserved(vault):
    note = vault.create("中文标题 笔记")
    assert note.id == "中文标题-笔记"
    assert (vault.root / "中文标题-笔记.md").exists()
