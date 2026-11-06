# cli-note

Local-first Markdown note-taking for the terminal — with tags, BM25 full-text
search, an interactive TUI, and a **built-in MCP server** so AI clients
(DSH, Claude Desktop, any MCP host) can read and manage your notes.
One codebase, two uses: a CLI/TUI for you, an MCP server for your agents.

## Features

- **Markdown notes, Obsidian-compatible** — every note is a plain `.md` file
  with YAML frontmatter; `[[wiki-links]]`, inline `#tags`, and your vault
  opens directly in Obsidian.
- **Tag management** — frontmatter tags + inline tags, counts, filtering.
- **BM25 full-text search** — Okapi BM25 with field boosts (title > tags >
  body) and a mixed Latin/CJK tokenizer (中文搜索开箱即用).
- **TUI** — Textual-based interface with live search, preview, tag bar.
- **MCP server over stdio** — 7 tools + 2 resources, zero extra processes.
- **Zero core dependencies** for storage/search; only `mcp` is required,
  `textual` only for the TUI.

## Install

```bash
pip install -e .          # CLI + MCP server
pip install -e ".[tui]"   # + TUI
```

Python ≥ 3.10.

## Quick start

```bash
cli-note init                          # create the vault
cli-note new "BM25 算法笔记" -t search,ml -c "k1 与 b 是调节参数"
cli-note list                          # or: cli-note ls -t ml
cli-note search "全文检索" -v           # BM25 ranked, with snippets
cli-note show BM25                     # id / title / unique prefix all work
cli-note edit BM25 -t search,ml,ir     # or omit -c/-t to edit in $EDITOR
cli-note tags
cli-note rm BM25 -y
```

Vault location: `--vault PATH` > `$CLI_NOTE_VAULT` > `~/.cli-note/vault`.

## TUI

```bash
cli-note tui
```

| Key | Action        | Key | Action          |
|-----|---------------|-----|-----------------|
| `/` | focus search  | `n` | new note        |
| `Esc` | clear search/filter | `e` | edit in $EDITOR |
| `t` | filter top tag | `d` | delete note     |
| `r` | reload vault  | `q` | quit            |

Search is live (BM25) and the preview renders Markdown as you move.

## MCP server

Run over stdio; register with any MCP client:

```bash
cli-note mcp                  # uses default vault
cli-note --vault ~/notes mcp  # explicit vault
```

Claude Desktop / DSH config example:

```json
{
  "mcpServers": {
    "cli-note": {
      "command": "cli-note",
      "args": ["--vault", "C:/Users/you/notes", "mcp"]
    }
  }
}
```

or `claude mcp add cli-note -- cli-note mcp`.

**Tools**: `list_notes`, `read_note`, `search_notes` (BM25, with snippets),
`create_note`, `update_note` (supports `append`), `delete_note`, `list_tags`.
**Resources**: `notes://index` (vault index), `note://{id}` (raw Markdown).

## Vault format

```markdown
---
title: BM25 算法笔记
tags: [search, ml]
created: 2026-11-06T04:11:36+00:00
modified: 2026-11-06T04:11:36+00:00
---

Body in plain Markdown. [[Other Note]] links and #inline-tags are picked up.
```

Filenames are the note id (slugified title, CJK preserved). Rename via
`edit --title` moves the file. Everything stays plain text and git-friendly.

## Development

```bash
pip install -e ".[dev]"
pytest          # 24 tests: store, BM25, MCP tools, headless TUI
```

Layout: `src/cli_note/` — `models.py` (frontmatter), `store.py` (vault CRUD,
tags, backlinks), `search.py` (BM25), `cli.py`, `tui.py`, `mcp_server.py`.
