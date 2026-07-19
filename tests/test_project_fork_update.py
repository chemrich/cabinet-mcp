"""Tests for project forking and delta editing.

Covers duplicate_project (fork with lineage), apply_project_patch /
update_saved_project (the update_project engine), and the design_project
overwrite guard — pure functions plus end-to-end runs of the MCP handlers.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from cadquery_furniture.project import (
    apply_project_patch,
    build_project,
    duplicate_project,
    list_saved_projects,
    load_project,
    project_from_dict,
    project_to_dict,
    save_project,
    update_saved_project,
)
from cadquery_furniture.server import (
    _tool_design_project,
    _tool_duplicate_project,
    _tool_update_project,
)


def _run(coro):
    # Match the existing test_server_*.py convention. ``asyncio.run`` would
    # create *and close* a fresh loop on each invocation, which breaks any
    # later test that calls ``asyncio.get_event_loop()``.
    return asyncio.get_event_loop().run_until_complete(coro)


def _payload(name: str = "fork_src") -> dict:
    return {
        "name": name,
        "notes": "original build notes",
        "shared": {"drawer_slide": "blum_tandem_550h", "side_thickness": 18},
        "cabinets": [
            {"name": "a", "config": {
                "width": 600, "height": 720, "depth": 500,
                "drawer_config": [[360, "drawer"], [360, "drawer"]]}},
            {"name": "b", "config": {
                "width": 400, "height": 720, "depth": 500,
                "drawer_config": [[720, "door"]]}},
        ],
    }


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Redirect the project store to tmp and pre-save the sample project."""
    from cadquery_furniture import project as pmod
    monkeypatch.setattr(pmod, "project_dir", lambda: tmp_path)
    save_project(build_project(_payload()))
    return tmp_path


# ─── duplicate_project ────────────────────────────────────────────────────────


class TestDuplicateProject:
    def test_fork_copies_and_stamps_lineage(self, store):
        path = duplicate_project("fork_src", "fork_dst")
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["name"] == "fork_dst"
        assert data["forked_from"] == "fork_src"
        assert data["forked_at"]  # ISO timestamp present
        # Source untouched — no lineage stamped there
        src = json.loads((store / "fork_src.json").read_text())
        assert "forked_from" not in src
        # The fork resolves to the same designs as the source
        for (n1, c1), (n2, c2) in zip(
            load_project("fork_src").resolved(), load_project("fork_dst").resolved()
        ):
            assert n1 == n2
            assert c1.width == c2.width
            assert c1.drawer_slide == c2.drawer_slide

    def test_refuses_to_overwrite_existing(self, store):
        duplicate_project("fork_src", "fork_dst")
        with pytest.raises(ValueError, match="already exists"):
            duplicate_project("fork_src", "fork_dst")

    def test_missing_source_raises(self, store):
        with pytest.raises(FileNotFoundError):
            duplicate_project("nope", "fork_dst")

    def test_notes_replacement(self, store):
        duplicate_project("fork_src", "fork_dst", notes="experiment: deeper boxes")
        assert load_project("fork_dst").notes == "experiment: deeper boxes"
        # Default keeps the copied notes
        duplicate_project("fork_src", "fork_dst2")
        assert load_project("fork_dst2").notes == "original build notes"

    def test_lineage_survives_round_trips(self, store):
        duplicate_project("fork_src", "fork_dst")
        proj = load_project("fork_dst")
        assert proj.forked_from == "fork_src"
        # dict round-trip (save/load path)
        again = project_from_dict(project_to_dict(proj))
        assert again.forked_from == "fork_src"
        assert again.forked_at == proj.forked_at
        # build_project round-trip (load_project tool -> design_project path)
        rebuilt = build_project(project_to_dict(proj))
        assert rebuilt.forked_from == "fork_src"

    def test_listing_shows_forked_from(self, store):
        duplicate_project("fork_src", "fork_dst")
        entries = {e["name"]: e for e in list_saved_projects()}
        assert entries["fork_dst"]["forked_from"] == "fork_src"
        assert "forked_from" not in entries["fork_src"]


