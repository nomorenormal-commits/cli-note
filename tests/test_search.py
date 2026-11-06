"""BM25 tokenizer and ranking tests."""

from cli_note.models import Note
from cli_note.search import BM25Index, highlight, tokenize


def _note(id_, title, content, tags=None):
    return Note(id=id_, title=title, content=content, tags=tags or [])


def test_tokenize_latin():
    assert tokenize("Hello, BM25_Search!") == ["hello", "bm25_search"]


def test_tokenize_cjk_unigram_and_bigram():
    tokens = tokenize("笔记")
    assert "笔" in tokens and "记" in tokens and "笔记" in tokens
    single = tokenize("好")
    assert single == ["好"]


def test_ranking_prefers_relevant_note():
    notes = [
        _note("a", "Python packaging", "how to build wheels and publish"),
        _note("b", "Pasta recipes", "boil water, add salt"),
        _note("c", "Python testing", "pytest fixtures for python projects"),
    ]
    results = BM25Index(notes).search("python")
    assert [n.id for n, _ in results][0] in {"a", "c"}
    assert all(n.id != "b" for n, _ in results)


def test_title_boost_beats_body_mention():
    notes = [
        _note("a", "random thoughts", "mentions obsidian once"),
        _note("b", "obsidian setup", "my editor config"),
    ]
    results = BM25Index(notes).search("obsidian")
    assert results[0][0].id == "b"


def test_cjk_search():
    notes = [
        _note("a", "机器学习笔记", "梯度下降与反向传播"),
        _note("b", "购物清单", "牛奶和鸡蛋"),
    ]
    results = BM25Index(notes).search("反向传播")
    assert results and results[0][0].id == "a"


def test_tag_boost():
    notes = [
        _note("a", "untitled thoughts", "nothing about it", tags=["python"]),
        _note("b", "other", "python python python"),
    ]
    results = BM25Index(notes).search("python")
    ids = [n.id for n, _ in results]
    assert set(ids) == {"a", "b"}


def test_empty_query_returns_nothing():
    notes = [_note("a", "t", "c")]
    assert BM25Index(notes).search("") == []


def test_highlight_snippet():
    text = "alpha " * 50 + "needle " + "omega " * 50
    out = highlight(text, "needle", 60)
    assert "needle" in out
    assert len(out) <= 62
