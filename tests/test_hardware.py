"""Tests for hardware specifications."""

import pytest
from cadquery_furniture.hardware import (
    BLUM_TANDEM_550H,
    BLUM_TANDEM_PLUS_563H,
    BLUM_MOVENTO_760H,
    BLUM_MOVENTO_769,
    ACCURIDE_3832,
    SALICE_FUTURA,
    SALICE_FUTURA_SMOVE,
    SALICE_PROGRESSA_PLUS,
    SALICE_PROGRESSA_PLUS_SMOVE,
    get_slide,
    get_hinge,
)


class TestBlumTandem550H:
    def test_slide_length_for_depth(self):
        # 500mm cabinet depth should yield 450mm or 500mm slide
        length = BLUM_TANDEM_550H.slide_length_for_depth(500)
        assert length <= 500
        assert length >= 450

    def test_slide_length_too_short(self):
        with pytest.raises(ValueError, match="No .* slide fits"):
            BLUM_TANDEM_550H.slide_length_for_depth(100)

    def test_drawer_box_width(self):
        opening = 564  # 600mm cabinet - 2×18mm sides
        box_width = BLUM_TANDEM_550H.drawer_box_width(opening)
        expected = opening - (21.0 * 2)  # 522.0mm — Blum formula: opening − 42mm
        assert abs(box_width - expected) < 0.1

    def test_validate_good_dims(self):
        issues = BLUM_TANDEM_550H.validate_drawer_dims(
            drawer_width=522.0,  # opening(564) − 42mm = 522mm (Blum nominal)
            drawer_height=120,
            drawer_depth=450,
            opening_width=564,
        )
        assert len(issues) == 0

    def test_validate_too_wide(self):
        issues = BLUM_TANDEM_550H.validate_drawer_dims(
            drawer_width=560,  # way too wide
            drawer_height=120,
            drawer_depth=450,
            opening_width=564,
        )
        assert any("clearance" in i.lower() for i in issues)

    def test_validate_too_short(self):
        issues = BLUM_TANDEM_550H.validate_drawer_dims(
            drawer_width=538,
            drawer_height=50,  # below 68mm minimum
            drawer_depth=450,
            opening_width=564,
        )
        assert any("height" in i.lower() for i in issues)


class TestBlumTandemPlus563H:
    def test_lengths_are_inch_based(self):
        """563H uses inch-series lengths (229=9", 533=21")."""
        assert 229 in BLUM_TANDEM_PLUS_563H.available_lengths
        assert 533 in BLUM_TANDEM_PLUS_563H.available_lengths

    def test_higher_capacity_than_550h(self):
        assert BLUM_TANDEM_PLUS_563H.max_load_kg > BLUM_TANDEM_550H.max_load_kg

    def test_slide_length_for_depth(self):
        length = BLUM_TANDEM_PLUS_563H.slide_length_for_depth(500)
        assert length <= 500

    def test_validate_good_dims(self):
        issues = BLUM_TANDEM_PLUS_563H.validate_drawer_dims(
            drawer_width=522.0, drawer_height=120, drawer_depth=450, opening_width=564
        )
        assert len(issues) == 0


class TestBlumMovento769:
    def test_heavy_duty_capacity(self):
        # 2026-07-17 review: max_load_kg is the DYNAMIC rating (70 kg); the
        # old assertion encoded the 77 kg static figure.
        assert BLUM_MOVENTO_769.max_load_kg == 70

    def test_longer_lengths_than_760h(self):
        assert max(BLUM_MOVENTO_769.available_lengths) > max(BLUM_MOVENTO_760H.available_lengths)

    def test_slide_length_for_deep_cabinet(self):
        length = BLUM_MOVENTO_769.slide_length_for_depth(650)
        assert length >= 600


