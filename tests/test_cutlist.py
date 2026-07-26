"""Tests for cutlist BOM extraction and formatting."""

import json
import pytest
from cadquery_furniture.cutlist import (
    CutlistPanel,
    SheetStock,
    SHEET_4x8_3_4,
    consolidate_bom,
    extract_bom_parametric,
    to_json,
    to_csv,
)
from cadquery_furniture.cabinet import PartInfo


class TestConsolidateBom:
    def test_merges_same_name_panels(self):
        panels = [
            CutlistPanel(name="side", length=720, width=500, thickness=18, grain_direction="length"),
            CutlistPanel(name="side", length=720, width=500, thickness=18, grain_direction="length"),
        ]
        result = consolidate_bom(panels)
        assert len(result) == 1
        assert result[0].quantity == 2

    def test_keeps_differently_named_identical_panels_separate(self):
        panels = [
            CutlistPanel(name="side_L", length=720, width=500, thickness=18, grain_direction="length"),
            CutlistPanel(name="side_R", length=720, width=500, thickness=18, grain_direction="length"),
        ]
        result = consolidate_bom(panels)
        assert len(result) == 2

    def test_keeps_different_panels_separate(self):
        panels = [
            CutlistPanel(name="side", length=720, width=500, thickness=18),
            CutlistPanel(name="bottom", length=564, width=500, thickness=18),
        ]
        result = consolidate_bom(panels)
        assert len(result) == 2

    def test_different_thickness_not_merged(self):
        panels = [
            CutlistPanel(name="side", length=720, width=500, thickness=18),
            CutlistPanel(name="side_thin", length=720, width=500, thickness=12),
        ]
        result = consolidate_bom(panels)
        assert len(result) == 2

    def test_preserves_original_notes(self):
        """BUG 5 fix: original notes (e.g. material callouts) must survive consolidation."""
        panels = [
            CutlistPanel(name="back", length=720, width=576, thickness=6, notes="1/4 inch plywood"),
        ]
        result = consolidate_bom(panels)
        assert len(result) == 1
        assert "1/4 inch plywood" in result[0].notes


class TestJsonExport:
    def test_basic_export(self):
        panels = [
            CutlistPanel(name="side", length=720, width=500, thickness=18, quantity=2),
        ]
        output = to_json(panels, kerf=3.2)
        data = json.loads(output)
        assert data["cut_width"] == 3.2
        assert len(data["panels"]) == 1
        assert data["panels"][0]["length"] == 720
        assert data["panels"][0]["quantity"] == 2

    def test_grain_rotation(self):
        panels = [
            CutlistPanel(name="panel_with_grain", length=720, width=500, thickness=18, grain_direction="length"),
            CutlistPanel(name="panel_no_grain", length=720, width=500, thickness=18, grain_direction=""),
        ]
        output = to_json(panels)
        data = json.loads(output)
        assert data["panels"][0]["can_rotate"] is False
        assert data["panels"][1]["can_rotate"] is True

    def test_with_stock(self):
        panels = [CutlistPanel(name="p", length=100, width=100, thickness=18)]
        output = to_json(panels, stock=[SHEET_4x8_3_4])
        data = json.loads(output)
        assert "stock" in data
        assert data["stock"][0]["length"] == 2440


class TestCsvExport:
    def test_csv_has_header(self):
        panels = [CutlistPanel(name="test", length=100, width=50, thickness=18)]
        output = to_csv(panels)
        lines = output.strip().split("\n")
        assert "Name" in lines[0]
        assert len(lines) == 2  # header + 1 row

    def test_csv_values(self):
        panels = [CutlistPanel(name="shelf", length=564, width=500, thickness=18, quantity=3)]
        output = to_csv(panels)
        assert "shelf" in output
        assert "564" in output


class TestExtractBomParametric:
    def test_fallback_returns_one_entry_per_part(self):
        """BUG 1 fix: parametric fallback must return an entry for every part."""
        parts = [
            PartInfo(name="left_side", shape=None, material_thickness=18, grain_direction="length"),
            PartInfo(name="right_side", shape=None, material_thickness=18, grain_direction="length"),
            PartInfo(name="bottom", shape=None, material_thickness=18, grain_direction="width"),
        ]
        result = extract_bom_parametric(parts)
        assert len(result) == 3

    def test_fallback_notes_indicate_unavailable(self):
        """Fallback panels should flag that dimensions were not computed."""
        parts = [PartInfo(name="p", shape=None, material_thickness=18, grain_direction="length")]
        result = extract_bom_parametric(parts)
        assert len(result) == 1
        assert "not computed" in result[0].notes or "not available" in result[0].notes

    def test_fallback_preserves_thickness(self):
        """Fallback panels should carry the correct material thickness."""
        parts = [PartInfo(name="back", shape=None, material_thickness=6, grain_direction="width")]
        result = extract_bom_parametric(parts)
        assert result[0].thickness == 6

    def test_fallback_zero_dimensions(self):
        """Length and width are 0 in fallback mode (no geometry available)."""
        parts = [PartInfo(name="side", shape=None, material_thickness=18, grain_direction="length")]
        result = extract_bom_parametric(parts)
        assert result[0].length == 0
        assert result[0].width == 0


class TestLiteModeImport:
    def test_cutlist_imports_without_reportlab(self):
        # Regression (caught by CI's first-ever run): _SheetDrawingFlowable
        # subclassed _Flowable at module level, so importing cutlist.py
        # crashed with NameError in a true lite install (no reportlab).
        import subprocess, sys
        code = (
            "import sys; sys.modules['reportlab'] = None; "
            "import cadquery_furniture.cutlist as cl; "
            "assert not cl._REPORTLAB_AVAILABLE; "
            "assert not hasattr(cl, '_SheetDrawingFlowable')"
        )
        subprocess.run([sys.executable, "-c", code], check=True)


