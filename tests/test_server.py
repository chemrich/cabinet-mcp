"""
Tests for the MCP server tool handlers and port-management utilities.

Tool handler tests call the async handler functions directly — no stdio or
HTTP transport needed, so the suite stays fast and dependency-free.

Port management tests use real sockets to exercise the auto-increment logic.
"""

import asyncio
import json
import socket
import tempfile
from pathlib import Path

import pytest

# Import the internal handler functions directly (they're module-level)
from cadquery_furniture.server import (
    DEFAULT_PORT,
    PORT_FILE,
    _tool_list_hardware,
    _tool_list_joinery,
    _tool_design_cabinet,
    _tool_evaluate_cabinet,
    _tool_design_door,
    _tool_design_drawer,
    _tool_generate_cutlist,
    _tool_compare_joinery,
    clear_port_file,
    find_free_port,
    write_port_file,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def run(coro):
    """Run a coroutine synchronously for testing."""
    return asyncio.get_event_loop().run_until_complete(coro)


def parse(result) -> dict:
    """Parse a TextContent list into the underlying JSON dict."""
    assert len(result) == 1
    text = result[0].text
    assert not text.startswith("ERROR:"), f"Tool returned error: {text}"
    return json.loads(text)


def is_error(result) -> bool:
    assert len(result) == 1
    return result[0].text.startswith("ERROR:")


# ─── list_hardware ─────────────────────────────────────────────────────────────

class TestListHardware:
    def test_all_returns_slides_and_hinges(self):
        data = parse(run(_tool_list_hardware({"category": "all"})))
        assert "slides" in data
        assert "hinges" in data

    def test_slides_only(self):
        data = parse(run(_tool_list_hardware({"category": "slides"})))
        assert "slides" in data
        assert "hinges" not in data

    def test_hinges_only(self):
        data = parse(run(_tool_list_hardware({"category": "hinges"})))
        assert "hinges" in data
        assert "slides" not in data

    def test_slides_have_required_fields(self):
        data = parse(run(_tool_list_hardware({"category": "slides"})))
        for key, slide in data["slides"].items():
            assert "name" in slide, key
            assert "available_lengths_mm" in slide, key
            assert "nominal_side_clearance_mm" in slide, key
            assert "max_load_kg" in slide, key

    def test_hinges_have_required_fields(self):
        data = parse(run(_tool_list_hardware({"category": "hinges"})))
        for key, hinge in data["hinges"].items():
            assert "overlay_type" in hinge, key
            assert "overlay_mm" in hinge, key
            assert "cup_diameter_mm" in hinge, key
            assert "soft_close" in hinge, key

    def test_blum_clip_top_full_overlay_present(self):
        data = parse(run(_tool_list_hardware({"category": "hinges"})))
        assert "blum_clip_top_110_full" in data["hinges"]
        h = data["hinges"]["blum_clip_top_110_full"]
        assert h["overlay_type"] == "full"
        assert h["overlay_mm"] == 16.0

    def test_default_category_all(self):
        data = parse(run(_tool_list_hardware({})))
        assert "slides" in data
        assert "hinges" in data


# ─── list_joinery_options ──────────────────────────────────────────────────────

class TestListJoineryOptions:
    def test_returns_three_sections(self):
        data = parse(run(_tool_list_joinery({})))
        assert "drawer_joinery_styles" in data
        assert "carcass_joinery_methods" in data
        assert "domino_sizes" in data

    def test_drawer_styles_complete(self):
        data = parse(run(_tool_list_joinery({})))
        styles = data["drawer_joinery_styles"]
        for s in ("butt", "qqq", "half_lap", "drawer_lock"):
            assert s in styles, s

    def test_carcass_methods_complete(self):
        data = parse(run(_tool_list_joinery({})))
        methods = data["carcass_joinery_methods"]
        for m in ("dado_rabbet", "floating_tenon", "pocket_screw", "biscuit", "dowel"):
            assert m in methods, m

    def test_domino_sizes_have_correct_fields(self):
        data = parse(run(_tool_list_joinery({})))
        sizes = data["domino_sizes"]
        assert "8x40" in sizes
        d = sizes["8x40"]
        assert "tenon_length_mm" in d
        assert "tenon_thickness_mm" in d
        assert "mortise_depth_per_side_mm" in d
        assert "machine" in d
        assert d["machine"] == "DF 500"

    def test_mortise_larger_than_tenon(self):
        data = parse(run(_tool_list_joinery({})))
        for key, d in data["domino_sizes"].items():
            assert d["mortise_length_mm"] >= d["tenon_length_mm"], key
            assert d["mortise_width_mm"] >= d["tenon_thickness_mm"], key


# ─── design_cabinet ────────────────────────────────────────────────────────────

class TestDesignCabinet:
    def _base(self, **kwargs):
        args = {"width": 600, "height": 720, "depth": 550, **kwargs}
        return parse(run(_tool_design_cabinet(args)))

    def test_exterior_dimensions_reflected(self):
        data = self._base()
        assert data["exterior"]["width_mm"] == 600
        assert data["exterior"]["height_mm"] == 720
        assert data["exterior"]["depth_mm"] == 550

    def test_interior_narrower_than_exterior(self):
        data = self._base()
        assert data["interior"]["width_mm"] < 600
        assert data["interior"]["depth_mm"] < 550

    def test_default_joinery_dado_rabbet(self):
        data = self._base()
        assert data["joinery"] == "dado_rabbet"

    def test_floating_tenon_joinery(self):
        data = self._base(carcass_joinery="floating_tenon")
        assert data["joinery"] == "floating_tenon"

    def test_panels_include_sides_bottom_back(self):
        data = self._base()
        panels = data["panels"]
        assert "side_panel" in panels
        assert panels["side_panel"]["qty"] == 2
        assert "bottom_panel" in panels
        assert "back_panel" in panels

    def test_drawer_config_reflected(self):
        data = self._base(drawer_config=[[150, "drawer"], [300, "open"]])
        stack = data["opening_stack"]
        assert len(stack) == 2
        assert stack[0]["type"] == "drawer"
        assert stack[0]["height_mm"] == 150

    def test_empty_drawer_config(self):
        data = self._base()
        assert data["opening_stack"] == []

    def test_adj_shelf_holes_false_by_default(self):
        data = self._base()
        assert data["adj_shelf_holes"] is False

    def test_adj_shelf_holes_true(self):
        data = self._base(adj_shelf_holes=True)
        assert data["adj_shelf_holes"] is True

    def test_door_hinge_default(self):
        data = self._base()
        assert data["door_hinge"] == "blum_clip_top_110_full"

    def test_custom_door_hinge(self):
        data = self._base(door_hinge="blum_clip_top_blumotion_110_full")
        assert data["door_hinge"] == "blum_clip_top_blumotion_110_full"


# ─── evaluate_cabinet ─────────────────────────────────────────────────────────

class TestEvaluateCabinet:
    def _eval(self, **kwargs):
        args = {"width": 600, "height": 720, "depth": 550, **kwargs}
        return parse(run(_tool_evaluate_cabinet(args)))

    def test_clean_cabinet_passes(self):
        data = self._eval()
        assert data["summary"]["pass"] is True
        assert data["summary"]["errors"] == 0

    def test_summary_fields_present(self):
        data = self._eval()
        s = data["summary"]
        assert "errors" in s
        assert "warnings" in s
        assert "info" in s
        assert "pass" in s

    def test_issues_list_present(self):
        data = self._eval()
        assert "issues" in data
        assert isinstance(data["issues"], list)

    def test_issue_has_required_fields(self):
        # Force an issue: drawer height taller than cabinet
        data = self._eval(drawer_config=[[800, "drawer"]])
        if data["issues"]:
            issue = data["issues"][0]
            assert "severity" in issue
            assert "check" in issue
            assert "message" in issue

    def test_floating_tenon_clean_cabinet(self):
        data = self._eval(carcass_joinery="floating_tenon")
        assert data["summary"]["errors"] == 0

    def test_pocket_screw_clean_cabinet(self):
        data = self._eval(carcass_joinery="pocket_screw")
        assert data["summary"]["errors"] == 0

    def test_with_door_configs(self):
        data = self._eval(door_configs=[{
            "opening_width": 560,
            "opening_height": 700,
            "num_doors": 1,
            "hinge_key": "blum_clip_top_110_full",
        }])
        assert "summary" in data


# ─── design_door ──────────────────────────────────────────────────────────────

class TestDesignDoor:
    def _door(self, **kwargs):
        args = {"opening_width": 600, "opening_height": 700, **kwargs}
        return parse(run(_tool_design_door(args)))

    def test_returns_door_dimensions(self):
        data = self._door()
        assert "door_width_mm" in data
        assert "door_height_mm" in data
        assert "hinges_per_door" in data

    def test_full_overlay_adds_overlay(self):
        data = self._door(hinge_key="blum_clip_top_110_full")
        # Full overlay adds 16mm each side → door_width > opening_width
        assert data["door_width_mm"] > 600

    def test_inset_door_narrower_than_opening(self):
        data = self._door(hinge_key="blum_clip_top_110_inset")
        assert data["door_width_mm"] < 600

    def test_door_pair(self):
        data = self._door(num_doors=2)
        assert data["num_doors"] == 2
        assert data["total_hinges"] >= 4  # at least 2 per door

    def test_single_door_hinge_count(self):
        data = self._door()
        assert data["hinges_per_door"] >= 2

    def test_hinge_positions_count_matches_hinge_count(self):
        data = self._door()
        assert len(data["hinge_positions_z_mm"]) == data["hinges_per_door"]

    def test_overlay_type_reported(self):
        data = self._door(hinge_key="blum_clip_top_110_half")
        assert data["overlay_type"] == "half"

    def test_soft_close_hinge(self):
        data = self._door(hinge_key="blum_clip_top_blumotion_110_full")
        assert data["hinge"]["soft_close"] is True

    def test_gap_fields_present(self):
        data = self._door()
        assert "gaps" in data
        assert "top_mm" in data["gaps"]
        assert "bottom_mm" in data["gaps"]

    def test_cup_boring_distance(self):
        data = self._door()
        assert data["hinge"]["cup_boring_distance_mm"] == 22.5


# ─── design_drawer ────────────────────────────────────────────────────────────

class TestDesignDrawer:
    def _drawer(self, **kwargs):
        args = {
            "opening_width": 560,
            "opening_height": 200,
            "opening_depth": 500,
            **kwargs,
        }
        return parse(run(_tool_design_drawer(args)))

    def test_returns_box_dimensions(self):
        data = self._drawer()
        assert "box_width_mm" in data
        assert "box_height_mm" in data
        assert "box_depth_mm" in data

    def test_box_narrower_than_opening(self):
        data = self._drawer()
        assert data["box_width_mm"] < 560

    def test_butt_joinery_no_cuts(self):
        data = self._drawer(joinery_style="butt")
        assert data["joinery"]["style"] == "butt"
        # butt joint: no dado depths reported
        assert "side_dado_depth_x_mm" not in data["joinery"]

    def test_qqq_joinery_has_cuts(self):
        data = self._drawer(joinery_style="qqq", side_thickness=12.0, front_back_thickness=12.0)
        j = data["joinery"]
        assert j["style"] == "qqq"
        assert "side_dado_depth_x_mm" in j
        # QQQ: all cut dims = side_thickness / 2 = 6.0
        assert j["side_dado_depth_x_mm"] == pytest.approx(6.0)

    def test_half_lap_joinery(self):
        data = self._drawer(joinery_style="half_lap")
        assert data["joinery"]["style"] == "half_lap"

    def test_drawer_lock_joinery_has_lock_step(self):
        data = self._drawer(joinery_style="drawer_lock")
        j = data["joinery"]
        assert "lock_step_depth_x_mm" in j
        assert j["requires_router_bit"] is True

    def test_slide_info_present(self):
        data = self._drawer()
        assert "slide" in data
        assert "name" in data["slide"]
        assert "nominal_side_clearance_mm" in data["slide"]

    def test_custom_slide(self):
        data = self._drawer(slide_key="blum_tandem_plus_563h")
        assert "blum" in data["slide"]["name"].lower()


# ─── generate_cutlist ─────────────────────────────────────────────────────────

class TestGenerateCutlist:
    def _cutlist(self, **kwargs):
        args = {"width": 600, "height": 720, "depth": 550, **kwargs}
        return parse(run(_tool_generate_cutlist(args)))

    def test_returns_panel_count(self):
        data = self._cutlist()
        assert "panel_count" in data
        assert data["panel_count"] > 0

    def test_returns_panels_summary(self):
        data = self._cutlist()
        assert "panels_summary" in data
        assert len(data["panels_summary"]) == data["panel_count"]

    def test_panel_has_required_fields(self):
        data = self._cutlist()
        for p in data["panels_summary"]:
            assert "name" in p
            assert "length_mm" in p
            assert "width_mm" in p
            assert "thickness_mm" in p
            assert "qty" in p

    def test_json_format(self):
        data = self._cutlist(format="json")
        assert "cutlist_json" in data
        assert "cutlist_csv" not in data

    def test_csv_format(self):
        data = self._cutlist(format="csv")
        assert "cutlist_csv" in data
        assert "cutlist_json" not in data

    def test_both_format(self):
        data = self._cutlist(format="both")
        assert "cutlist_json" in data
        assert "cutlist_csv" in data

    def test_csv_has_header(self):
        data = self._cutlist(format="csv")
        csv_text = data["cutlist_csv"]
        assert "name" in csv_text.lower() or "length" in csv_text.lower()

    def test_json_has_panels_array(self):
        data = self._cutlist(format="json")
        cj = data["cutlist_json"]
        assert "panels" in cj

    def test_custom_sheet_size(self):
        # Should not error with custom sheet dimensions
        data = self._cutlist(sheet_length=3050, sheet_width=1525)
        assert data["panel_count"] > 0


# ─── compare_joinery ──────────────────────────────────────────────────────────

class TestCompareJoinery:
    def _compare(self, **kwargs):
        return parse(run(_tool_compare_joinery(kwargs)))

    def test_returns_all_four_styles(self):
        data = self._compare()
        styles = data["styles"]
        for s in ("butt", "qqq", "half_lap", "drawer_lock"):
            assert s in styles, s

    def test_default_thickness(self):
        data = self._compare()
        assert data["side_thickness_mm"] == 12.0

    def test_custom_thickness(self):
        data = self._compare(side_thickness=18.0, front_back_thickness=18.0)
        assert data["side_thickness_mm"] == 18.0
        # QQQ cuts should all be 9.0
        qqq = data["styles"]["qqq"]
        assert qqq["side_dado_depth_x_mm"] == pytest.approx(9.0)

    def test_drawer_lock_has_router_bit_flag(self):
        data = self._compare()
        assert data["styles"]["drawer_lock"]["requires_router_bit"] is True

    def test_butt_has_no_cuts(self):
        data = self._compare()
        butt = data["styles"]["butt"]
        assert butt["side_dado_depth_x_mm"] == 0.0

    def test_qqq_note_present(self):
        data = self._compare()
        assert "note" in data["styles"]["qqq"]

    def test_thickness_fields_present(self):
        data = self._compare()
        assert "side_thickness_mm" in data
        assert "front_back_thickness_mm" in data

# ─── Port management ──────────────────────────────────────────────────────────

class TestFindFreePort:
    """Tests for the auto-increment port-finding logic."""

    def test_returns_int(self):
        port = find_free_port(start=19800)
        assert isinstance(port, int)

    def test_port_in_requested_range(self):
        start = 19810
        port = find_free_port(start=start, max_attempts=20)
        assert start <= port < start + 20

    def test_skips_occupied_port(self):
        # Bind a socket on the start port, then verify find_free_port returns
        # a higher one.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            occupied.bind(("", 19820))
            found = find_free_port(start=19820, max_attempts=10)
        assert found > 19820

    def test_skips_multiple_occupied_ports(self):
        # Block three consecutive ports; expect the fourth to be returned.
        start = 19830
        sockets = []
        try:
            for offset in range(3):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("", start + offset))
                sockets.append(s)
            found = find_free_port(start=start, max_attempts=10)
            assert found >= start + 3
        finally:
            for s in sockets:
                s.close()

    def test_raises_when_range_exhausted(self):
        # Block a range of ports and demand the server cannot escape it.
        start = 19850
        count = 5
        sockets = []
        try:
            for offset in range(count):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("", start + offset))
                sockets.append(s)
            with pytest.raises(RuntimeError, match="No free port found"):
                find_free_port(start=start, max_attempts=count)
        finally:
            for s in sockets:
                s.close()

    def test_default_port_constant_is_int(self):
        assert isinstance(DEFAULT_PORT, int)
        assert DEFAULT_PORT > 1024  # not a privileged port