# ─── apply_project_patch ──────────────────────────────────────────────────────


class TestApplyProjectPatch:
    def _base(self) -> dict:
        return project_to_dict(build_project(_payload()))

    def test_notes_and_wall(self):
        out, changes = apply_project_patch(
            self._base(), {"notes": "new", "wall_width_mm": 2000})
        assert out["notes"] == "new"
        assert out["wall_width_mm"] == 2000.0
        out2, _ = apply_project_patch(out, {"wall_width_mm": None})
        assert "wall_width_mm" not in out2
        assert "notes replaced" in changes

    def test_shared_merge_and_clear(self):
        out, changes = apply_project_patch(self._base(), {
            "shared": {"drawer_slide": "blum_movento_769", "side_thickness": None}})
        assert out["shared"]["drawer_slide"] == "blum_movento_769"
        assert "side_thickness" not in out["shared"]
        assert any("shared.side_thickness cleared" in c for c in changes)

    def test_config_patch_pins_shared_token_override(self):
        # Shared slide is tandem; pinning movento on one cabinet must add the
        # override so the child's value survives resolution (round-tripped
        # overrides lists are exhaustive).
        out, _ = apply_project_patch(self._base(), {
            "cabinets": [{"name": "a", "config": {"drawer_slide": "blum_movento_769"}}]})
        resolved = dict(build_project(out).resolved())
        assert resolved["a"].drawer_slide == "blum_movento_769"
        assert resolved["b"].drawer_slide == "blum_tandem_550h"

    def test_config_null_clears_key_and_override(self):
        patched, _ = apply_project_patch(self._base(), {
            "cabinets": [{"name": "a", "config": {"drawer_slide": "blum_movento_769"}}]})
        cleared, _ = apply_project_patch(patched, {
            "cabinets": [{"name": "a", "config": {"drawer_slide": None}}]})
        entry = next(c for c in cleared["cabinets"] if c["name"] == "a")
        assert "drawer_slide" not in entry["config"]
        assert "drawer_slide" not in entry["overrides"]
        # Shared token applies again
        assert dict(build_project(cleared).resolved())["a"].drawer_slide == "blum_tandem_550h"

    def test_explicit_overrides_replace_and_skip_autopin(self):
        out, _ = apply_project_patch(self._base(), {
            "cabinets": [{"name": "a",
                          "config": {"drawer_slide": "blum_movento_769"},
                          "overrides": []}]})
        # Explicit empty overrides: shared token wins at resolve time
        assert dict(build_project(out).resolved())["a"].drawer_slide == "blum_tandem_550h"

    def test_rename_add_remove(self):
        out, changes = apply_project_patch(self._base(), {"cabinets": [
            {"name": "b", "new_name": "bee"},
            {"name": "c", "add": True, "config": {
                "width": 300, "height": 720, "depth": 500,
                "drawer_config": [[720, "door"]]}},
        ]})
        names = [c["name"] for c in out["cabinets"]]
        assert names == ["a", "bee", "c"]
        out2, _ = apply_project_patch(out, {"cabinets": [{"name": "c", "remove": True}]})
        assert [c["name"] for c in out2["cabinets"]] == ["a", "bee"]
        assert "cabinet 'b' renamed to 'bee'" in changes

    def test_added_cabinet_infers_overrides(self):
        # A new cabinet has no exhaustive overrides list, so key-presence
        # inference applies — its explicit slide should stick.
        out, _ = apply_project_patch(self._base(), {"cabinets": [
            {"name": "c", "add": True, "config": {
                "width": 300, "height": 720, "depth": 500,
                "drawer_slide": "blum_movento_769",
                "drawer_config": [[360, "drawer"], [360, "drawer"]]}}]})
        assert dict(build_project(out).resolved())["c"].drawer_slide == "blum_movento_769"

    def test_error_paths(self):
        base = self._base()
        with pytest.raises(ValueError, match="No cabinet named 'zz'"):
            apply_project_patch(base, {"cabinets": [{"name": "zz", "config": {"width": 1}}]})
        with pytest.raises(ValueError, match="already exists"):
            apply_project_patch(base, {"cabinets": [{"name": "a", "new_name": "b"}]})
        with pytest.raises(ValueError, match="already exists"):
            apply_project_patch(base, {"cabinets": [{"name": "a", "add": True, "config": {"width": 1}}]})
        with pytest.raises(ValueError, match="requires a 'config'"):
            apply_project_patch(base, {"cabinets": [{"name": "c", "add": True}]})
        with pytest.raises(ValueError, match="at least one cabinet"):
            apply_project_patch(base, {"cabinets": [
                {"name": "a", "remove": True}, {"name": "b", "remove": True}]})

    def test_base_is_not_mutated(self):
        base = self._base()
        snapshot = json.loads(json.dumps(base))
        apply_project_patch(base, {
            "notes": "x",
            "shared": {"drawer_slide": "blum_movento_769"},
            "cabinets": [{"name": "a", "config": {"height": 700}}]})
        assert base == snapshot


