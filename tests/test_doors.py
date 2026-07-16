"""
Tests for door.py, the extended HingeSpec in hardware.py, and the door
evaluation checks in evaluation.py.

All tests are pure-Python (no CadQuery) — they exercise parametric logic only.
"""

import importlib.util
import math

import pytest


cq_missing = importlib.util.find_spec("cadquery") is None
skipif_no_cq = pytest.mark.skipif(cq_missing, reason="cadquery not installed")

if not cq_missing:
    import cadquery as cq

from cadquery_furniture.hardware import (
    OverlayType,
    BLUM_CLIP_TOP_110_FULL,
    BLUM_CLIP_TOP_110_HALF,
    BLUM_CLIP_TOP_110_INSET,
    BLUM_CLIP_TOP_BLUMOTION_110_FULL,
    BLUM_CLIP_TOP_BLUMOTION_110_HALF,
    BLUM_CLIP_TOP_BLUMOTION_110_INSET,
    BLUM_CLIP_TOP_170_FULL,
    get_hinge,
    HINGES,
)
from cadquery_furniture.door import DoorConfig
from cadquery_furniture.evaluation import (
    Severity,
    check_door_hinge_count,
    check_door_dimensions,
    check_door_pair_width,
)


# ─── HingeSpec structural tests ───────────────────────────────────────────────

class TestHingeSpecStructure:
    """Basic sanity checks on the hinge database."""

    def test_all_expected_keys_present(self):
        expected = [
            "blum_clip_top_110_full",
            "blum_clip_top_blumotion_110_full",
            "blum_clip_top_110_half",
            "blum_clip_top_blumotion_110_half",
            "blum_clip_top_110_inset",
            "blum_clip_top_blumotion_110_inset",
            "blum_clip_top_170_full",
            # legacy aliases
            "blum_clip_top_110",
            "blum_clip_top_170",
        ]
        for key in expected:
            assert key in HINGES, f"Missing hinge key: {key}"

    def test_overlay_types_correct(self):
        assert BLUM_CLIP_TOP_110_FULL.overlay_type == OverlayType.FULL
        assert BLUM_CLIP_TOP_110_HALF.overlay_type == OverlayType.HALF
        assert BLUM_CLIP_TOP_110_INSET.overlay_type == OverlayType.INSET

    def test_overlay_amounts(self):
        assert BLUM_CLIP_TOP_110_FULL.overlay == pytest.approx(16.0)
        assert BLUM_CLIP_TOP_110_HALF.overlay == pytest.approx(9.5)
        assert BLUM_CLIP_TOP_110_INSET.overlay == pytest.approx(0.0)

    def test_cup_boring_standard(self):
        for hinge in [BLUM_CLIP_TOP_110_FULL, BLUM_CLIP_TOP_110_HALF, BLUM_CLIP_TOP_110_INSET]:
            assert hinge.cup_boring_distance == pytest.approx(22.5)
            assert hinge.cup_diameter == pytest.approx(35.0)
            assert hinge.cup_depth == pytest.approx(13.0)

    def test_soft_close_flags(self):
        assert BLUM_CLIP_TOP_110_FULL.soft_close is False
        assert BLUM_CLIP_TOP_BLUMOTION_110_FULL.soft_close is True
        assert BLUM_CLIP_TOP_110_HALF.soft_close is False
        assert BLUM_CLIP_TOP_BLUMOTION_110_HALF.soft_close is True
        assert BLUM_CLIP_TOP_110_INSET.soft_close is False
        assert BLUM_CLIP_TOP_BLUMOTION_110_INSET.soft_close is True

    def test_blumotion_higher_weight_rating(self):
        assert BLUM_CLIP_TOP_BLUMOTION_110_FULL.max_door_weight_kg > BLUM_CLIP_TOP_110_FULL.max_door_weight_kg

    def test_part_numbers_present(self):
        assert BLUM_CLIP_TOP_110_FULL.part_number == "71B3550"
        assert BLUM_CLIP_TOP_BLUMOTION_110_FULL.part_number == "71B3590"
        assert BLUM_CLIP_TOP_110_HALF.part_number == "71H3550"
        assert BLUM_CLIP_TOP_110_INSET.part_number == "71N3550"

    def test_cup_edge_clearance_valid(self):
        """Cup boring must leave ≥ 3 mm of material at the door edge."""
        for hinge in HINGES.values():
            edge_margin = hinge.cup_boring_distance - hinge.cup_diameter / 2
            assert edge_margin >= 3.0, (
                f"{hinge.name}: cup edge margin {edge_margin:.1f} mm < 3 mm"
            )

    def test_get_hinge_raises_on_unknown(self):
        with pytest.raises(KeyError):
            get_hinge("nonexistent_hinge")

    def test_legacy_alias_resolves(self):
        assert get_hinge("blum_clip_top_110") is BLUM_CLIP_TOP_110_FULL
        assert get_hinge("blum_clip_top_170") is BLUM_CLIP_TOP_170_FULL


