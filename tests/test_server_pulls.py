"""
MCP-server tests for pull-related behaviour.

Covers:
    * list_hardware pulls category (+ brand / mount_style filters)
    * design_pulls end-to-end (flat stack, multi-column, door-pair counting,
      style-mismatch warning, unknown SKU, pack-quantity BOM math)
    * pull block surfaced on design_drawer / design_door

Tests call the async handler functions directly — no MCP transport.
"""

import asyncio
import json

import pytest

from cadquery_furniture.server import (
    _tool_list_hardware,
    _tool_design_pulls,
    _tool_design_drawer,
    _tool_design_door,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def parse(result) -> dict:
    assert len(result) == 1
    text = result[0].text
    assert not text.startswith("ERROR:"), f"Tool returned error: {text}"
    return json.loads(text)


def is_error(result) -> bool:
    assert len(result) == 1
    return result[0].text.startswith("ERROR:")


# ─── list_hardware: pulls ─────────────────────────────────────────────────────

class TestListHardwarePulls:
    def test_pulls_key_present_when_all(self):
        data = parse(run(_tool_list_hardware({"category": "all"})))
        assert "pulls" in data
        assert data["pulls_count"] == len(data["pulls"])

    def test_pulls_only(self):
        data = parse(run(_tool_list_hardware({"category": "pulls"})))
        assert "pulls" in data
        assert "slides" not in data
        assert "hinges" not in data
        assert data["pulls_count"] > 0

    def test_pulls_have_required_fields(self):
        data = parse(run(_tool_list_hardware({"category": "pulls"})))
        for key, p in data["pulls"].items():
            for field in (
                "name", "brand", "model_number", "style", "mount_style",
                "pack_quantity", "cc_mm", "length_mm", "projection_mm",
            ):
                assert field in p, f"{key} missing {field}"

    def test_brand_filter_case_insensitive(self):
        data = parse(run(_tool_list_hardware(
            {"category": "pulls", "brand": "ikea"})))
        assert data["pulls_count"] > 0
        for key, p in data["pulls"].items():
            assert "ikea" in p["brand"].lower(), key

    def test_mount_style_filter(self):
        data = parse(run(_tool_list_hardware(
            {"category": "pulls", "mount_style": "edge"})))
        assert data["pulls_count"] > 0
        for key, p in data["pulls"].items():
            assert p["mount_style"] == "edge", key

    def test_brand_and_mount_filter_combined(self):
        data = parse(run(_tool_list_hardware(
            {"category": "pulls", "brand": "ikea", "mount_style": "surface"})))
        for key, p in data["pulls"].items():
            assert "ikea" in p["brand"].lower()
            assert p["mount_style"] == "surface"

    def test_unknown_mount_style_returns_empty(self):
        # Enum-wise "jimmy" won't match anything — an unknown filter should
        # simply yield zero hits rather than fall back to "unfiltered".
        data = parse(run(_tool_list_hardware(
            {"category": "pulls", "mount_style": "jimmy"})))
        assert data["pulls_count"] == 0


# ─── design_pulls ─────────────────────────────────────────────────────────────

class TestDesignPullsFlatStack:
    def test_drawer_only_stack(self):
        data = parse(run(_tool_design_pulls({
            "width": 900, "height": 720, "depth": 550,
            "drawer_config": [[180, "drawer"], [180, "drawer"]],
            "drawer_pull": "topknobs-hb-128",
        })))
        assert len(data["drawer_slots"]) == 2
        assert data["door_slots"] == []
        # 884 mm face > 600 mm threshold → dual pulls per drawer → 4 pieces
        assert data["bom_totals"]["pieces_needed"] == 4
        assert data["bom_totals"]["line_count"] == 1
        for slot in data["drawer_slots"]:
            assert slot["pull_key"] == "topknobs-hb-128"
            assert slot["count"] == 2
            assert slot["issues"] == []

    def test_door_pair_counts_two_pulls(self):
        data = parse(run(_tool_design_pulls({
            "width": 900, "height": 720, "depth": 550,
            "drawer_config": [[720, "door_pair"]],
            "door_pull": "topknobs-hb-128",
        })))
        assert len(data["door_slots"]) == 1
        slot = data["door_slots"][0]
        assert slot["num_doors"] == 2
        assert slot["total_pulls"] == 2 * slot["pulls_per_leaf"]
        assert data["bom_totals"]["pieces_needed"] == slot["total_pulls"]

    def test_shelf_and_open_slots_skipped(self):
        data = parse(run(_tool_design_pulls({
            "width": 900, "height": 720, "depth": 550,
            "drawer_config": [
                [180, "drawer"],
                [180, "shelf"],
                [180, "open"],
                [180, "drawer"],
            ],
            "drawer_pull": "topknobs-hb-128",
        })))
        # Only the two drawer slots produce placements; shelf/open are skipped.
        assert len(data["drawer_slots"]) == 2
        assert [s["slot_index"] for s in data["drawer_slots"]] == [0, 3]

    def test_door_without_pull_produces_no_slot(self):
        data = parse(run(_tool_design_pulls({
            "width": 900, "height": 720, "depth": 550,
            "drawer_config": [[180, "drawer"], [540, "door"]],
            "drawer_pull": "topknobs-hb-128",
            # no door_pull
        })))
        assert len(data["drawer_slots"]) == 1
        assert data["door_slots"] == []

    def test_no_pulls_at_all_returns_empty_bom(self):
        data = parse(run(_tool_design_pulls({
            "width": 900, "height": 720, "depth": 550,
            "drawer_config": [[180, "drawer"], [540, "door"]],
        })))
        assert data["drawer_slots"] == []
        assert data["door_slots"] == []
        assert data["bom_totals"]["pieces_needed"] == 0
        assert data["hardware_bom"] == []

    def test_vertical_policy_propagates(self):
        data = parse(run(_tool_design_pulls({
            "width": 900, "height": 720, "depth": 550,
            "drawer_config": [[180, "drawer"]],
            "drawer_pull": "topknobs-hb-128",
            "drawer_pull_vertical": "upper_third",
        })))
        assert data["drawer_pull_vertical"] == "upper_third"
        assert data["drawer_slots"][0]["vertical_policy"] == "upper_third"


class TestDesignPullsColumns:
    def test_columns_walk_emits_column_index(self):
        data = parse(run(_tool_design_pulls({
            "width": 1200, "height": 720, "depth": 550,
            "columns": [
                {"width_mm": 591, "drawer_config": [[300, "drawer"], [300, "drawer"]]},
                {"width_mm": 591, "drawer_config": [[600, "door"]]},
            ],
            "drawer_pull": "topknobs-hb-128",
            "door_pull":   "topknobs-hb-128",
        })))
        assert len(data["drawer_slots"]) == 2
        assert len(data["door_slots"]) == 1
        assert all("column_index" in s for s in data["drawer_slots"])
        assert data["drawer_slots"][0]["column_index"] == 0
        assert data["door_slots"][0]["column_index"] == 1

    def test_columns_override_drawer_config(self):
        # Flat drawer_config is ignored when columns are supplied.
        data = parse(run(_tool_design_pulls({
            "width": 1200, "height": 720, "depth": 550,
            "drawer_config": [[999, "drawer"]],   # would produce 1 drawer if used
            "columns": [
                {"width_mm": 591, "drawer_config": [[720, "door"]]},
                {"width_mm": 591, "drawer_config": [[720, "door"]]},
            ],
            "door_pull": "topknobs-hb-128",
        })))
        assert data["drawer_slots"] == []
        assert len(data["door_slots"]) == 2


class TestDesignPullsIssues:
    def test_style_mismatch_warning(self):
        data = parse(run(_tool_design_pulls({
            "width": 900, "height": 720, "depth": 550,
            "drawer_config": [[180, "drawer"], [540, "door"]],
            "drawer_pull": "topknobs-hb-128",   # Transitional
            "door_pull":   "rockler-wnl-160",   # Contemporary
        })))
        checks = [i["check"] for i in data["cabinet_issues"]]
        assert "pull_style_mismatch" in checks

    def test_matching_pulls_no_mismatch(self):
        data = parse(run(_tool_design_pulls({
            "width": 900, "height": 720, "depth": 550,
            "drawer_config": [[180, "drawer"], [540, "door"]],
            "drawer_pull": "topknobs-hb-128",
            "door_pull":   "topknobs-hb-128",
        })))
        assert data["cabinet_issues"] == []

    def test_unknown_sku_surfaces_slot_error(self):
        data = parse(run(_tool_design_pulls({
            "width": 900, "height": 720, "depth": 550,
            "drawer_config": [[180, "drawer"]],
            "drawer_pull": "nope-not-real",
        })))
        slot = data["drawer_slots"][0]
        assert any(i["check"] == "pull_unknown" for i in slot["issues"])
        # No BOM entry when the SKU can't be resolved.
        assert data["hardware_bom"] == []


class TestDesignPullsBomMath:
    def test_pack_quantity_two_rounds_up(self):
        # IKEA Bagganäs ships in 2-packs; 5 needed → 3 packs → 6 ordered → 1 leftover.
        data = parse(run(_tool_design_pulls({
            "width": 500, "height": 720, "depth": 550,  # 464 mm face → single pull
            "drawer_config": [
                [150, "drawer"], [150, "drawer"], [150, "drawer"],
                [150, "drawer"], [150, "drawer"],
            ],
            "drawer_pull": "ikea-bagganas-black-128",
        })))
        assert data["bom_totals"]["pieces_needed"] == 5
        line = data["hardware_bom"][0]
        assert line["sku"] == "ikea-bagganas-black-128"
        assert line["pack_quantity"] == 2
        assert line["packs_to_order"] == 3
        assert line["pieces_ordered"] == 6
        assert line["leftover"] == 1

    def test_bom_consolidates_across_slot_types(self):
        # Same SKU on drawer + door → one consolidated line.
        data = parse(run(_tool_design_pulls({
            "width": 900, "height": 720, "depth": 550,
            "drawer_config": [[180, "drawer"], [540, "door"]],
            "drawer_pull": "topknobs-hb-128",
            "door_pull":   "topknobs-hb-128",
        })))
        assert len(data["hardware_bom"]) == 1
        assert data["hardware_bom"][0]["sku"] == "topknobs-hb-128"


# ─── pull block on design_drawer / design_door ────────────────────────────────

class TestDesignDrawerPullBlock:
    def test_no_pull_omits_block(self):
        data = parse(run(_tool_design_drawer({
            "opening_width": 400, "opening_height": 180, "opening_depth": 500,
        })))
        assert "pull" not in data

    def test_pull_block_populated(self):
        data = parse(run(_tool_design_drawer({
            "opening_width": 400, "opening_height": 180, "opening_depth": 500,
            "pull_key": "topknobs-hb-128",
        })))
        assert "pull" in data
        pull = data["pull"]
        assert pull["key"] == "topknobs-hb-128"
        assert pull["count"] >= 1
        assert pull["count"] == len(pull["placements"])
        assert pull["face_width_mm"] > 0
        assert pull["face_height_mm"] > 0
        assert pull["bom"] is not None
        assert pull["bom"]["pieces_needed"] == pull["count"]

    def test_wide_drawer_gets_dual_pulls(self):
        # 884 mm face > 600 mm threshold → 2 pulls.
        data = parse(run(_tool_design_drawer({
            "opening_width": 900, "opening_height": 180, "opening_depth": 500,
            "pull_key": "topknobs-hb-128",
        })))
        assert data["pull"]["count"] == 2

    def test_vertical_policy_override(self):
        data = parse(run(_tool_design_drawer({
            "opening_width": 400, "opening_height": 180, "opening_depth": 500,
            "pull_key": "topknobs-hb-128",
            "pull_vertical": "upper_third",
        })))
        assert data["pull"]["vertical_policy"] == "upper_third"


class TestDesignDoorPullBlock:
    def test_no_pull_omits_block(self):
        data = parse(run(_tool_design_door({
            "opening_width": 400, "opening_height": 600,
        })))
        assert "pull" not in data

    def test_pull_block_populated_single_door(self):
        data = parse(run(_tool_design_door({
            "opening_width": 400, "opening_height": 600,
            "pull_key": "topknobs-hb-128",
        })))
        pull = data["pull"]
        assert pull["key"] == "topknobs-hb-128"
        assert pull["pulls_per_leaf"] >= 1
        assert pull["total_pulls"] == pull["pulls_per_leaf"]
        assert pull["bom"]["pieces_needed"] == pull["total_pulls"]

    def test_door_pair_doubles_total(self):
        data = parse(run(_tool_design_door({
            "opening_width": 800, "opening_height": 600,
            "num_doors": 2,
            "pull_key": "topknobs-hb-128",
        })))
        pull = data["pull"]
        assert pull["total_pulls"] == 2 * pull["pulls_per_leaf"]
