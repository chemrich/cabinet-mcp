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
        assert BLUM_MOVENTO_769.max_load_kg >= 75

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