# ─── HingeSpec.hinges_for_height ─────────────────────────────────────────────

class TestHingesForHeight:
    h = BLUM_CLIP_TOP_110_FULL  # 20 kg rating

    def test_short_door_2_hinges(self):
        # 700 mm door: base 2 hinges, span 500 mm ≤ max_hinge_spacing → stays 2.
        assert self.h.hinges_for_height(700) == 2

    def test_thousand_mm_door_spacing_bumps_to_3(self):
        # Behavior change (audit finding: count vs max_hinge_spacing contradiction).
        # Old rule gave a 1200 mm door 2 hinges at 1000 mm spacing — which
        # check_door_hinge_count then flagged as > 700 mm max. hinges_for_height
        # now raises the count until spacing ≤ max_hinge_spacing, so a 1200 mm
        # door gets 3 hinges (max gap 500 mm ≤ 700 mm) instead of 2.
        assert self.h.hinges_for_height(1200) == 3
        # No position gap exceeds the spec's own max_hinge_spacing.
        pos = self.h.hinge_positions(1200)
        gaps = [pos[i] - pos[i - 1] for i in range(1, len(pos))]
        assert max(gaps) <= self.h.max_hinge_spacing + 1e-6

    def test_tall_door_3_hinges(self):
        # 1201 mm door: base 3 hinges, span 1001 mm → ceil(1001/700)+1 = 3.
        assert self.h.hinges_for_height(1201) == 3

    def test_1800_mm_door_spacing_bumps_to_4(self):
        # Behavior change: 1800 mm span 1600 mm needs ceil(1600/700)+1 = 4
        # hinges to keep spacing ≤ 700 mm (old height-only rule gave 3).
        assert self.h.hinges_for_height(1800) == 4

    def test_very_tall_door_4_hinges(self):
        assert self.h.hinges_for_height(1801) == 4

    def test_overweight_adds_hinge(self):
        # 20 kg rating; 45 kg door should add extra hinges
        count = self.h.hinges_for_height(700, door_weight_kg=45.0)
        assert count > 2

    def test_weight_exactly_at_limit_no_extra(self):
        count = self.h.hinges_for_height(700, door_weight_kg=20.0)
        assert count == 2


# ─── HingeSpec.hinge_positions ────────────────────────────────────────────────

class TestHingePositions:
    h = BLUM_CLIP_TOP_110_FULL

    def test_two_hinge_positions(self):
        positions = self.h.hinge_positions(720)
        assert len(positions) == 2
        # Bottom hinge 100 mm from door bottom
        assert positions[0] == pytest.approx(self.h.hinge_inset_bottom)
        # Top hinge 100 mm from door top
        assert positions[1] == pytest.approx(720 - self.h.hinge_inset_top)

    def test_three_hinge_positions(self):
        positions = self.h.hinge_positions(1500)
        assert len(positions) == 3
        assert positions[0] == pytest.approx(self.h.hinge_inset_bottom)
        assert positions[-1] == pytest.approx(1500 - self.h.hinge_inset_top)
        # Middle hinge should be evenly centred
        mid = (positions[0] + positions[-1]) / 2
        assert positions[1] == pytest.approx(mid)

    def test_positions_are_increasing(self):
        for height in [720, 1400, 2000]:
            positions = self.h.hinge_positions(height)
            for i in range(1, len(positions)):
                assert positions[i] > positions[i - 1]


# ─── Hinge layout regressions (audit) ─────────────────────────────────────────

