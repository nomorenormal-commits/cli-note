"""Headless TUI test via Textual Pilot."""

import pytest

from cli_note.store import Vault
from cli_note.tui import NoteApp


@pytest.mark.anyio
async def test_tui_mounts_and_lists_notes(tmp_path):
    vault = Vault(tmp_path)
    vault.create("TUI Note", "body text", ["ui"])
    app = NoteApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        ids = app._note_ids()
        assert "TUI-Note" in ids
        # live search
        app.query_one("#search").value = "tui"
        await pilot.pause()
        assert app._note_ids() == ["TUI-Note"]
        app.query_one("#search").value = "zzzz"
        await pilot.pause()
        assert app._note_ids() == []