class TestPortFile:
    """Tests for the port-file write/clear helpers."""

    def test_write_creates_file(self, tmp_path):
        p = tmp_path / "cabinet-mcp.port"
        write_port_file(3749, path=p)
        assert p.exists()

    def test_write_contains_port_number(self, tmp_path):
        p = tmp_path / "cabinet-mcp.port"
        write_port_file(4242, path=p)
        assert p.read_text() == "4242"

    def test_write_overwrites_previous(self, tmp_path):
        p = tmp_path / "cabinet-mcp.port"
        write_port_file(1111, path=p)
        write_port_file(2222, path=p)
        assert p.read_text() == "2222"

    def test_clear_removes_file(self, tmp_path):
        p = tmp_path / "cabinet-mcp.port"
        p.write_text("3749")
        clear_port_file(path=p)
        assert not p.exists()

    def test_clear_is_idempotent(self, tmp_path):
        p = tmp_path / "cabinet-mcp.port"
        # File does not exist — clear should not raise.
        clear_port_file(path=p)
        clear_port_file(path=p)

    def test_roundtrip(self, tmp_path):
        p = tmp_path / "cabinet-mcp.port"
        port = find_free_port(start=19900)
        write_port_file(port, path=p)
        assert int(p.read_text()) == port
        clear_port_file(path=p)
        assert not p.exists()

    def test_default_port_file_path_is_path(self):
        assert isinstance(PORT_FILE, Path)