class TestSaliceFutura:
    def test_lookup_by_key(self):
        slide = get_slide("salice_futura")
        assert slide.manufacturer == "Salice"

    def test_min_drawer_height_higher_than_blum(self):
        """Futura has a taller slide body than Blum Tandem."""
        assert SALICE_FUTURA.min_drawer_height > BLUM_TANDEM_550H.min_drawer_height

    def test_validate_good_dims(self):
        issues = SALICE_FUTURA.validate_drawer_dims(
            drawer_width=522.0, drawer_height=100, drawer_depth=380, opening_width=564
        )
        assert len(issues) == 0

    def test_validate_too_short(self):
        issues = SALICE_FUTURA.validate_drawer_dims(
            drawer_width=538.6, drawer_height=50, drawer_depth=380, opening_width=564
        )
        assert any("height" in i.lower() for i in issues)

    def test_smove_same_footprint(self):
        """Smove variant must have the same lengths and clearances as standard Futura."""
        assert SALICE_FUTURA_SMOVE.available_lengths == SALICE_FUTURA.available_lengths
        assert SALICE_FUTURA_SMOVE.nominal_side_clearance == SALICE_FUTURA.nominal_side_clearance


class TestSaliceProgressaPlus:
    def test_lookup_by_key(self):
        slide = get_slide("salice_progressa_plus")
        assert slide.manufacturer == "Salice"

    def test_widest_length_range(self):
        """Progressa+ goes up to 762 mm (30") — longest of any undermount in the DB."""
        assert max(SALICE_PROGRESSA_PLUS.available_lengths) == 762

    def test_short_length_available(self):
        assert 229 in SALICE_PROGRESSA_PLUS.available_lengths

    def test_higher_capacity_than_futura(self):
        assert SALICE_PROGRESSA_PLUS.max_load_kg > SALICE_FUTURA.max_load_kg

    def test_slide_length_for_deep_cabinet(self):
        length = SALICE_PROGRESSA_PLUS.slide_length_for_depth(700)
        assert length >= 650

    def test_smove_variant_same_lengths(self):
        assert (SALICE_PROGRESSA_PLUS_SMOVE.available_lengths ==
                SALICE_PROGRESSA_PLUS.available_lengths)


class TestLookup:
    def test_get_slide_valid(self):
        slide = get_slide("blum_tandem_550h")
        assert slide.name == "Blum Tandem 550H"

    def test_all_slides_registered(self):
        """Every slide constant must be reachable via get_slide."""
        keys = [
            "blum_tandem_550h", "blum_tandem_plus_563h",
            "blum_movento_760h", "blum_movento_769",
            "accuride_3832",
            "salice_futura", "salice_futura_smove",
            "salice_progressa_plus", "salice_progressa_plus_smove",
        ]
        for key in keys:
            slide = get_slide(key)
            assert slide.name  # non-empty name

    def test_get_slide_invalid(self):
        with pytest.raises(KeyError):
            get_slide("nonexistent_slide")

    def test_get_hinge_valid(self):
        hinge = get_hinge("blum_clip_top_110")
        assert hinge.opening_angle == 110

    def test_get_hinge_170(self):
        hinge = get_hinge("blum_clip_top_170")
        assert hinge.opening_angle == 170

    def test_get_hinge_invalid(self):
        with pytest.raises(KeyError):
            get_hinge("nonexistent_hinge")


