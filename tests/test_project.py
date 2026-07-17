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

    def test_shared_pull_preset_applies_door_pull_inset(self, monkeypatch):
        # Regression: _merge expanded a shared pull_preset into the two pull
        # keys but dropped preset.door_pull_inset_mm — latent while every
        # shipped preset used the 50.0 default, wrong the moment one doesn't.
        from cadquery_furniture import hardware as hmod
        real = hmod.get_pull_preset("contemporary_slab")
        from dataclasses import replace as _dc_replace
        fake = _dc_replace(real, door_pull_inset_mm=75.0)
        monkeypatch.setattr(hmod, "get_pull_preset", lambda key: fake)

        proj = build_project(_sample_payload())
        for _, cfg in proj.resolved():
            assert cfg.door_pull_inset_mm == 75.0

    def test_design_cabinet_convenience_params_accepted(self):
        # Regression: num_drawers / drawer_proportion / furniture_top used to
        # raise TypeError inside CabinetConfig(**kwargs) despite the tool
        # description promising design_cabinet-shaped child configs.
        payload = {
            "name": "conv",
            "cabinets": [{"name": "a", "config": {
                "width": 600, "height": 720, "depth": 550,
                "num_drawers": 3, "furniture_top": True,
            }}],
        }
        proj = build_project(payload)
        cfg = proj.resolved()[0][1]
        assert len(cfg.openings) == 3
        assert all(op.opening_type == "drawer" for op in cfg.openings)
        # Largest drawer at the bottom, stack fills the interior height
        heights = [op.height_mm for op in cfg.openings]
        assert heights == sorted(heights, reverse=True)
        assert sum(heights) == pytest.approx(720 - 36)


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

    def test_shelf_pin_fields_survive_round_trip(self):
        # Regression: _config_to_dict omitted shelf_pin_* fields, silently
        # resetting them to defaults on save/load.
        payload = {
            "name": "pins",
            "cabinets": [{"name": "a", "config": {
                "width": 600, "height": 720, "depth": 550,
                "adj_shelf_holes": True,
                "shelf_pin_spacing": 25.0,
                "shelf_pin_row_inset": 45.0,
            }}],
        }
        proj = build_project(payload)
        loaded = project_from_dict(project_to_dict(proj))
        cfg = loaded.resolved()[0][1]
        assert cfg.shelf_pin_spacing == 25.0
        assert cfg.shelf_pin_row_inset == 45.0

    def test_joinery_specs_survive_round_trip(self):
        # Regression: custom domino/pocket-screw/biscuit/dowel specs were
        # dropped by _config_to_dict and reset to defaults on load.
        from cadquery_furniture.joinery import DominoSpec
        payload = {
            "name": "specs",
            "cabinets": [{"name": "a", "config": {
                "width": 600, "height": 720, "depth": 550,
            }}],
        }
        proj = build_project(payload)
        custom = DominoSpec(size_key="10x50", max_spacing=120.0)
        pc = proj.cabinets[0]
        from dataclasses import replace as _dc_replace
        proj = CabinetProject(
            name=proj.name,
            cabinets=(ProjectCabinet(pc.name, _dc_replace(pc.config, domino_spec=custom)),),
            shared=proj.shared,
        )
        loaded = project_from_dict(project_to_dict(proj))
        cfg = loaded.resolved()[0][1]
        assert isinstance(cfg.domino_spec, DominoSpec)
        assert cfg.domino_spec.size_key == "10x50"
        assert cfg.domino_spec.max_spacing == 120.0

    def test_column_fixed_shelves_survive_round_trip(self):
        # Regression: ColumnConfig dropped per-column fixed_shelf_positions,
        # losing shelves from persisted projects permanently.
        payload = {
            "name": "colshelf",
            "cabinets": [{"name": "a", "config": {
                "width": 1200, "height": 762, "depth": 500,
                "columns": [
                    {"width_mm": 570, "openings": [[706, "door"]],
                     "fixed_shelf_positions": [250, 500]},
                    {"width_mm": 576, "openings": [[200, "drawer"], [506, "open"]]},
                ],
            }}],
        }
        proj = build_project(payload)
        loaded = project_from_dict(project_to_dict(proj))
        cfg = loaded.resolved()[0][1]
        assert cfg.columns[0].fixed_shelf_positions == (250.0, 500.0)
        assert cfg.columns[1].fixed_shelf_positions == ()

    def test_project_names_with_path_separators_rejected(self, tmp_path, monkeypatch):
        # Regression: raw names were used as filename stems — "kitchen/run"
        # crashed with FileNotFoundError and "../evil" escaped the projects dir.
        from cadquery_furniture import project as pmod
        monkeypatch.setattr(pmod, "project_dir", lambda: tmp_path)
        for bad in ("kitchen/run", "../evil", ".hidden", ""):
            with pytest.raises(ValueError):
                save_project(build_project(_sample_payload(name=bad)))
            with pytest.raises(ValueError):
                load_project(bad)

    def test_over_long_project_name_rejected(self, tmp_path, monkeypatch):
        # Regression: names were length-unbounded, so a very long name reached
        # the filesystem and failed with OSError on write.
        from cadquery_furniture import project as pmod
        monkeypatch.setattr(pmod, "project_dir", lambda: tmp_path)
        assert pmod.project_path("a" * 100).name == "a" * 100 + ".json"
        with pytest.raises(ValueError):
            pmod.project_path("a" * 101)


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

    def test_alignment_baseline_skips_drawerless_lead_cabinet(self):
        # Regression: the alignment check used cabinets[0] as its baseline, so
        # a leading door-only cabinet (no drawer faces) suppressed the whole
        # check — two later cabinets could clash unnoticed. The baseline must
        # be the first cabinet that actually has drawer faces.
        payload = {
            "name": "align_test",
            "cabinets": [
                {"name": "base", "config": {"width": 600, "height": 720, "depth": 550,
                                            "openings": [[684, "door"]]}},
                {"name": "b", "config": {"width": 600, "height": 720, "depth": 550,
                                         "openings": [[300, "drawer"], [384, "drawer"]]}},
                {"name": "c", "config": {"width": 600, "height": 720, "depth": 550,
                                         "openings": [[400, "drawer"], [284, "drawer"]]}},
            ],
        }
        proj = build_project(payload)
        checks = {i["check"] for i in check_project_consistency(proj)}
        assert "project_drawer_face_alignment" in checks

    def test_alignment_silent_when_drawer_faces_match(self):
        payload = {
            "name": "align_ok",
            "cabinets": [
                {"name": "base", "config": {"width": 600, "height": 720, "depth": 550,
                                            "openings": [[684, "door"]]}},
                {"name": "b", "config": {"width": 600, "height": 720, "depth": 550,
                                         "openings": [[300, "drawer"], [384, "drawer"]]}},
                {"name": "c", "config": {"width": 600, "height": 720, "depth": 550,
                                         "openings": [[300, "drawer"], [384, "drawer"]]}},
            ],
        }
        proj = build_project(payload)
        checks = {i["check"] for i in check_project_consistency(proj)}
        assert "project_drawer_face_alignment" not in checks


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

    def test_single_column_cabinet_gets_drawer_box_panels(self, tmp_path, monkeypatch):
        # Regression: single-column cabinets (openings/drawer_config, no
        # columns) produced slides in the hardware BOM but zero drawer-box
        # and false-front panels in the combined cutlist.
        from cadquery_furniture import project as pmod
        monkeypatch.setattr(pmod, "project_dir", lambda: tmp_path / "projects")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        payload = {
            "name": "single_col",
            "cabinets": [{"name": "a", "config": {
                "width": 600, "height": 720, "depth": 550,
                "drawer_config": [[200, "drawer"], [200, "drawer"], [250, "drawer"]],
            }}],
        }
        out = _run(_tool_generate_project_cutlist({"project": payload}))
        data = json.loads(out[0].text)

        names = {p["name"] for p in data["panels_summary"]}
        assert {"drawer_box_side", "drawer_box_front", "drawer_box_back",
                "drawer_box_bottom", "false_front"} <= names, names

        # Panels and hardware must describe the same three drawers.
        n_false_fronts = sum(p["qty"] for p in data["panels_summary"]
                             if p["name"] == "false_front")
        slide_pairs = sum(h["pieces_needed"] // 2 for h in data["hardware_bom"]
                          if h["category"] == "slide")
        assert n_false_fronts == slide_pairs == 3

    def test_per_column_fixed_shelves_produce_shelf_panels(self, tmp_path, monkeypatch):
        # Regression: per-column fixed_shelf_positions vanished in the
        # project cutlist path (ColumnConfig didn't carry them).
        from cadquery_furniture import project as pmod
        monkeypatch.setattr(pmod, "project_dir", lambda: tmp_path / "projects")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        payload = {
            "name": "colshelf_cut",
            "cabinets": [{"name": "a", "config": {
                "width": 1200, "height": 762, "depth": 500,
                "columns": [
                    {"width_mm": 570, "openings": [[706, "door"]],
                     "fixed_shelf_positions": [250, 500]},
                    {"width_mm": 576, "openings": [[200, "drawer"], [506, "open"]]},
                ],
            }}],
        }
        out = _run(_tool_generate_project_cutlist({"project": payload}))
        data = json.loads(out[0].text)
        shelves = [p for p in data["panels_summary"] if p["name"].startswith("shelf")]
        assert sum(p["qty"] for p in shelves) == 2, shelves
        # Shelf panels are cut to the column's interior width
        assert all(p["length_mm"] == 570.0 for p in shelves), shelves


