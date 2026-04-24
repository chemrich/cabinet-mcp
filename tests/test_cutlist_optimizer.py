"""Tests for the strip-cutting sheet-goods optimiser in cutlist.py."""

import pytest
from cadquery_furniture.cutlist import (
    CutlistPanel,
    OptimizationResult,
    Placement,
    SheetStock,
    SHEET_4x8_3_4,
    SHEET_4x8_1_2,
    optimize_cutlist,
    _RECTPACK_AVAILABLE,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


def panel(name: str, length: float, width: float, qty: int = 1, grain: str = "length") -> CutlistPanel:
    return CutlistPanel(name=name, length=length, width=width, thickness=18, quantity=qty, grain_direction=grain)


SMALL_SHEET = SheetStock(name="test_600x600", length=600, width=600, thickness=18)


# ─── Result structure ─────────────────────────────────────────────────────────


class TestOptimizationResultStructure:
    def test_returns_optimization_result(self):
        result = optimize_cutlist([panel("side", 400, 200)], stock_sheet=SMALL_SHEET)
        assert isinstance(result, OptimizationResult)

    def test_placements_are_placement_objects(self):
        result = optimize_cutlist([panel("side", 400, 200)], stock_sheet=SMALL_SHEET)
        assert all(isinstance(p, Placement) for p in result.placements)

    def test_stock_sheet_preserved(self):
        result = optimize_cutlist([panel("side", 400, 200)], stock_sheet=SMALL_SHEET)
        assert result.stock_sheet is SMALL_SHEET

    def test_is_complete_true_when_all_placed(self):
        result = optimize_cutlist([panel("side", 200, 100)], stock_sheet=SMALL_SHEET)
        assert result.is_complete is True

    def test_is_complete_false_when_oversized(self):
        result = optimize_cutlist([panel("giant", 700, 700)], stock_sheet=SMALL_SHEET)
        assert result.is_complete is False


# ─── Single-sheet fit ─────────────────────────────────────────────────────────


class TestSingleSheetFit:
    def test_two_panels_one_sheet(self):
        panels = [panel("left", 400, 200), panel("right", 400, 200)]
        result = optimize_cutlist(panels, stock_sheet=SMALL_SHEET)
        assert result.sheets_used == 1

    def test_one_piece_per_panel_placed(self):
        panels = [panel("left", 400, 200), panel("right", 400, 200)]
        result = optimize_cutlist(panels, stock_sheet=SMALL_SHEET)
        assert len(result.placements) == 2

    def test_panel_names_in_placements(self):
        panels = [panel("left", 400, 200), panel("right", 400, 200)]
        result = optimize_cutlist(panels, stock_sheet=SMALL_SHEET)
        names = {p.panel_name for p in result.placements}
        assert "left" in names
        assert "right" in names

    def test_waste_pct_is_float_in_range(self):
        result = optimize_cutlist([panel("p", 400, 200)], stock_sheet=SMALL_SHEET)
        assert 0.0 <= result.waste_pct <= 100.0

    def test_placement_coords_non_negative(self):
        result = optimize_cutlist([panel("p", 400, 200)], stock_sheet=SMALL_SHEET)
        for p in result.placements:
            assert p.x >= 0
            assert p.y >= 0

    def test_placement_sheet_index_zero(self):
        result = optimize_cutlist([panel("p", 400, 200)], stock_sheet=SMALL_SHEET)
        assert all(p.sheet_index == 0 for p in result.placements)

    def test_default_stock_sheet_is_4x8(self):
        # A small panel with no explicit sheet should land on the 4×8 default.
        result = optimize_cutlist([panel("p", 400, 200)])
        assert result.stock_sheet is SHEET_4x8_3_4


# ─── Quantity expansion ───────────────────────────────────────────────────────


class TestQuantityExpansion:
    def test_quantity_expands_to_multiple_placements(self):
        result = optimize_cutlist([panel("side", 200, 100, qty=4)], stock_sheet=SMALL_SHEET)
        assert len(result.placements) == 4

    def test_all_pieces_have_same_panel_name(self):
        result = optimize_cutlist([panel("side", 200, 100, qty=3)], stock_sheet=SMALL_SHEET)
        assert all(p.panel_name == "side" for p in result.placements)

    def test_mixed_quantities(self):
        panels = [panel("a", 200, 100, qty=2), panel("b", 150, 80, qty=3)]
        result = optimize_cutlist(panels, stock_sheet=SMALL_SHEET)
        assert len(result.placements) == 5


# ─── Multi-sheet layouts ──────────────────────────────────────────────────────


class TestMultipleSheets:
    def test_many_panels_require_multiple_sheets(self):
        # 8 × (500×500) panels can't all fit on one 600×600 sheet.
        panels = [panel(f"p{i}", 500, 500) for i in range(8)]
        result = optimize_cutlist(panels, stock_sheet=SMALL_SHEET)
        assert result.sheets_used > 1

    def test_sheet_indices_are_sequential(self):
        panels = [panel(f"p{i}", 500, 500) for i in range(4)]
        result = optimize_cutlist(panels, stock_sheet=SMALL_SHEET)
        indices = sorted({p.sheet_index for p in result.placements})
        assert indices == list(range(result.sheets_used))

    def test_all_placed_across_sheets(self):
        panels = [panel(f"p{i}", 500, 500) for i in range(4)]
        result = optimize_cutlist(panels, stock_sheet=SMALL_SHEET)
        assert result.is_complete

    def test_realistic_kitchen_base_cabinet(self):
        # 600 mm wide base: 2 sides, top, bottom, back (simplified — no CadQuery)
        panels = [
            panel("side",   720, 560, qty=2),
            panel("top",    564, 560),
            panel("bottom", 564, 560),
            panel("back",   600, 720, grain=""),   # no grain — plywood back
            panel("shelf",  564, 540, qty=2),
        ]
        result = optimize_cutlist(panels, stock_sheet=SHEET_4x8_3_4)
        assert result.is_complete
        assert result.sheets_used >= 1
        assert result.waste_pct < 80  # sanity: shouldn't be nearly all waste


# ─── Oversized panels ─────────────────────────────────────────────────────────


class TestOversizedPanels:
    def test_oversized_panel_is_unplaced(self):
        big = panel("wardrobe_side", 800, 700)  # too big for SMALL_SHEET (600×600)
        result = optimize_cutlist([big], stock_sheet=SMALL_SHEET)
        assert "wardrobe_side" in result.unplaced

    def test_oversized_does_not_consume_a_sheet(self):
        big = panel("wardrobe_side", 800, 700)
        result = optimize_cutlist([big], stock_sheet=SMALL_SHEET)
        assert result.sheets_used == 0

    def test_normal_panels_placed_alongside_oversized(self):
        panels = [
            panel("giant", 800, 700),    # oversized — unplaced
            panel("small", 200, 100),    # fits fine
        ]
        result = optimize_cutlist(panels, stock_sheet=SMALL_SHEET)
        assert "giant" in result.unplaced
        assert any(p.panel_name == "small" for p in result.placements)

    def test_oversized_name_appears_once(self):
        # qty=3 of an oversized panel: name should appear only once in unplaced
        big = panel("giant", 800, 700, qty=3)
        result = optimize_cutlist([big], stock_sheet=SMALL_SHEET)
        assert result.unplaced.count("giant") == 1


# ─── Kerf accounting ─────────────────────────────────────────────────────────


class TestKerfAccounting:
    def test_custom_kerf_accepted(self):
        result = optimize_cutlist(
            [panel("p", 400, 200)], stock_sheet=SMALL_SHEET, kerf=4.0
        )
        assert result.sheets_used >= 1  # just must not raise

    def test_zero_kerf_accepted(self):
        result = optimize_cutlist(
            [panel("p", 400, 200)], stock_sheet=SMALL_SHEET, kerf=0.0
        )
        assert result.is_complete

    def test_kerf_reduces_effective_sheet_area(self):
        # A panel that fits within the sheet minus kerf (with a 1 mm margin to
        # avoid floating-point boundary issues) should be placed successfully.
        # A panel equal to the full nominal sheet size cannot fit once kerf is added.
        kerf = 3.2
        just_fits = panel("ok", SMALL_SHEET.length - kerf * 2 - 1, SMALL_SHEET.width - kerf * 2 - 1)
        result_ok = optimize_cutlist([just_fits], stock_sheet=SMALL_SHEET, kerf=kerf)
        assert result_ok.is_complete

        too_big = panel("nope", SMALL_SHEET.length, SMALL_SHEET.width)
        result_nope = optimize_cutlist([too_big], stock_sheet=SMALL_SHEET, kerf=kerf)
        assert not result_nope.is_complete


# ─── Waste calculation ────────────────────────────────────────────────────────


class TestWasteCalculation:
    def test_waste_zero_for_empty_panels(self):
        result = optimize_cutlist([], stock_sheet=SMALL_SHEET)
        assert result.waste_pct == 0.0
        assert result.sheets_used == 0

    def test_waste_lower_when_panels_fill_sheet(self):
        # Two panels that together nearly fill a 600×600 sheet
        almost_full = [panel("a", 580, 290), panel("b", 580, 290)]
        result = optimize_cutlist(almost_full, stock_sheet=SMALL_SHEET)
        # These two panels cover ~(580×290)*2 = 336,400 mm² of a 360,000 mm² sheet → ~7% waste
        assert result.waste_pct < 30

    def test_waste_higher_for_small_panels_on_large_sheet(self):
        tiny = [panel("chip", 50, 30)]
        result = optimize_cutlist(tiny, stock_sheet=SHEET_4x8_3_4)
        assert result.waste_pct > 90  # one tiny piece on a 4×8 is mostly waste


# ─── No rectpack ─────────────────────────────────────────────────────────────


class TestNoRectpack:
    """Strip cutting is pure Python — rectpack is not required."""

    def test_works_without_rectpack(self, monkeypatch):
        import cadquery_furniture.cutlist as cl
        monkeypatch.setattr(cl, "_RECTPACK_AVAILABLE", False)
        # Should succeed: strip layout has no rectpack dependency.
        result = cl.optimize_cutlist([panel("p", 200, 100)])
        assert result.is_complete
