"""Regressions for the 2026-07-29 review's evaluator/viewer/preset minors
(M8 + minors — docs/code-review-2026-07-29.md)."""

import pytest

from cadquery_furniture.cabinet import CabinetConfig
from cadquery_furniture.evaluation import (
    check_edge_band_face_gap,
    check_edge_banding,
)

STOCK = {"width_mm": 89.0, "length_mm": 1219.2, "price_usd": 10.0,
         "strip_width_mm": 20.0}


def _hardwood(**kw) -> CabinetConfig:
    base = dict(width=600, height=720, depth=450,
                openings=[(300, "drawer"), (384, "drawer")],
                edge_band_mode="hardwood", edge_band_thickness_mm=3.2,
                edge_band_material="white_oak", edge_band_stock=dict(STOCK))
    base.update(kw)
    return CabinetConfig(**base)


class TestBandLengthVerticalEdges:
    """M8: side-panel front edges run the full cabinet height — a 2.1 m
    pantry must warn against a 1.2 m board even though every width-derived
    edge fits."""

    def test_tall_cabinet_warns_on_short_boards(self):
        cfg = _hardwood(height=2100,
                        openings=[(600, "door"), (1464, "door")])
        issues = check_edge_banding(cfg)
        assert any("Longest banded edge" in i.message for i in issues)

    def test_short_cabinet_still_silent(self):
        issues = check_edge_banding(_hardwood())
        assert not any("Longest banded edge" in i.message for i in issues)


class TestBandCoverageDoorThickness:
    def test_thick_door_edge_uncoverable_errors(self):
        cfg = _hardwood(openings=[(684, "door", {"door_thickness": 25.0})])
        issues = check_edge_banding(cfg)
        assert any("cannot cover" in i.message and i.severity.value == "error"
                   for i in issues)

    def test_default_doors_fine(self):
        cfg = _hardwood(openings=[(684, "door")])
        issues = check_edge_banding(cfg)
        assert not any("cannot cover" in i.message for i in issues)


class TestBandThicknessTolerance:
    def test_exact_quarter_inch_accepted(self):
        issues = check_edge_banding(_hardwood(edge_band_thickness_mm=6.35))
        assert not any("commonly sold" in i.message for i in issues)

    def test_odd_thickness_still_warns(self):
        issues = check_edge_banding(_hardwood(edge_band_thickness_mm=4.0))
        assert any("commonly sold" in i.message for i in issues)


class TestFaceGapBoundary:
    def _cfg(self, thk):
        return CabinetConfig(
            width=600, height=720, depth=450,
            openings=[(300, "drawer"), (384, "drawer")],
            edge_band_mode="hot_melt", edge_band_thickness_mm=thk,
            edge_band_material="white_oak")

    def test_exactly_closed_gap_is_error(self):
        # 2 × 2.0 mm growth closes the 4 mm gap to exactly 0 — faces bind.
        issues = check_edge_band_face_gap(self._cfg(2.0))
        assert [i.severity.value for i in issues] == ["error"]

    def test_narrow_but_open_gap_warns(self):
        issues = check_edge_band_face_gap(self._cfg(1.5))
        assert [i.severity.value for i in issues] == ["warning"]

    def test_hot_melt_over_1mm_warns(self):
        issues = check_edge_banding(self._cfg(1.2))
        assert any("too thick" in i.message for i in issues)


class TestPresetHinges:
    def test_all_presets_use_blumotion_hinges(self):
        # kitchen_base_door_pair_wide was missed by the BLUMOTION sweep.
        from cadquery_furniture.presets import PRESETS
        for name, preset in PRESETS.items():
            hinge = getattr(preset.config, "door_hinge", None) or ""
            if hinge:
                assert "blumotion" in hinge, (name, hinge)


class TestMangaJitterClamp:
    def test_jitter_clamped_in_tight_interior(self):
        cq = pytest.importorskip("cadquery")
        from cadquery_furniture.drawer import (
            DrawerConfig, build_drawer, MANGA_MAX_STACK,
        )
        # Find an opening whose interior width lands in the tight-but-
        # passing window [117.5, 121): the fit check passes, but the
        # unclamped jitter used to push manga1/manga3 1.5 mm into the
        # right side panel.
        cfg = None
        for w in range(140, 220):
            c = DrawerConfig(opening_width=w, opening_height=250,
                             opening_depth=450, use_standard_height=False)
            iw = c.box_width - 2 * c.side_thickness
            if 117.5 <= iw < 121.0:
                cfg = c
                break
        assert cfg is not None, "no opening width hit the tight window"
        assy, _parts = build_drawer(cfg, include_manga=True)
        side = None
        mangas = []
        for child in assy.children:
            if child.name == "side_R":
                side = child
            if child.name and child.name.startswith("manga"):
                mangas.append(child)
        assert len(mangas) == MANGA_MAX_STACK
        assert side is not None
        side_solid = side.obj.val().located(side.loc)
        for m in mangas:
            vol = m.obj.val().located(m.loc)
            overlap = vol.intersect(side_solid).Volume()
            assert overlap < 1e-6, (m.name, overlap)


class TestViewerMangaGate:
    def test_emitted_js_gates_manga_on_drawer_parent(self):
        from cadquery_furniture import visualize
        # The structural gate must be present in the emitted viewer JS —
        # without it a cabinet legitimately named "manga2" classifies as
        # manga volumes and renders invisible.
        assert "BOX_RE.test(n.parent.name" in visualize._MANGA_JS