class TestImperialAnnotations:
    """Cut sheets carry metric AND fractional imperial (to 1/32) — Charlie's
    print request, Jul 2026."""

    def test_inch_frac_values(self):
        from cadquery_furniture.cutlist import _inch_frac
        assert _inch_frac(1219.2) == "48"          # exact inches drop fraction
        assert _inch_frac(457) == "18"             # rounds to whole
        assert _inch_frac(324) == "12 3/4"         # reduced from 24/32
        assert _inch_frac(533) == "20 31/32"
        assert _inch_frac(15.875) == "5/8"         # no whole part
        assert _inch_frac(663.6) == "26 1/8"

    def test_thickness_nominal_labels(self):
        from cadquery_furniture.cutlist import _thickness_imperial
        assert _thickness_imperial(18) == '3/4"'   # trade name, not 23/32
        assert _thickness_imperial(12) == '1/2"'
        assert _thickness_imperial(6) == '1/4"'

    def test_graphics_metric_only_with_part_ids(self):
        # Charlie's split (Jul 2026): imperial lives in the TABLES; the
        # cut-sheet graphics stay metric-only and carry the row IDs.
        from cadquery_furniture.cutlist import (
            CutlistPanel, SheetStock, optimize_cutlist, assign_part_ids,
            generate_sheet_layout_html)
        panels = [CutlistPanel(name="side", length=663.6, width=457,
                               thickness=18, quantity=2)]
        assign_part_ids(panels)
        assert panels[0].part_id == "S1"   # no project letter when solo
        opt = optimize_cutlist(panels, stock_sheet=SheetStock(
            name="s", length=2440, width=1220, thickness=18), kerf=3.2)
        html = generate_sheet_layout_html(
            [("18mm", panels, opt)], cabinet_name="imp_test", kerf=3.2)
        assert "26 1/8" not in html        # imperial removed from graphics
        assert "S1 · side" in html         # ID labels each placement
        assert "663.6" in html or "664×457" in html or "664" in html

    def test_part_ids_batch_lettering(self):
        from cadquery_furniture.cutlist import CutlistPanel, assign_part_ids
        ps = [CutlistPanel(name="side", length=100, width=50, thickness=18,
                           source="dining"),
              CutlistPanel(name="drawer_box_side", length=100, width=50,
                           thickness=12, source="dining"),
              CutlistPanel(name="drawer_box_side", length=90, width=50,
                           thickness=12, source="kid1"),
              CutlistPanel(name="drawer_box_front", length=90, width=50,
                           thickness=12, source="kid1")]
        letters = assign_part_ids(ps)
        assert letters == {"dining": "A", "kid1": "B"}
        assert [x.part_id for x in ps] == ["A-S1", "A-DB1", "B-DB1", "B-DB2"]

    def test_per_sheet_project_key_lists_only_present_projects(self):
        from cadquery_furniture.cutlist import (
            CutlistPanel, SheetStock, optimize_cutlist, assign_part_ids,
            generate_sheet_layout_html)
        stock = SheetStock(name="s", length=2440, width=1220, thickness=18)
        both = [CutlistPanel(name="side", length=600, width=400, thickness=18,
                             source="alpha"),
                CutlistPanel(name="side", length=500, width=400, thickness=18,
                             source="beta")]
        solo = [CutlistPanel(name="top", length=600, width=400, thickness=18,
                             source="beta")]
        assign_part_ids(both + solo)
        g1 = optimize_cutlist(both, stock_sheet=stock, kerf=3.2)
        g2 = optimize_cutlist(solo, stock_sheet=stock, kerf=3.2)
        html = generate_sheet_layout_html(
            [("g1", both, g1), ("g2", solo, g2)],
            cabinet_name="key_test", kerf=3.2)
        keys = [seg.split("</div>")[0] for seg in html.split('<div class="sheet-key">')[1:]]
        assert len(keys) == 2
        assert "alpha" in keys[0] and "beta" in keys[0]      # both on sheet 1
        assert "beta" in keys[1] and "alpha" not in keys[1]  # only beta on g2
        assert "A · alpha" in keys[0] and "B · beta" in keys[0]

    def test_global_sheet_numbers_across_groups(self):
        # Numbers run 1..N across ALL groups (never reset per material) so
        # Charlie can pencil them on the physical sheet edges.
        from cadquery_furniture.cutlist import (
            CutlistPanel, SheetStock, optimize_cutlist, assign_part_ids,
            generate_sheet_layout_html)
        stock = SheetStock(name="s", length=2440, width=1220, thickness=18)
        # Two panels too big to share a sheet -> group 1 uses 2 sheets.
        g1p = [CutlistPanel(name="side", length=2200, width=1100, thickness=18,
                            quantity=2)]
        g2p = [CutlistPanel(name="top", length=600, width=400, thickness=18)]
        assign_part_ids(g1p + g2p)
        g1 = optimize_cutlist(g1p, stock_sheet=stock, kerf=3.2)
        g2 = optimize_cutlist(g2p, stock_sheet=stock, kerf=3.2)
        assert g1.sheets_used == 2
        html = generate_sheet_layout_html(
            [("g1", g1p, g1), ("g2", g2p, g2)],
            cabinet_name="num_test", kerf=3.2)
        assert "Sheet #1 " in html and "Sheet #2 " in html
        assert "Sheet #3 " in html          # group 2 continues, not resets
        assert html.count("Sheet #") == 3
        assert "(#1–#2)" in html and "(#3–#3)" in html or "(#3)" in html