# ─── Cross-cabinet checks (extended) ──────────────────────────────────────────


class TestExtendedConsistencyChecks:
    def _run_with(self, mutate=None, wall=None):
        base = {"width": 800, "height": 720, "depth": 550,
                "drawer_config": [[150, "drawer"], [200, "drawer"], [298, "drawer"]]}
        payload = {
            "name": "checks",
            "cabinets": [
                {"name": "a", "config": dict(base)},
                {"name": "b", "config": dict(base)},
            ],
        }
        if wall is not None:
            payload["wall_width_mm"] = wall
        if mutate:
            payload["cabinets"][1]["config"].update(mutate)
        return check_project_consistency(build_project(payload))

    def test_wall_overflow_is_error(self):
        issues = self._run_with(wall=1500)   # run is 1600 mm
        wall = [i for i in issues if i["check"] == "project_wall_fit"]
        assert wall and wall[0]["severity"] == "error"

    def test_wall_gap_is_info(self):
        issues = self._run_with(wall=1700)
        wall = [i for i in issues if i["check"] == "project_wall_fit"]
        assert wall and wall[0]["severity"] == "info"
        assert "100.0 mm" in wall[0]["message"]

    def test_exact_wall_fit_is_silent(self):
        issues = self._run_with(wall=1600)
        assert not [i for i in issues if i["check"] == "project_wall_fit"]

    def test_hardware_divergence_is_info(self):
        issues = self._run_with(mutate={"drawer_slide": "accuride_3832"})
        hits = [i for i in issues if i["check"] == "project_drawer_slide_match"]
        assert hits and hits[0]["severity"] == "info"

    def test_material_divergence_is_warning(self):
        issues = self._run_with(mutate={"side_thickness": 15})
        hits = [i for i in issues if i["check"] == "project_side_thickness_match"]
        assert hits and hits[0]["severity"] == "warning"

    def test_misaligned_drawer_faces_flagged(self):
        issues = self._run_with(
            mutate={"drawer_config": [[250, "drawer"], [250, "drawer"], [148, "drawer"]]})
        hits = [i for i in issues if i["check"] == "project_drawer_face_alignment"]
        assert hits and hits[0]["severity"] == "info"

    def test_matched_run_stays_clean(self):
        assert self._run_with() == []

    def test_wall_width_survives_round_trip(self):
        payload = _sample_payload(name="wall_rt")
        payload["wall_width_mm"] = 3700
        proj = build_project(payload)
        assert project_from_dict(project_to_dict(proj)).wall_width_mm == 3700