# ─── update_saved_project ─────────────────────────────────────────────────────


class TestUpdateSavedProject:
    def test_patch_persists(self, store):
        project, changes = update_saved_project({
            "name": "fork_src",
            "cabinets": [{"name": "a", "config": {"height": 781}}]})
        assert changes
        assert dict(load_project("fork_src").resolved())["a"].height == 781

    def test_empty_patch_saves_nothing(self, store):
        path = store / "fork_src.json"
        before = path.stat().st_mtime_ns
        project, changes = update_saved_project({"name": "fork_src"})
        assert changes == []
        assert path.stat().st_mtime_ns == before

    def test_invalid_patch_leaves_snapshot_untouched(self, store):
        path = store / "fork_src.json"
        before = path.read_text()
        with pytest.raises(ValueError):
            update_saved_project({
                "name": "fork_src",
                "cabinets": [{"name": "zz", "config": {"width": 1}}]})
        assert path.read_text() == before

    def test_missing_project_raises(self, store):
        with pytest.raises(FileNotFoundError):
            update_saved_project({"name": "nope", "notes": "x"})


# ─── MCP handlers end-to-end ──────────────────────────────────────────────────


class TestHandlers:
    def test_design_project_overwrite_guard(self, store):
        out = _run(_tool_design_project(_payload()))
        assert out[0].text.startswith("ERROR")
        assert "overwrite=true" in out[0].text
        # Snapshot untouched by the refused call
        assert load_project("fork_src").notes == "original build notes"
        data = json.loads(_run(_tool_design_project(
            {**_payload(), "notes": "v2", "overwrite": True}))[0].text)
        assert data["name"] == "fork_src"
        assert load_project("fork_src").notes == "v2"

    def test_duplicate_tool(self, store):
        data = json.loads(_run(_tool_duplicate_project(
            {"name": "fork_src", "new_name": "fork_dst"}))[0].text)
        assert data["name"] == "fork_dst"
        assert data["forked_from"] == "fork_src"
        assert data["forked_at"]
        assert data["cabinet_count"] == 2
        out = _run(_tool_duplicate_project({"name": "fork_src"}))
        assert out[0].text.startswith("ERROR")  # missing new_name

    def test_update_tool(self, store):
        data = json.loads(_run(_tool_update_project({
            "name": "fork_src",
            "shared": {"drawer_slide": "blum_movento_769"},
            "cabinets": [{"name": "a", "config": {"height": 781}}]}))[0].text)
        assert any("a.config.height" in c for c in data["changes"])
        cabs = {c["name"]: c for c in data["cabinets"]}
        assert cabs["a"]["exterior_mm"]["height"] == 781
        assert cabs["b"]["drawer_slide"] == "blum_movento_769"

    def test_update_tool_empty_patch(self, store):
        data = json.loads(_run(_tool_update_project({"name": "fork_src"}))[0].text)
        assert data["changes"] == []
        assert "nothing to change" in data["note"]
