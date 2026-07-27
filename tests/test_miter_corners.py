"""Tests for mitered exterior corners — solver, panel dims, evaluator."""

import pytest

from cadquery_furniture.cabinet import CabinetConfig, CarcassJoinery
from cadquery_furniture.evaluation import check_miter_corners
from cadquery_furniture.joinery import (
    get_domino_size,
    miter_mortise_placement,
)
from cadquery_furniture.server import _raw_panels_for_cabinet


def _cfg(**kw) -> CabinetConfig:
    return CabinetConfig(width=1219.2, height=663.6, depth=457, **kw)


class TestMiterMortiseSolver:
    def test_5x30_fits_18mm_stock(self):
        p = miter_mortise_placement(get_domino_size("5x30"), 18.0)
        # Face width t·√2; feasible window biases toward the long point.
        assert p.face_width == pytest.approx(25.5, abs=0.1)
        assert p.from_heel > p.face_width / 2
        assert p.from_heel + p.from_long_point == pytest.approx(
            p.face_width, abs=0.2)
        assert p.inner_wall >= 2.0
        assert p.depth == 15

    def test_5x30_rejects_12mm_stock(self):
        with pytest.raises(ValueError, match="does not fit a 45° miter"):
            miter_mortise_placement(get_domino_size("5x30"), 12.0)

    def test_minimum_thickness_boundary(self):
        # min t = wall + mortise_width·cos45 + depth·cos45 ≈ 16.5 for 5x30.
        size = get_domino_size("5x30")
        with pytest.raises(ValueError):
            miter_mortise_placement(size, 16.0)
        p = miter_mortise_placement(size, 17.0)
        assert p.inner_wall >= 2.0

    def test_4x17_fits_thinner_stock(self):
        p = miter_mortise_placement(get_domino_size("4x17"), 15.0)
        assert p.inner_wall >= 2.0


class TestMiterPanelDims:
    def test_butt_default_unchanged(self):
        c, _, _, _ = _raw_panels_for_cabinet(_cfg(), None)
        top = next(p for p in c if p.name == "top")
        assert top.length == pytest.approx(1219.2 - 36)
        assert "bevel" not in top.notes

    def test_miter_top_bottom_full_width_long_point(self):
        c, _, _, _ = _raw_panels_for_cabinet(
            _cfg(carcass_corner_style="miter"), None)
        top = next(p for p in c if p.name == "top")
        bottom = next(p for p in c if p.name == "bottom")
        side = next(p for p in c if p.name == "side")
        assert top.length == pytest.approx(1219.2)
        assert bottom.length == pytest.approx(1219.2)
        assert "45° bevels both ends" in top.notes
        assert side.length == pytest.approx(663.6)   # unchanged number
        assert "45° bevels top+bottom ends" in side.notes

    def test_miter_leaves_shelves_and_depth_alone(self):
        cfg = _cfg(carcass_corner_style="miter",
                   fixed_shelf_positions=[300])
        c, _, _, _ = _raw_panels_for_cabinet(cfg, None)
        shelf = next(p for p in c if p.name == "shelf_1")
        assert shelf.length == pytest.approx(1219.2 - 36)
        assert "bevel" not in shelf.notes


class TestMiterCheck:
    def test_butt_silent(self):
        assert check_miter_corners(_cfg()) == []

    def test_unknown_style_errors(self):
        issues = check_miter_corners(_cfg(carcass_corner_style="lock"))
        assert any(i.severity.value == "error" for i in issues)

    def test_valid_miter_silent(self):
        assert check_miter_corners(_cfg(carcass_corner_style="miter")) == []

    def test_non_tenon_joinery_errors(self):
        issues = check_miter_corners(_cfg(
            carcass_corner_style="miter",
            carcass_joinery=CarcassJoinery.DADO_RABBET))
        assert any("floating-tenon" in i.message for i in issues)

    def test_mismatched_thickness_errors(self):
        issues = check_miter_corners(_cfg(
            carcass_corner_style="miter", top_thickness=12.0))
        assert any("equal mating thicknesses" in i.message for i in issues)

    def test_thin_stock_errors(self):
        issues = check_miter_corners(_cfg(
            carcass_corner_style="miter", side_thickness=12.0,
            top_thickness=12.0, bottom_thickness=12.0))
        assert any("does not fit a 45° miter" in i.message for i in issues)


class TestMiterToken:
    def test_shared_token_merges(self):
        from cadquery_furniture.project import _merge, shared_from_dict
        shared = shared_from_dict({"carcass_corner_style": "miter"})
        merged = _merge(CabinetConfig(width=800, height=700, depth=457),
                        shared, frozenset())
        assert merged.carcass_corner_style == "miter"