class TestPerOpeningDetailInProjectCutlist:
    def test_pull_and_hinge_overrides_survive(self, tmp_path, monkeypatch):
        # Regression: _columns_dict_from_cfg used to flatten openings to
        # [height, type], losing hinge_key/pull_key/num_doors — project
        # hardware BOMs silently fell back to cabinet defaults.
        from cadquery_furniture import project as pmod
        monkeypatch.setattr(pmod, "project_dir", lambda: tmp_path / "projects")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        payload = {"name": "detail", "cabinets": [{"name": "a", "config": {
            "width": 1200, "height": 762, "depth": 500,
            "drawer_pull": "topknobs-bsn-96",
            "columns": [
                {"width_mm": 570, "openings": [
                    {"height_mm": 200, "opening_type": "drawer",
                     "pull_key": "topknobs-blk-128"},
                    {"height_mm": 506, "opening_type": "door_pair"},
                ]},
                {"width_mm": 576, "openings": [[706, "door"]]},
            ]}}]}
        out = _run(_tool_generate_project_cutlist({"project": payload}))
        data = json.loads(out[0].text)
        pull_models = {h["model_number"] for h in data["hardware_bom"]
                       if h["category"] == "pull"}
        # TK128BLK is topknobs-blk-128 — the per-opening override; the
        # cabinet default topknobs-bsn-96 would be TK96BSN.
        assert "TK128BLK" in pull_models, pull_models
        # door_pair (2 doors) + single door across a 762 mm face → 6 hinges
        hinges = sum(h["pieces_needed"] for h in data["hardware_bom"]
                     if h["category"] == "hinge")
        assert hinges == 6, hinges