class TestHingeLayoutRegressions:
    """Guards the audit fixes: (1) hinges_for_height must never recommend a
    layout that exceeds its own max_hinge_spacing; (2) hinge_positions must be
    ordered and inside the door for short doors; (3) validate_door flags doors
    too short to seat top+bottom hinges; (4) the weight off-by-one is gone.
    """

    h = BLUM_CLIP_TOP_110_FULL

    def test_spacing_within_max_for_every_covered_height(self):
        # Every height the count rule covers must produce a layout whose
        # largest hinge gap is ≤ max_hinge_spacing.
        for height in range(200, 3001, 10):
            positions = self.h.hinge_positions(height)
            if len(positions) < 2:
                continue
            gaps = [positions[i] - positions[i - 1] for i in range(1, len(positions))]
            assert max(gaps) <= self.h.max_hinge_spacing + 1e-6, (height, gaps)

    def test_short_door_positions_ordered_and_in_range(self):
        for height in (80, 100, 150, 199, 235):
            positions = self.h.hinge_positions(height)
            assert all(0.0 <= z <= height for z in positions), (height, positions)
            for i in range(1, len(positions)):
                assert positions[i] > positions[i - 1], (height, positions)

    def test_validate_door_flags_too_short(self):
        min_h = (self.h.hinge_inset_top + self.h.hinge_inset_bottom
                 + self.h.cup_diameter)  # 235 mm for this hinge
        issues = self.h.validate_door(door_thickness=19.0, door_height=min_h - 1)
        assert any("too short" in i for i in issues)
        # A comfortably tall door raises no height issue.
        assert not any("too short" in i
                       for i in self.h.validate_door(19.0, min_h + 100))

    def test_weight_off_by_one_fixed(self):
        # Exactly one bracket above the rating adds exactly one hinge, not two.
        base = self.h.hinges_for_height(700)  # 2 for a short door
        # +25 kg over the 20 kg rating → +1 hinge.
        assert self.h.hinges_for_height(700, door_weight_kg=45.0) == base + 1
        # Just past the limit is already +1.
        assert self.h.hinges_for_height(700, door_weight_kg=20.1) == base + 1
        # Just past two brackets is +2.
        assert self.h.hinges_for_height(700, door_weight_kg=45.1) == base + 2


# ─── DoorConfig properties ────────────────────────────────────────────────────

class TestDoorConfigFullOverlay:
    """Full overlay (16 mm per side), single door."""

    def _cfg(self, **kwargs):
        defaults = dict(opening_width=564, opening_height=716, hinge_key="blum_clip_top_110_full")
        defaults.update(kwargs)
        return DoorConfig(**defaults)

    def test_door_width_single(self):
        cfg = self._cfg()
        # door_width = opening_width + 2 × overlay = 564 + 32 = 596
        assert cfg.door_width == pytest.approx(596.0)

    def test_door_height(self):
        cfg = self._cfg()
        # door_height = opening_height - gap_top - gap_bottom = 716 - 4 = 712
        assert cfg.door_height == pytest.approx(712.0)

    def test_hinge_count_short_door(self):
        cfg = self._cfg()
        assert cfg.hinge_count == 2

    def test_hinge_count_tall_door(self):
        cfg = self._cfg(opening_height=1310)
        # door_height ≈ 1306 > 1200 → 3 hinges
        assert cfg.hinge_count == 3

    def test_total_hinge_count_single(self):
        cfg = self._cfg()
        assert cfg.total_hinge_count == cfg.hinge_count * 1


class TestDoorConfigFullOverlayPair:
    """Full overlay, door pair."""

    def _cfg(self, **kwargs):
        defaults = dict(
            opening_width=1128,
            opening_height=716,
            num_doors=2,
            hinge_key="blum_clip_top_110_full",
        )
        defaults.update(kwargs)
        return DoorConfig(**defaults)

    def test_door_width_pair(self):
        cfg = self._cfg()
        # door_width_each = opening_width/2 + overlay − gap_between/2
        # = 564 + 16 − 1 = 579
        expected = 1128 / 2 + 16.0 - 2.0 / 2
        assert cfg.door_width == pytest.approx(expected)

    def test_total_hinge_count_pair(self):
        cfg = self._cfg()
        assert cfg.total_hinge_count == cfg.hinge_count * 2


class TestDoorConfigHalfOverlay:
    """Half overlay (9.5 mm), single door."""

    def _cfg(self, **kwargs):
        defaults = dict(opening_width=564, opening_height=716, hinge_key="blum_clip_top_110_half")
        defaults.update(kwargs)
        return DoorConfig(**defaults)

    def test_door_width_single(self):
        cfg = self._cfg()
        # door_width = opening_width + 2 × 9.5 = 564 + 19 = 583
        assert cfg.door_width == pytest.approx(583.0)

    def test_overlay_type(self):
        cfg = self._cfg()
        assert cfg.hinge.overlay_type == OverlayType.HALF


