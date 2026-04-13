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
    def test_merges_identical_panels(self):
        panels = [
            CutlistPanel(name="side_L", length=720, width=500, thickness=18, grain_direction="length"),
            CutlistPanel(name="side_R", length=720, width=500, thickness=18, grain_direction="length"),
        ]
        result = consolidate_bom(panels)
        assert len(result) == 1
        assert result[0].quantity == 2

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
