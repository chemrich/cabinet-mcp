"""Tests for the multi-cabinet project feature.

Covers the pure-Python core (merge semantics, persistence, cross-cabinet
checks) plus end-to-end runs of the three MCP tools (design_project,
evaluate_project, generate_project_cutlist).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from cadquery_furniture.project import (
    SharedDesign,
    ProjectCabinet,
    CabinetProject,
    build_project,
    save_project,
    load_project,
    check_project_consistency,
    project_to_dict,
    project_from_dict,
)
from cadquery_furniture.cabinet import CabinetConfig
from cadquery_furniture.joinery import CarcassJoinery
from cadquery_furniture.server import (
    _tool_design_project,
    _tool_evaluate_project,
    _tool_generate_project_cutlist,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _sample_payload(name: str = "trio") -> dict:
    """Three identical sideboards sharing design tokens."""
    return {
        "name": name,
        "shared": {
            "side_thickness": 18,
            "drawer_slide": "blum_tandem_550h",
            "pull_preset": "contemporary_slab",
            "carcass_joinery": "floating_tenon",
        },
        "cabinets": [
            {"name": "left",   "config": {"width": 1219, "height": 762, "depth": 500,
                                           "openings": [[150, "drawer"], [596, "door_pair"]]}},
            {"name": "center", "config": {"width": 1219, "height": 762, "depth": 500,
                                           "openings": [[150, "drawer"], [596, "door_pair"]]}},
            {"name": "right",  "config": {"width": 1219, "height": 762, "depth": 500,
                                           "openings": [[150, "drawer"], [596, "door_pair"]]}},
        ],
    }


# ─── Merge semantics ──────────────────────────────────────────────────────────


class TestSharedDesignMerge:
    def test_shared_tokens_apply_to_every_child(self):
        proj = build_project(_sample_payload())
        for _, cfg in proj.resolved():
            assert cfg.side_thickness == 18
            assert cfg.drawer_slide == "blum_tandem_550h"
            assert cfg.carcass_joinery == CarcassJoinery.FLOATING_TENON

    def test_pull_preset_expands_to_drawer_and_door_pulls(self):
        proj = build_project(_sample_payload())
        first = proj.resolved()[0][1]
        assert first.drawer_pull is not None
        assert first.door_pull is not None

    def test_child_explicit_field_wins_over_shared(self):
        payload = _sample_payload()
        payload["cabinets"][2]["config"]["drawer_slide"] = "accuride_3832"
        proj = build_project(payload)
        resolved = dict(proj.resolved())
        assert resolved["left"].drawer_slide == "blum_tandem_550h"
        assert resolved["center"].drawer_slide == "blum_tandem_550h"
        assert resolved["right"].drawer_slide == "accuride_3832"

    def test_override_set_captures_child_explicit_keys(self):
        payload = _sample_payload()
        payload["cabinets"][2]["config"]["drawer_slide"] = "accuride_3832"
        proj = build_project(payload)
        assert "drawer_slide" in proj.cabinets[2].overrides
        assert "drawer_slide" not in proj.cabinets[0].overrides

    def test_empty_shared_block_is_a_noop(self):
        payload = _sample_payload()
        payload["shared"] = {}
        proj = build_project(payload)
        # Should still resolve cleanly; child defaults preserved
        assert len(proj.resolved()) == 3

    def test_child_explicit_pull_wins_over_shared_pull_preset(self):
        # Regression: shared pull_preset expands into drawer_pull/door_pull
        # at merge time, which used to clobber a child's explicit pull
        # because "drawer_pull" never intersected the shared key set.
        from cadquery_furniture.hardware import get_pull_preset
        preset = get_pull_preset("contemporary_slab")

        payload = _sample_payload()
        payload["cabinets"][1]["config"]["drawer_pull"] = "topknobs-hb-128"
        proj = build_project(payload)
        resolved = dict(proj.resolved())

        assert resolved["center"].drawer_pull == "topknobs-hb-128"
        # door_pull wasn't pinned by the child, so it still follows the preset
        assert resolved["center"].door_pull == preset.door_pull
        # untouched siblings still get both pulls from the preset
        assert resolved["left"].drawer_pull == preset.drawer_pull

    def test_child_pull_preset_wins_over_shared_pull_preset(self):
        from cadquery_furniture.hardware import get_pull_preset
        child_preset = get_pull_preset("industrial_black")

        payload = _sample_payload()
        payload["cabinets"][2]["config"]["pull_preset"] = "industrial_black"
        proj = build_project(payload)
        resolved = dict(proj.resolved())

        assert resolved["right"].drawer_pull == child_preset.drawer_pull
        assert resolved["right"].door_pull == child_preset.door_pull


# ─── Persistence ──────────────────────────────────────────────────────────────


class TestProjectPersistence:
    def test_round_trip_through_dict(self):
        proj = build_project(_sample_payload())
        d = project_to_dict(proj)
        loaded = project_from_dict(d)
        assert loaded.name == proj.name
        assert len(loaded.cabinets) == len(proj.cabinets)
        # Resolved configs match across the round-trip
        for (n1, c1), (n2, c2) in zip(proj.resolved(), loaded.resolved()):
            assert n1 == n2
            assert c1.width == c2.width
            assert c1.drawer_slide == c2.drawer_slide

    def test_save_and_load_from_disk(self, tmp_path, monkeypatch):
        # Redirect the project dir to a tmp location
        from cadquery_furniture import project as pmod
        monkeypatch.setattr(pmod, "project_dir", lambda: tmp_path)
        proj = build_project(_sample_payload(name="tmp_proj"))
        path = save_project(proj)
        assert path.exists()
        loaded = load_project("tmp_proj")
        assert loaded.name == "tmp_proj"
        assert len(loaded.cabinets) == 3

    def test_load_missing_project_raises(self, tmp_path, monkeypatch):
        from cadquery_furniture import project as pmod
        monkeypatch.setattr(pmod, "project_dir", lambda: tmp_path)
        with pytest.raises(FileNotFoundError):
            load_project("does_not_exist")


# ─── Cross-cabinet checks ─────────────────────────────────────────────────────


class TestProjectConsistencyChecks:
    def test_matching_run_has_no_issues(self):
        proj = build_project(_sample_payload())
        assert check_project_consistency(proj) == []

    def test_depth_divergence_emits_warning(self):
        payload = _sample_payload()
        payload["cabinets"][1]["config"]["depth"] = 550
        proj = build_project(payload)
        issues = check_project_consistency(proj)
        checks = {i["check"] for i in issues}
        assert "project_depth_match" in checks

    def test_height_divergence_emits_warning(self):
        payload = _sample_payload()
        payload["cabinets"][2]["config"]["height"] = 900
        proj = build_project(payload)
        issues = check_project_consistency(proj)
        checks = {i["check"] for i in issues}
        assert "project_height_match" in checks


# ─── MCP tool end-to-end ──────────────────────────────────────────────────────


def _run(coro):
    # Match the existing test_server_*.py convention. ``asyncio.run`` would
    # create *and close* a fresh loop on each invocation, which breaks any
    # later test that calls ``asyncio.get_event_loop()`` (e.g. test_server_pulls).
    return asyncio.get_event_loop().run_until_complete(coro)


class TestDesignProjectTool:
    def test_returns_per_cabinet_summary_and_persists(self, tmp_path, monkeypatch):
        from cadquery_furniture import project as pmod
        monkeypatch.setattr(pmod, "project_dir", lambda: tmp_path)
        out = _run(_tool_design_project(_sample_payload(name="tool_smoke")))
        data = json.loads(out[0].text)
        assert data["cabinet_count"] == 3
        assert data["total_run_width_mm"] == pytest.approx(3 * 1219)
        assert Path(data["saved_to"]).exists()
        assert all(c["drawer_pull"] for c in data["cabinets"])


class TestEvaluateProjectTool:
    def test_evaluate_inline_payload(self):
        out = _run(_tool_evaluate_project({"project": _sample_payload()}))
        data = json.loads(out[0].text)
        assert "by_cabinet" in data
        assert set(data["by_cabinet"].keys()) == {"left", "center", "right"}
        assert "summary" in data
        assert data["summary"]["cabinet_count"] == 3

    def test_evaluate_flags_depth_mismatch(self):
        payload = _sample_payload()
        payload["cabinets"][1]["config"]["depth"] = 550
        out = _run(_tool_evaluate_project({"project": payload}))
        data = json.loads(out[0].text)
        checks = {i["check"] for i in data["project_issues"]}
        assert "project_depth_match" in checks

    def test_evaluate_requires_project_or_project_name(self):
        # The MCP dispatcher in server.call_tool wraps handler exceptions into
        # an ERROR response, but the bare handler propagates them — that's the
        # contract we want from the helper.
        with pytest.raises(ValueError, match="project_name"):
            _run(_tool_evaluate_project({}))


class TestGenerateProjectCutlistTool:
    def test_combined_cutlist_merges_identical_panels(self, tmp_path, monkeypatch):
        # Redirect both the project dir and the cutlist output dir.
        from cadquery_furniture import project as pmod
        monkeypatch.setattr(pmod, "project_dir", lambda: tmp_path / "projects")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        out = _run(_tool_generate_project_cutlist({"project": _sample_payload(name="merge_check")}))
        data = json.loads(out[0].text)

        # Three identical cabinets → carcass sides should consolidate to a
        # single panel row with quantity == 3 × 2 = 6.
        sides = [p for p in data["panels_summary"] if p["name"] == "side"]
        assert len(sides) == 1, sides
        assert sides[0]["qty"] == 6

        # Backs: one per cabinet → quantity == 3
        backs = [p for p in data["panels_summary"] if p["name"] == "back"]
        assert len(backs) == 1
        assert backs[0]["qty"] == 3

        # Sheet output files were written
        assert "csv" in data["files"]
        assert "json" in data["files"]
        # All output files live under the project subdir
        for path in data["files"].values():
            assert "merge_check" in path

    def test_mixed_carcass_thickness_gets_own_sheet_group(self, tmp_path, monkeypatch):
        # Regression: carcass panels used to be packed (and priced) as a
        # single group at the first cabinet's side_thickness even when a
        # child overrode it.
        from cadquery_furniture import project as pmod
        monkeypatch.setattr(pmod, "project_dir", lambda: tmp_path / "projects")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        payload = _sample_payload(name="mixed_t")
        payload["cabinets"][1]["config"]["side_thickness"] = 12
        out = _run(_tool_generate_project_cutlist({"project": payload}))
        data = json.loads(out[0].text)

        # Both carcass thicknesses appear as separate sheet-goods groups.
        thicknesses = {g["thickness_mm"] for g in data["sheet_goods"]}
        assert {18, 12} <= thicknesses, data["sheet_goods"]

        # Side panels no longer consolidate across the thickness split:
        # 2 cabinets × 2 sides at 18 mm, 1 cabinet × 2 sides at 12 mm.
        sides = {p["thickness_mm"]: p["qty"]
                 for p in data["panels_summary"] if p["name"] == "side"}
        assert sides == {18: 4, 12: 2}, sides