class TestDoorConfigInset:
    """Inset door — door sits inside the opening."""

    def _cfg(self, **kwargs):
        defaults = dict(
            opening_width=564,
            opening_height=716,
            hinge_key="blum_clip_top_110_inset",
            gap_side=2.0,
        )
        defaults.update(kwargs)
        return DoorConfig(**defaults)

    def test_door_width_single(self):
        cfg = self._cfg()
        # door_width = opening_width − 2 × gap_side = 564 − 4 = 560
        assert cfg.door_width == pytest.approx(560.0)

    def test_door_width_pair(self):
        cfg = self._cfg(num_doors=2)
        # door_width_each = (opening_width − gap_between) / 2 − gap_side
        # = (564 − 2) / 2 − 2 = 281 − 2 = 279
        expected = (564 - 2.0) / 2 - 2.0
        assert cfg.door_width == pytest.approx(expected)

    def test_door_height(self):
        cfg = self._cfg()
        # Same formula: opening_height − gap_top − gap_bottom
        assert cfg.door_height == pytest.approx(712.0)


# ─── Door evaluation checks ───────────────────────────────────────────────────

class TestCheckDoorHingeCount:

    def _cfg(self, **kwargs):
        defaults = dict(opening_width=564, opening_height=716, hinge_key="blum_clip_top_110_full")
        defaults.update(kwargs)
        return DoorConfig(**defaults)

    def test_normal_door_no_issues(self):
        issues = check_door_hinge_count(self._cfg())
        assert not any(i.severity == Severity.ERROR for i in issues)

    def test_very_short_door_still_2_hinges(self):
        issues = check_door_hinge_count(self._cfg(opening_height=200))
        # 2 hinges — no error (minimum is 2)
        assert not any(i.severity == Severity.ERROR for i in issues)

    def test_overweight_door_warning(self):
        issues = check_door_hinge_count(self._cfg(door_weight_kg=50.0))
        messages = [i.message for i in issues]
        # Should produce a weight warning
        assert any("weight" in m.lower() for m in messages)

    def test_tall_door_no_error(self):
        # 1500mm door needs 3 hinges — should be fine
        issues = check_door_hinge_count(self._cfg(opening_height=1510))
        assert not any(i.severity == Severity.ERROR for i in issues)


class TestCheckDoorDimensions:

    def _cfg(self, **kwargs):
        defaults = dict(opening_width=564, opening_height=716, hinge_key="blum_clip_top_110_full")
        defaults.update(kwargs)
        return DoorConfig(**defaults)

    def test_valid_door_no_errors(self):
        issues = check_door_dimensions(self._cfg())
        errors = [i for i in issues if i.severity == Severity.ERROR]
        assert not errors

    def test_door_too_thin_error(self):
        cfg = self._cfg()
        cfg.door_thickness = 12.0  # below min 16 mm
        issues = check_door_dimensions(cfg)
        assert any(i.severity == Severity.ERROR for i in issues)

    def test_door_too_thick_error(self):
        cfg = self._cfg()
        cfg.door_thickness = 30.0  # above max 25 mm
        issues = check_door_dimensions(cfg)
        assert any(i.severity == Severity.ERROR for i in issues)

    def test_door_thickness_at_limits_ok(self):
        for t in [16.0, 18.0, 25.0]:
            cfg = self._cfg()
            cfg.door_thickness = t
            issues = check_door_dimensions(cfg)
            errors = [i for i in issues if i.severity == Severity.ERROR]
            assert not errors, f"Thickness {t} mm should be valid but got errors: {errors}"

    def test_inset_door_fit_warning(self):
        """An inset door whose width doesn't match opening − 2×gap_side should warn."""
        cfg = DoorConfig(
            opening_width=564,
            opening_height=716,
            hinge_key="blum_clip_top_110_inset",
            gap_side=2.0,
        )
        # door_width is computed correctly so no warning expected
        issues = check_door_dimensions(cfg)
        warnings = [i for i in issues if i.check == "door_inset_fit"]
        assert not warnings

    def test_negative_door_height_error(self):
        """Gaps that exceed opening height should raise an error."""
        cfg = self._cfg(opening_height=2, gap_top=2.0, gap_bottom=2.0)
        issues = check_door_dimensions(cfg)
        assert any(i.severity == Severity.ERROR for i in issues)


class TestCheckDoorPairWidth:

    def test_narrow_pair_no_warning(self):
        cfg = DoorConfig(opening_width=800, opening_height=716, num_doors=2,
                         hinge_key="blum_clip_top_110_full")
        issues = check_door_pair_width(cfg)
        assert not issues

    def test_wide_pair_warning(self):
        # opening_width=1300 → each door ≈ 665 mm > 600 mm threshold
        cfg = DoorConfig(opening_width=1300, opening_height=716, num_doors=2,
                         hinge_key="blum_clip_top_110_full")
        issues = check_door_pair_width(cfg)
        assert any(i.severity == Severity.WARNING for i in issues)

    def test_single_door_no_check(self):
        # check_door_pair_width should return nothing for single doors
        cfg = DoorConfig(opening_width=700, opening_height=716, num_doors=1,
                         hinge_key="blum_clip_top_110_full")
        issues = check_door_pair_width(cfg)
        assert issues == []


