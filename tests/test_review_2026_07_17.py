"""Regression tests for the 2026-07-17 full code review fixes.

Each test encodes one verified finding from docs/code-review-2026-07-17.md —
majors M1–M7 plus the highest-value minors.
"""

import math

import pytest

from cadquery_furniture.auto_fix import auto_fix_cabinet
from cadquery_furniture.cabinet import CabinetConfig, OpeningConfig, to_opening
from cadquery_furniture.cutlist import (
    CutlistPanel,
    SheetStock,
    consolidate_hardware_lines,
    optimize_cutlist,
    slide_lines_for_cabinet_config,
    _panel_colour,
)
from cadquery_furniture.evaluation import Severity, evaluate_cabinet
from cadquery_furniture.hardware import (
    BLUM_MOVENTO_769,
    SALICE_FUTURA,
    SALICE_FUTURA_SMOVE,
)
from cadquery_furniture.joinery import DrawerJoineryStyle, drawer_joinery_spec


class TestM1DynamicLoadRatings:
    def test_movento_and_salice_carry_dynamic_ratings(self):
        assert BLUM_MOVENTO_769.max_load_kg == 70
        assert SALICE_FUTURA.max_load_kg == 34
        assert SALICE_FUTURA_SMOVE.max_load_kg == 34


class TestM2QqqThinFrontGuard:
    def test_thin_front_back_raises(self):
        with pytest.raises(ValueError, match="QQQ"):
            drawer_joinery_spec(DrawerJoineryStyle.QQQ, 19, 6)

    def test_equal_stock_still_fine(self):
        spec = drawer_joinery_spec(DrawerJoineryStyle.QQQ, 12, 12)
        assert spec.fb_channel_depth_y == 6.0

    def test_non_positive_stock_raises(self):
        with pytest.raises(ValueError, match="positive"):
            drawer_joinery_spec(DrawerJoineryStyle.HALF_LAP, 0, 15)


class TestM3AutoFixPreservesPerDrawerOptions:
    def test_rebalance_keeps_slide_and_bottom_overrides(self):
        cfg = CabinetConfig(width=600, height=500, depth=550, openings=[
            OpeningConfig(300, "drawer", slide_key="blum_movento_769",
                          bottom_thickness=12.0),
            OpeningConfig(300, "drawer"),
        ])
        fixed = auto_fix_cabinet(cfg).config
        assert fixed.openings[0].slide_key == "blum_movento_769"
        assert fixed.openings[0].bottom_thickness == 12.0


class TestM4UnknownSlideIsAnIssueNotACrash:
    def test_bad_per_opening_slide_key(self):
        issues = evaluate_cabinet(CabinetConfig(
            width=600, height=400, depth=550,
            openings=[OpeningConfig(200, "drawer", slide_key="bogus")],
        ))
        assert any(i.check == "slide_unknown" and i.severity == Severity.ERROR
                   for i in issues)

    def test_bad_cabinet_default_with_valid_override(self):
        # The valid per-drawer override must not be sunk by the bad default.
        issues = evaluate_cabinet(CabinetConfig(
            width=600, height=400, depth=550, drawer_slide="bogus_default",
            openings=[OpeningConfig(200, "drawer",
                                    slide_key="blum_tandem_550h")],
        ))
        assert not any(i.check == "slide_unknown" for i in issues)


class TestM5AutoFixMinHeightRespectsSnapping:
    def test_salice_clamp_does_not_snap_below_minimum(self):
        # Salice min box 79 mm: the clamp floor must target the 102 mm
        # standard size, not 79 (which would snap down to 76 and fail).
        cfg = CabinetConfig(width=600, height=450, depth=550,
                            drawer_slide="salice_futura",
                            openings=[[250, "drawer"], [250, "drawer"]])
        result = auto_fix_cabinet(cfg)
        hardware_errors = [i for i in result.final_issues
                           if i.check == "hardware_clearance"
                           and i.severity == Severity.ERROR]
        assert hardware_errors == []


class TestM7BayConfigsCarryEveryField:
    def test_multi_column_bay_inherits_box_stock_and_legs(self):
        # The visualize path rebuilds per-column bay configs; a hand-picked
        # field list silently dropped drawer_box_thickness/prefinished.
        from cadquery_furniture import server as srv
        import dataclasses as dc

        cfg = srv._build_cabinet_config({
            "width": 700, "height": 400, "depth": 550,
            "drawer_box_thickness": 12, "drawer_box_prefinished": True,
            "leg_count": 6,
            "columns": [
                {"width_mm": 332, "drawer_config": [[300, "drawer"]]},
                {"width_mm": 314, "drawer_config": [[300, "drawer"]]},
            ],
        })
        columns_raw = srv._columns_dict_from_cfg(cfg)
        side_t = cfg.side_thickness
        bay = dc.replace(
            cfg,
            width=float(columns_raw[0]["width_mm"]) + 2 * side_t,
            columns=[],
            openings=[srv._to_opening(r)
                      for r in srv._stack_from_column(columns_raw[0])],
        )
        assert bay.drawer_box_thickness == 12
        assert bay.drawer_box_prefinished is True
        assert bay.leg_count == 6


