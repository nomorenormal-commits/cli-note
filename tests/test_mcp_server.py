"""MCP server tool surface tests (no transport, direct calls)."""

import json

import pytest

from cli_note.mcp_server import build_server
from cli_note.store import Vault


@pytest.fixture()
def server(tmp_path):
    vault = Vault(tmp_path)
    vault.create("MCP Test", "the mcp protocol connects tools", ["mcp"])
    vault.create("Other", "unrelated content", ["misc"])
    return build_server(tmp_path)


async def _call(server, tool, **kwargs):
    result = await server.call_tool(tool, kwargs)
    # FastMCP returns (content, structured) tuple or content list depending on version
    content = result[0] if isinstance(result, tuple) else result
    text = content[0].text if isinstance(content, list) else content.text
    return text


@pytest.mark.anyio
async def test_tools_registered(server):
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert {"list_notes", "read_note", "search_notes", "create_note",
            "update_note", "delete_note", "list_tags"} <= names


@pytest.mark.anyio
async def test_search_and_read(server):
    hits = json.loads(await _call(server, "search_notes", query="mcp protocol"))
    assert hits and hits[0]["id"] == "MCP-Test"

    note = json.loads(await _call(server, "read_note", note="MCP-Test"))
    assert "protocol" in note["content"]
    assert note["tags"] == ["mcp"]


@pytest.mark.anyio
async def test_create_update_delete(server):
    created = json.loads(await _call(server, "create_note", title="via mcp", content="hi", tags=["t"]))
    assert created["created"]["id"] == "via-mcp"

    updated = json.loads(await _call(server, "update_note", note="via-mcp", content=" more", append=True))
    assert updated["updated"]["id"] == "via-mcp"

    deleted = json.loads(await _call(server, "delete_note", note="via-mcp"))
    assert deleted["deleted"] == "via-mcp"


@pytest.mark.anyio
async def test_list_tags(server):
    tags = json.loads(await _call(server, "list_tags"))
    assert tags == {"mcp": 1, "misc": 1}