# ─── Cabinet config slot type integration ────────────────────────────────────

class TestCabinetConfigDoorSlots:
    """Verify CabinetConfig accepts door/door_pair slot types and door_hinge."""

    def test_door_hinge_default(self):
        from cadquery_furniture.cabinet import CabinetConfig
        cfg = CabinetConfig()
        assert cfg.door_hinge == "blum_clip_top_110_full"

    def test_door_slot_accepted(self):
        from cadquery_furniture.cabinet import CabinetConfig
        cfg = CabinetConfig(openings=[(716, "door")])
        assert cfg.openings[0].opening_type == "door"

    def test_door_pair_slot_accepted(self):
        from cadquery_furniture.cabinet import CabinetConfig
        cfg = CabinetConfig(openings=[(716, "door_pair")])
        assert cfg.openings[0].opening_type == "door_pair"

    def test_mixed_slots_accepted(self):
        from cadquery_furniture.cabinet import CabinetConfig
        cfg = CabinetConfig(
            openings=[
                (200, "drawer"),
                (516, "door"),
            ]
        )
        total = sum(op.height_mm for op in cfg.openings)
        assert total == pytest.approx(716)


# ─── Hinge cup boring geometry (CadQuery) ─────────────────────────────────────

@skipif_no_cq
class TestHingeCupBoringGeometry:
    """Regression tests for the CadQuery hinge-cup borings in make_door_panel.

    The cups must be bored into the *back* face (y = door_thickness) at
    x = cup_boring_distance from the hinge edge and z = each hinge position —
    not on the wrong axis (a prior bug transposed x/z and bored across width).
    """

    def _panel(self):
        from cadquery_furniture.door import DoorConfig, make_door_panel
        cfg = DoorConfig(opening_width=500, opening_height=700)
        return cfg, make_door_panel(cfg).val()

    def _has_material(self, solid, x, y, z):
        probe = (
            cq.Workplane("XY")
            .transformed(offset=(x - 0.5, y - 0.5, z - 0.5))
            .box(1, 1, 1, centered=False)
        )
        return solid.intersect(probe.val()).Volume() > 1e-6

    def test_removed_volume_equals_two_full_cups(self):
        cfg, solid = self._panel()
        h = cfg.hinge
        r = h.cup_diameter / 2
        full = cfg.door_width * cfg.door_height * cfg.door_thickness
        removed = full - solid.Volume()
        expected = len(cfg.hinge_positions_z) * math.pi * r * r * h.cup_depth
        assert len(cfg.hinge_positions_z) == 2
        assert removed == pytest.approx(expected, rel=1e-3)

    def test_cups_bored_into_back_face_at_correct_positions(self):
        cfg, solid = self._panel()
        h = cfg.hinge
        t = cfg.door_thickness
        for z_pos in cfg.hinge_positions_z:
            # Interior of the intended cup void is empty (material removed).
            assert not self._has_material(
                solid, h.cup_boring_distance, t - h.cup_depth / 2, z_pos
            )
            # Front face at the same x/z is still solid (cup does not pierce through).
            assert self._has_material(solid, h.cup_boring_distance, 1.0, z_pos)


# ─── Drawer face over a door opening (CadQuery) ───────────────────────────────

@skipif_no_cq
class TestDrawerFaceOverDoor:
    """Regression: a drawer stacked above a door must not anchor its face to
    the bottom of the face stack (which would overlap the door below it)."""

    def _faces(self, openings):
        from cadquery_furniture.cabinet import CabinetConfig, build_multi_bay_cabinet
        cfg = CabinetConfig(
            width=600, height=720, depth=550, openings=openings
        )
        assy, _ = build_multi_bay_cabinet([cfg], include_feet=False)
        spans = {}
        for child in assy.children:
            n = child.name
            if "face" in n or "door" in n:
                z0 = child.loc.toTuple()[0][2]
                bb = child.obj.val().BoundingBox()
                spans[n] = (z0 + bb.zmin, z0 + bb.zmax)
        return cfg, spans

    def test_drawer_face_starts_above_door(self):
        cfg, spans = self._faces([(450, "door"), (234, "drawer")])
        door_top = spans["bay0_door0"][1]
        face_bot = spans["bay0_face1"][0]
        # Face must start above the bottom panel (bug produced z≈18) and sit a
        # face_gap/2 reveal above the door top rather than overlapping it.
        assert face_bot > cfg.bottom_thickness + 1
        assert face_bot >= door_top