class TestProjectLibrary:
    """list_saved_projects + the list/load tools and batched cutlists."""

    def _redirect(self, tmp_path, monkeypatch):
        from cadquery_furniture import project as pmod
        monkeypatch.setattr(pmod, "project_dir", lambda: tmp_path)

    def test_list_saved_projects_empty_store(self, tmp_path, monkeypatch):
        from cadquery_furniture.project import list_saved_projects
        self._redirect(tmp_path / "nonexistent", monkeypatch)
        assert list_saved_projects() == []

    def test_list_saved_projects_metadata(self, tmp_path, monkeypatch):
        from cadquery_furniture.project import list_saved_projects
        self._redirect(tmp_path, monkeypatch)
        save_project(build_project(_sample_payload(name="lib_one")))
        entries = list_saved_projects()
        assert len(entries) == 1
        e = entries[0]
        assert e["name"] == "lib_one"
        assert e["cabinet_count"] == 3
        assert e["total_run_width_mm"] > 0
        assert "modified" in e and "error" not in e

    def test_list_saved_projects_tolerates_corrupt_file(self, tmp_path, monkeypatch):
        from cadquery_furniture.project import list_saved_projects
        self._redirect(tmp_path, monkeypatch)
        save_project(build_project(_sample_payload(name="lib_good")))
        (tmp_path / "lib_bad.json").write_text("{not json")
        entries = list_saved_projects()
        by_name = {e["name"]: e for e in entries}
        assert "error" in by_name["lib_bad"]
        assert "error" not in by_name["lib_good"]

    def test_load_project_tool_round_trip(self, tmp_path, monkeypatch):
        from cadquery_furniture.server import _tool_load_project
        self._redirect(tmp_path, monkeypatch)
        save_project(build_project(_sample_payload(name="lib_rt")))
        data = json.loads(_run(_tool_load_project({"name": "lib_rt"}))[0].text)
        assert data["name"] == "lib_rt"
        # The returned payload is design_project-shaped: rebuilding it yields
        # the same resolved configs.
        rebuilt = build_project(data["project"])
        for (n1, c1), (n2, c2) in zip(
            load_project("lib_rt").resolved(), rebuilt.resolved()
        ):
            assert n1 == n2
            assert c1.width == c2.width
            assert c1.drawer_slide == c2.drawer_slide

    def test_batch_cutlist_merges_projects(self, tmp_path, monkeypatch):
        from cadquery_furniture.server import _tool_generate_project_cutlist
        self._redirect(tmp_path, monkeypatch)
        save_project(build_project(_sample_payload(name="lib_a")))
        save_project(build_project(_sample_payload(name="lib_b")))
        # Keep the output files in the tmp tree too.
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        data = json.loads(_run(_tool_generate_project_cutlist(
            {"project_names": ["lib_a", "lib_b"]}
        ))[0].text)
        assert data["project"] == "lib_a-lib_b"
        assert data["projects"] == ["lib_a", "lib_b"]
        assert data["cabinet_count"] == 6
        assert data["per_cabinet"][0]["name"].startswith("lib_a/")
        # Identical panels merge across projects: each project has 3 identical
        # cabinets, so sides consolidate to one row of 12 across the batch.
        sides = [p for p in data["panels_summary"] if p["name"] == "side"]
        assert sides and sides[0]["qty"] == 12