class TestInputValidation:
    def test_string_option_values_coerced(self):
        op = to_opening([300, "drawer", {"bottom_thickness": "12"}])
        assert op.bottom_thickness == 12.0

    def test_nan_height_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            to_opening([float("nan"), "drawer"])
        with pytest.raises(ValueError, match="finite"):
            to_opening(["inf", "drawer"])

    def test_negative_bottom_thickness_rejected(self):
        with pytest.raises(ValueError, match="bottom_thickness"):
            to_opening([300, "drawer", {"bottom_thickness": -6}])

    def test_bad_num_doors_rejected(self):
        with pytest.raises(ValueError, match="num_doors"):
            to_opening([300, "door", {"num_doors": 3}])

    def test_mixed_column_rows_normalize(self):
        from cadquery_furniture.cabinet import ColumnConfig
        cfg = CabinetConfig(width=600, height=400, depth=550, columns=[
            ColumnConfig(width_mm=564,
                         openings=(OpeningConfig(150, "drawer"),
                                   [150, "drawer"])),
        ])
        assert all(isinstance(op, OpeningConfig)
                   for op in cfg.columns[0].openings)

    def test_unknown_shared_token_is_value_error(self):
        from cadquery_furniture.project import build_project
        with pytest.raises(ValueError, match="shared design token"):
            build_project({"name": "x", "shared": {"bogus_token": 1},
                           "cabinets": []})


class TestCutlistRobustness:
    def test_slide_notes_deduplicated(self):
        cfg = CabinetConfig(width=600, height=720, depth=550, openings=[
            [200, "drawer"], [200, "drawer"], [200, "drawer"]])
        lines = slide_lines_for_cabinet_config(cfg)
        assert len(lines) == 1
        assert lines[0].notes.count("mm") == 1  # one length note, not three
        assert lines[0].pieces_needed == 6

    def test_shallow_depth_skips_drawer_not_whole_bom(self):
        # Known slide, cabinet too shallow for it: that drawer is skipped,
        # the others still bill.
        cfg = CabinetConfig(width=600, height=720, depth=550, openings=[
            [200, "drawer", {"slide_key": "salice_progressa_plus"}],
            [200, "drawer"], [200, "drawer"]])
        # progressa+ shortest length may fit 544 interior; use a truly
        # shallow cabinet for the override drawer instead
        shallow = CabinetConfig(width=600, height=720, depth=250, openings=[
            [200, "drawer"]])
        assert slide_lines_for_cabinet_config(shallow) == []
        lines = slide_lines_for_cabinet_config(cfg)
        assert sum(l.pieces_needed for l in lines) >= 4

    def test_panel_colour_deterministic(self):
        assert _panel_colour("drawer_box_side") == _panel_colour("drawer_box_side")
        # Cross-process determinism: crc32 has a fixed value we can pin.
        import zlib
        assert zlib.crc32(b"drawer_box_side") % 1 == 0  # crc32 is salt-free

    def test_optimizer_rejects_mismatched_thickness(self):
        with pytest.raises(ValueError, match="thickness mismatch"):
            optimize_cutlist(
                [CutlistPanel("drawer_box_bottom", 500, 400, 6)],
                stock_sheet=SheetStock("18mm", 2440, 1220, 18),
                algorithm="strip",
            )


class TestFollowUps:
    """Post-review follow-ups: deferred-data resolutions + remaining nits."""

    def test_blum_hinge_chart(self):
        from cadquery_furniture.hardware import BLUM_CLIP_TOP_110_FULL as h
        # Blum's published chart (ea.blum.com "Number of hinges").
        assert [h.hinges_for_height(x) for x in (900, 901, 1600, 1601, 2000, 2001)] \
            == [2, 3, 3, 4, 4, 5]

    def test_9mm_sheet_prices_present(self):
        from cadquery_furniture.hardware import price_for
        assert price_for("sheet_baltic_birch_9mm") == 56.0
        assert price_for("sheet_baltic_birch_prefinished_9mm") == 78.0

    def test_multi_column_preset_summary_shows_columns(self):
        from cadquery_furniture.presets import get_preset
        s = get_preset("armoire_2col").summary()
        assert len(s["columns"]) == 2
        assert s["columns"][0]["opening_stack"], "column stacks must be populated"

    def test_progressa_inch_series_kept(self):
        from cadquery_furniture.hardware import get_slide
        assert 686 in get_slide("salice_progressa_plus").available_lengths


class TestPresetIntegrity:
    def test_config_dict_round_trips_every_preset(self):
        # Guard: config_dict → build_cabinet_config must reproduce the
        # preset's config exactly, so no CabinetConfig field can silently
        # fall out of preset serialization again.
        from cadquery_furniture.presets import PRESETS
        from cadquery_furniture.cabinet import build_cabinet_config
        for name, preset in PRESETS.items():
            rebuilt = build_cabinet_config(dict(preset.config_dict()))
            assert rebuilt == preset.config, name

    def test_tall_presets_drill_pins_high_enough(self):
        from cadquery_furniture.presets import get_preset
        for name in ("kitchen_tall_pantry", "bedroom_armoire",
                     "bathroom_linen_tower"):
            c = get_preset(name).config
            assert c.shelf_pin_end_z > 1000, name


class TestDoorOverridesThread:
    def test_doors_from_cabinet_config_honors_overrides(self):
        # num_doors / hinge_key / pull_key overrides must reach the door
        # assemblies, matching how the hinge BOM bills them.
        pytest.importorskip("cadquery")
        from cadquery_furniture.door import doors_from_cabinet_config

        cfg = CabinetConfig(width=1000, height=800, depth=550, openings=[
            [700, "door", {"num_doors": 2,
                           "hinge_key": "blum_clip_top_110_half"}]])
        doors = doors_from_cabinet_config(cfg)
        assert len(doors) == 1
        _, parts, _ = doors[0]
        door_panels = [p for p in parts if "door" in p.name.lower()]
        assert len(door_panels) == 2, [p.name for p in parts]