class TestPartNumberPricing:
    """price_for() must resolve the SKU forms the hardware-BOM helpers emit:
    manufacturer part numbers for hinges/legs, catalog keys as fallback."""

    def test_every_priced_hinge_part_number_is_priced(self):
        from cadquery_furniture.hardware import HINGES, PRICE_LIST, price_for
        for key, spec in HINGES.items():
            if key in PRICE_LIST and spec.part_number:
                assert price_for(spec.part_number) == PRICE_LIST[key], (
                    f"{key}: part number {spec.part_number} not priced"
                )

    def test_170_hinge_part_number_priced(self):
        # Regression: PRICE_LIST used a dead '71T6580' alias while the spec
        # carries part_number '71B3750', pricing 170-degree hinges at $0.
        from cadquery_furniture.hardware import get_hinge, price_for
        assert price_for(get_hinge("blum_clip_top_170_full").part_number) == 12.00

    def test_every_priced_leg_part_number_is_priced(self):
        # Regression: leg BOM lines use spec.part_number as the SKU, but
        # PRICE_LIST only listed catalog keys — all Richelieu legs priced $0.
        from cadquery_furniture.hardware import LEGS, PRICE_LIST, price_for
        for key, spec in LEGS.items():
            if key in PRICE_LIST and spec.part_number:
                assert price_for(spec.part_number) == PRICE_LIST[key], (
                    f"{key}: part number {spec.part_number} not priced"
                )

    def test_leg_bom_line_prices_nonzero(self):
        from cadquery_furniture.cabinet import CabinetConfig
        from cadquery_furniture.cutlist import leg_lines_for_cabinet_config
        from cadquery_furniture.hardware import price_for
        lines = leg_lines_for_cabinet_config(CabinetConfig())
        assert lines and price_for(lines[0].sku) == 18.00


class TestSoldAsPair:
    def test_undermount_slides_sold_as_pairs(self):
        from cadquery_furniture.hardware import get_slide
        for key in ("blum_tandem_550h", "blum_movento_769", "salice_futura"):
            assert get_slide(key).sold_as_pair, key

    def test_accuride_side_mount_sold_as_singles(self):
        from cadquery_furniture.hardware import get_slide
        assert not get_slide("accuride_3832").sold_as_pair

    def test_pack_quantity_follows_sold_as_pair(self):
        from cadquery_furniture.cabinet import CabinetConfig
        from cadquery_furniture.cutlist import slide_lines_for_cabinet_config

        blum = CabinetConfig(drawer_slide="blum_tandem_550h", openings=[[200, "drawer"]])
        line = slide_lines_for_cabinet_config(blum)[0]
        assert (line.pack_quantity, line.packs_to_order) == (2, 1)  # buy 1 pair

        acc = CabinetConfig(drawer_slide="accuride_3832", openings=[[200, "drawer"]])
        line = slide_lines_for_cabinet_config(acc)[0]
        assert (line.pack_quantity, line.packs_to_order) == (1, 2)  # buy 2 singles


class TestBuildConfigValidation:
    def test_unknown_key_raises_value_error_with_valid_keys(self):
        from cadquery_furniture.cabinet import build_cabinet_config
        with pytest.raises(ValueError, match="heigth.*Valid parameters"):
            build_cabinet_config({"width": 600, "heigth": 720})


class TestShowWoodSheetPrices:
    def test_rift_white_oak_ply_priced(self):
        from cadquery_furniture.hardware import price_for
        assert price_for("sheet_rift_white_oak_ply_18mm") == 209.00


class TestSlideExtension:
    """The BOM must STATE drawer travel — Charlie couldn't verify the 563H
    swap was full extension from the paperwork (2026-07-23)."""

    def test_550h_is_the_only_partial_extension_slide(self):
        from cadquery_furniture.hardware import SLIDES
        assert SLIDES["blum_tandem_550h"].extension == "3/4"
        assert all(s.extension == "full" for k, s in SLIDES.items()
                   if k != "blum_tandem_550h")

    def test_bom_notes_state_extension(self):
        from cadquery_furniture.cabinet import build_cabinet_config
        from cadquery_furniture.cutlist import slide_lines_for_cabinet_config
        cfg = build_cabinet_config({
            "width": 600, "height": 720, "depth": 550,
            "drawer_slide": "blum_tandem_plus_563h",
            "drawer_config": [[300, "drawer"]]})
        slide = next(l for l in slide_lines_for_cabinet_config(cfg)
                     if l.category == "slide")
        assert "full extension" in slide.notes
