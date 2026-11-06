"""Note model and Obsidian-compatible YAML frontmatter handling."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

_WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]")
_INLINE_TAG_RE = re.compile(r"(?<![\w/#])#([A-Za-z0-9_\-\u4e00-\u9fff/]+)")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(title: str) -> str:
    """Turn a title into a filename-safe slug, keeping CJK characters."""
    slug = title.strip()
    slug = re.sub(r"[\\/:*?\"<>|]", "", slug)  # illegal filename chars
    slug = re.sub(r"\s+", "-", slug)
    slug = slug.strip(".-_ ")
    return slug or "untitled"


@dataclass
class Note:
    """A single Markdown note."""

    id: str  # filename stem, unique within the vault
    title: str
    content: str  # markdown body (without frontmatter)
    tags: list[str] = field(default_factory=list)
    created: str = ""
    modified: str = ""
    path: str = ""  # absolute path on disk

    @property
    def links(self) -> list[str]:
        """Outgoing Obsidian wiki-links found in the body."""
        return [m.group(1).strip() for m in _WIKILINK_RE.finditer(self.content)]

    @property
    def inline_tags(self) -> list[str]:
        """#tags written inline in the body (Obsidian style)."""
        return _INLINE_TAG_RE.findall(self.content)

    @property
    def all_tags(self) -> list[str]:
        seen: dict[str, None] = {}
        for t in [*self.tags, *self.inline_tags]:
            seen.setdefault(t, None)
        return list(seen)

    def summary(self, width: int = 80) -> str:
        text = re.sub(r"\s+", " ", self.content).strip()
        return text if len(text) <= width else text[: width - 1] + "…"


# ---------------------------------------------------------------------------
# Frontmatter (de)serialization — minimal YAML subset, Obsidian compatible.
# Supports:  key: value,  key: [a, b],  key:\n  - a\n  - b
# ---------------------------------------------------------------------------


def _quote_scalar(value: str) -> str:
    if value == "" or re.search(r"[:#\[\]{}&,*!|>'\"%@`]", value) or value != value.strip():
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def dump_frontmatter(note: Note) -> str:
    lines = ["---"]
    lines.append(f"title: {_quote_scalar(note.title)}")
    if note.tags:
        tags = ", ".join(_quote_scalar(t) for t in note.tags)
        lines.append(f"tags: [{tags}]")
    lines.append(f"created: {note.created}")
    lines.append(f"modified: {note.modified}")
    lines.append("---")
    return "\n".join(lines)


def serialize(note: Note) -> str:
    body = note.content.strip("\n")
    fm = dump_frontmatter(note)
    return f"{fm}\n\n{body}\n" if body else f"{fm}\n"


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
        if value and value[0] != "'":
            value = value.replace('\\"', '"').replace("\\\\", "\\")
    return value


def parse_frontmatter(raw: str) -> tuple[dict[str, object], str]:
    """Split raw markdown into (frontmatter dict, body)."""
    if not raw.startswith("---"):
        return {}, raw
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", raw, re.DOTALL)
    if not m:
        return {}, raw
    fm_text, body = m.group(1), raw[m.end():]

    data: dict[str, object] = {}
    current_key: str | None = None
    for line in fm_text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and current_key:
            data.setdefault(current_key, [])
            if isinstance(data[current_key], list):
                data[current_key].append(_unquote(item.group(1)))
            continue
        kv = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if not kv:
            continue
        key, value = kv.group(1).lower(), kv.group(2).strip()
        current_key = key
        if value == "":
            data[key] = []
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = [_unquote(v) for v in inner.split(",") if v.strip()] if inner else []
        else:
            data[key] = _unquote(value)
    return data, body


def parse_note(note_id: str, raw: str, path: str = "") -> Note:
    data, body = parse_frontmatter(raw)
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    title = str(data.get("title") or note_id)
    return Note(
        id=note_id,
        title=title,
        content=body.strip("\n"),
        tags=[str(t) for t in tags],
        created=str(data.get("created") or ""),
        modified=str(data.get("modified") or ""),
        path=path,
    )
