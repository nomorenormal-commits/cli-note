"""Okapi BM25 full-text search with a mixed Latin/CJK tokenizer."""

from __future__ import annotations

import math
import re
from collections import Counter

from .models import Note

_LATIN_RE = re.compile(r"[a-z0-9_]+")
_CJK_RE = re.compile(r"[一-鿿㐀-䶿぀-ヿ가-힯]+")

# Field boosts: title matches matter most, then tags, then body.
BOOST_TITLE = 3.0
BOOST_TAG = 2.0
BOOST_BODY = 1.0


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens for Latin text, unigrams+bigrams for CJK runs."""
    text = text.lower()
    tokens = _LATIN_RE.findall(text)
    for run in _CJK_RE.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run)  # unigrams keep recall
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


class BM25Index:
    """In-memory BM25 index over a list of notes."""

    def __init__(self, notes: list[Note], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.notes = notes
        self.doc_tokens: list[list[str]] = []
        self.doc_len: list[int] = []
        self.tf: list[Counter[str]] = []
        df: Counter[str] = Counter()

        for note in notes:
            weighted: list[str] = []
            weighted += tokenize(note.title) * int(BOOST_TITLE)
            weighted += tokenize(" ".join(note.all_tags)) * int(BOOST_TAG)
            weighted += tokenize(note.content) * int(BOOST_BODY)
            self.doc_tokens.append(weighted)
            self.doc_len.append(len(weighted))
            counts = Counter(weighted)
            self.tf.append(counts)
            for term in counts:
                df[term] += 1

        n_docs = max(len(notes), 1)
        self.idf = {
            term: math.log(1 + (n_docs - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }
        self.avgdl = sum(self.doc_len) / n_docs if notes else 0.0

    def search(self, query: str, limit: int = 20) -> list[tuple[Note, float]]:
        terms = tokenize(query)
        if not terms:
            return []
        scores: list[tuple[int, float]] = []
        for i, counts in enumerate(self.tf):
            score = 0.0
            dl = self.doc_len[i] or 1
            norm = self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
            for term in terms:
                f = counts.get(term)
                if f:
                    score += self.idf.get(term, 0.0) * (f * (self.k1 + 1)) / (f + norm)
            if score > 0:
                scores.append((i, score))
        scores.sort(key=lambda kv: kv[1], reverse=True)
        return [(self.notes[i], s) for i, s in scores[:limit]]


def highlight(text: str, query: str, width: int = 120) -> str:
    """Return a one-line snippet of `text` around the first query-term hit."""
    terms = set(tokenize(query))
    if not terms:
        return re.sub(r"\s+", " ", text).strip()[:width]
    lowered = text.lower()
    pos = -1
    for m in re.finditer(r"[a-z0-9_]+|[一-鿿㐀-䶿぀-ヿ가-힯]", lowered):
        tok = m.group(0)
        if tok in terms or any(len(t) == 2 and tok in t for t in terms):
            pos = m.start()
            break
    snippet = re.sub(r"\s+", " ", text).strip()
    if pos < 0:
        return snippet[:width]
    start = max(0, pos - width // 3)
    out = snippet[start:start + width]
    return ("…" if start > 0 else "") + out + ("…" if start + width < len(snippet) else "")
