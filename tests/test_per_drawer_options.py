"""Per-drawer options: [height, type, {options}] rows and the size-based
bottom-thickness default (boxes > 5" tall and ≥ 16" wide get 12 mm bottoms)."""

import pytest

from cadquery_furniture.cabinet import CabinetConfig, OpeningConfig, to_opening
from cadquery_furniture.drawer import (
    DEFAULT_BOTTOM_THICKNESS,
    HEAVY_BOTTOM_THICKNESS,
    DrawerConfig,
)
from cadquery_furniture.project import _opening_to_dict


class TestOpeningRowParsing:
    def test_two_element_row_unchanged(self):
        op = to_opening([300, "drawer"])
        assert op.height_mm == 300
        assert op.opening_type == "drawer"
        assert op.bottom_thickness is None

    def test_three_element_row_with_options(self):
        op = to_opening([300, "drawer", {"bottom_thickness": 12}])
        assert op.bottom_thickness == 12

    def test_none_third_element_tolerated(self):
        assert to_opening([300, "drawer", None]).bottom_thickness is None

    def test_unknown_option_key_raises(self):
        with pytest.raises(ValueError, match="Unknown per-opening option"):
            to_opening([300, "drawer", {"botom_thickness": 12}])

    def test_non_dict_third_element_raises(self):
        with pytest.raises(ValueError, match="options dict"):
            to_opening([300, "drawer", 12])

    def test_dict_row_carries_bottom_thickness(self):
        op = to_opening({"height_mm": 300, "opening_type": "drawer",
                         "bottom_thickness": 12})
        assert op.bottom_thickness == 12

    def test_slide_key_option_round_trips(self):
        op = to_opening([300, "drawer", {"slide_key": "blum_movento_769"}])
        assert op.slide_key == "blum_movento_769"
        from cadquery_furniture.project import _opening_to_dict
        d = _opening_to_dict(op)
        assert d["slide_key"] == "blum_movento_769"
        assert to_opening(d).slide_key == "blum_movento_769"

    def test_slide_key_override_reaches_bom(self):
        from cadquery_furniture.cutlist import slide_lines_for_cabinet_config
        cfg = CabinetConfig(
            width=700, height=764, depth=600,
            drawer_slide="blum_tandem_550h",
            openings=[[300, "drawer", {"slide_key": "blum_movento_769"}],
                      [232, "drawer"], [192, "drawer"]],
        )
        lines = slide_lines_for_cabinet_config(cfg)
        by_name = {l.name: l.pieces_needed for l in lines}
        assert by_name == {"Blum Movento 769": 2, "Blum Tandem 550H": 4}

    def test_unknown_slide_key_skips_that_drawer_only(self):
        from cadquery_furniture.cutlist import slide_lines_for_cabinet_config
        cfg = CabinetConfig(
            width=700, height=764, depth=600,
            drawer_slide="blum_tandem_550h",
            openings=[[300, "drawer", {"slide_key": "no_such_slide"}],
                      [232, "drawer"], [192, "drawer"]],
        )
        lines = slide_lines_for_cabinet_config(cfg)
        assert {l.name for l in lines} == {"Blum Tandem 550H"}
        assert sum(l.pieces_needed for l in lines) == 4

    def test_cabinet_config_normalizes_options_row(self):
        cfg = CabinetConfig(
            width=700, height=400, depth=550,
            openings=[[300, "drawer", {"bottom_thickness": 12}]],
        )
        assert cfg.openings[0].bottom_thickness == 12

    def test_project_dict_round_trip(self):
        op = OpeningConfig(height_mm=300, opening_type="drawer",
                           bottom_thickness=12)
        d = _opening_to_dict(op)
        assert d["bottom_thickness"] == 12
        assert to_opening(d).bottom_thickness == 12

    def test_project_dict_omits_unset_override(self):
        d = _opening_to_dict(OpeningConfig(height_mm=300, opening_type="drawer"))
        assert "bottom_thickness" not in d


class TestBottomThicknessDefault:
    def _cfg(self, opening_width, opening_height, **kw):
        return DrawerConfig(
            opening_width=opening_width,
            opening_height=opening_height,
            opening_depth=550,
            **kw,
        )

    def test_heavy_box_defaults_to_half_inch(self):
        # 609.6 opening → 567.6 box (≥ 406.4); 273 opening → 229 box (> 127)
        cfg = self._cfg(609.6, 273, slide_key="blum_movento_769")
        assert cfg.bottom_thickness == HEAVY_BOTTOM_THICKNESS

    def test_narrow_box_keeps_quarter_inch(self):
        cfg = self._cfg(254, 273, slide_key="blum_movento_769")
        assert cfg.bottom_thickness == DEFAULT_BOTTOM_THICKNESS

    def test_shallow_box_keeps_quarter_inch(self):
        # 104 opening → 76 box, well under the 127 mm height threshold
        cfg = self._cfg(609.6, 104, slide_key="blum_movento_769")
        assert cfg.bottom_thickness == DEFAULT_BOTTOM_THICKNESS

    def test_five_inch_box_is_not_heavy(self):
        # Threshold is strict: a box of exactly 127 mm (5") stays thin.
        cfg = self._cfg(609.6, 127 + 27, slide_key="blum_movento_769")
        assert cfg.box_height == 127.0
        assert cfg.bottom_thickness == DEFAULT_BOTTOM_THICKNESS

    def test_explicit_override_wins_both_ways(self):
        assert self._cfg(609.6, 273, slide_key="blum_movento_769",
                         bottom_thickness=6).bottom_thickness == 6
        assert self._cfg(254, 104, bottom_thickness=12).bottom_thickness == 12

    def test_bad_slide_key_falls_back_thin(self):
        # Construction must not become the failure point for a bad slide key.
        cfg = self._cfg(609.6, 273, slide_key="no_such_slide")
        assert cfg.bottom_thickness == DEFAULT_BOTTOM_THICKNESS
        with pytest.raises(KeyError):
            _ = cfg.box_width
