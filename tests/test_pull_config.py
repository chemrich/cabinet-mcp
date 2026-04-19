"""Tests for pull-hardware fields on DrawerConfig, DoorConfig, and CabinetConfig.

These tests exercise the *config plumbing* added in Phase 3 — the pull catalog
loader and placement math themselves are covered in tests/test_pulls.py.
"""

import pytest

from cadquery_furniture.cabinet import CabinetConfig
from cadquery_furniture.door import DoorConfig
from cadquery_furniture.drawer import DrawerConfig
from cadquery_furniture.hardware import get_pull
from cadquery_furniture.pulls import PullPlacement


# ─── DrawerConfig ────────────────────────────────────────────────────────────


class TestDrawerConfigPullFields:
    def test_default_no_pull(self):
        d = DrawerConfig(opening_width=564, opening_height=150, opening_depth=541)
        assert d.pull_key is None
        assert d.pull_count == 0
        assert d.pull_vertical == "center"
        assert d.pull_placements == []

    def test_with_pull_centered(self):
        d = DrawerConfig(
            opening_width=564, opening_height=150, opening_depth=541,
            pull_key="topknobs-hb-128",
        )
        placements = d.pull_placements
        assert len(placements) == 1
        assert isinstance(placements[0], PullPlacement)
        # Face width = 564 + 2·10 = 584; expect centred at 292.
        assert placements[0].center[0] == pytest.approx(d.face_width / 2)
        assert placements[0].pull_key == "topknobs-hb-128"
        # Two surface-mount holes at ±64 mm from centre
        xs = [hx for hx, _ in placements[0].hole_coords]
        assert xs[0] == pytest.approx(d.face_width / 2 - 64.0)
        assert xs[1] == pytest.approx(d.face_width / 2 + 64.0)

    def test_pull_vertical_upper_third(self):
        d = DrawerConfig(
            opening_width=564, opening_height=300, opening_depth=541,
            pull_key="topknobs-hb-128",
            pull_vertical="upper_third",
        )
        # face_height = 300 + 3 + 3 = 306; upper_third → z = 2/3 · 306 = 204
        assert d.pull_placements[0].center[1] == pytest.approx(d.face_height * 2.0 / 3.0)

    def test_explicit_pull_count(self):
        d = DrawerConfig(
            opening_width=564, opening_height=150, opening_depth=541,
            pull_key="topknobs-hb-76",  # short pull → fits dual easily
            pull_count=2,
        )
        assert len(d.pull_placements) == 2

    def test_no_face_means_no_placements(self):
        # applied_face=False → pull cannot mount on the sub-front
        d = DrawerConfig(
            opening_width=564, opening_height=150, opening_depth=541,
            pull_key="topknobs-hb-128",
            applied_face=False,
        )
        assert d.pull_placements == []

    def test_unknown_pull_key_raises(self):
        d = DrawerConfig(
            opening_width=564, opening_height=150, opening_depth=541,
            pull_key="not-a-real-pull",
        )
        with pytest.raises(KeyError, match="Unknown pull"):
            _ = d.pull_placements


# ─── DoorConfig ──────────────────────────────────────────────────────────────


class TestDoorConfigPullFields:
    def test_default_no_pull(self):
        d = DoorConfig(opening_width=400, opening_height=720)
        assert d.pull_key is None
        assert d.pull_placements == []
        assert d.total_pull_count == 0

    def test_single_door_with_pull(self):
        d = DoorConfig(opening_width=400, opening_height=720, pull_key="topknobs-hb-96")
        placements = d.pull_placements
        assert len(placements) == 1
        # Door width centre, door height centre
        assert placements[0].center[0] == pytest.approx(d.door_width / 2)
        assert placements[0].center[1] == pytest.approx(d.door_height / 2)
        assert d.total_pull_count == 1

    def test_door_pair_doubles_total_count(self):
        d = DoorConfig(
            opening_width=600, opening_height=720, num_doors=2,
            pull_key="topknobs-hb-96",
        )
        # Each door gets one pull → two pulls total
        assert len(d.pull_placements) == 1
        assert d.total_pull_count == 2

    def test_unknown_pull_key_raises(self):
        d = DoorConfig(
            opening_width=400, opening_height=720,
            pull_key="not-a-real-pull",
        )
        with pytest.raises(KeyError, match="Unknown pull"):
            _ = d.pull_placements

    def test_pull_vertical_lower_third_on_overhead(self):
        # Use case: wall cabinet — pull near the bottom for reach
        d = DoorConfig(
            opening_width=400, opening_height=600,
            pull_key="topknobs-hb-96",
            pull_vertical="lower_third",
        )
        # door_height = 600 - 2 - 2 = 596; lower_third → 596 / 3
        assert d.pull_placements[0].center[1] == pytest.approx(d.door_height / 3.0)


# ─── CabinetConfig defaults + propagation ────────────────────────────────────


class TestCabinetConfigPullDefaults:
    def test_defaults_are_none(self):
        cab = CabinetConfig()
        assert cab.drawer_pull is None
        assert cab.door_pull is None

    def test_drawer_pull_propagates(self):
        # Mirror what drawers_from_cabinet_config does internally.
        # (We do NOT call the real function here because it imports cadquery.)
        cab = CabinetConfig(drawer_pull="topknobs-hb-128")
        dcfg = DrawerConfig(
            opening_width=cab.interior_width,
            opening_height=150,
            opening_depth=cab.interior_depth,
            slide_key=cab.drawer_slide,
            pull_key=cab.drawer_pull,
        )
        assert dcfg.pull_key == "topknobs-hb-128"
        assert len(dcfg.pull_placements) == 1

    def test_door_pull_propagates(self):
        cab = CabinetConfig(door_pull="topknobs-hb-96")
        dcfg = DoorConfig(
            opening_width=cab.interior_width,
            opening_height=720,
            num_doors=1,
            hinge_key=cab.door_hinge,
            pull_key=cab.door_pull,
        )
        assert dcfg.pull_key == "topknobs-hb-96"
        assert len(dcfg.pull_placements) == 1

    def test_per_drawer_override_wins(self):
        # If a caller constructs a DrawerConfig with its own pull_key, that
        # value takes precedence — there is no merging on DrawerConfig itself.
        cab = CabinetConfig(drawer_pull="topknobs-hb-128")
        dcfg = DrawerConfig(
            opening_width=cab.interior_width,
            opening_height=150,
            opening_depth=cab.interior_depth,
            pull_key="topknobs-hb-76",  # explicit override
        )
        assert dcfg.pull_key == "topknobs-hb-76"
