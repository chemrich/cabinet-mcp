"""rips_first optimizer — geometry validity, fence cap, strip bundling,
and the declared cut plan."""

import pytest

from cadquery_furniture.cutlist import (
    CutlistPanel,
    RIPS_FIRST_FENCE_LIMIT_MM,
    RIPS_FIRST_MIN_STRIP_MM,
    SheetStock,
    optimize_cutlist,
)


def _boxes():
    return [
        CutlistPanel("side_a", 381, 76, 12, quantity=36,
                     grain_direction="", material="x"),
        CutlistPanel("side_b", 415, 76, 12, quantity=14,
                     grain_direction="", material="x"),
        CutlistPanel("front_a", 263, 76, 12, quantity=24,
                     grain_direction="", material="x"),
        CutlistPanel("front_b", 303, 152, 12, quantity=4,
                     grain_direction="", material="x"),
        CutlistPanel("side_c", 381, 152, 12, quantity=8,
                     grain_direction="", material="x"),
    ]


def _run(panels, L=2440, W=1220, t=12):
    return optimize_cutlist(
        panels, stock_sheet=SheetStock("s", L, W, t), kerf=3.2,
        algorithm="rips_first")


def _assert_valid(r, L, W):
    by = {}
    for p in r.placements:
        by.setdefault(p.sheet_index, []).append(p)
    for pls in by.values():
        for i, a in enumerate(pls):
            assert a.x + a.placed_length <= L + 0.01
            assert a.y + a.placed_width <= W + 0.01
            for b in pls[i + 1:]:
                overlap = (a.x < b.x + b.placed_length - 0.01
                           and b.x < a.x + a.placed_length - 0.01
                           and a.y < b.y + b.placed_width - 0.01
                           and b.y < a.y + a.placed_width - 0.01)
                assert not overlap, (a.panel_name, b.panel_name)


class TestRipsFirst:
    def test_geometry_valid(self):
        r = _run(_boxes())
        assert r.unplaced == []
        _assert_valid(r, 2440, 1220)

    def test_algorithm_reported(self):
        assert _run(_boxes()).algorithm_used == "rips_first"

    def test_narrow_pieces_bundle_into_wide_track_rips(self):
        # 76 mm parts must NOT each own a track-saw strip: every declared
        # breakdown rip is at least RIPS_FIRST_MIN_STRIP_MM, except at most
        # one remainder strip per sheet (a lone tail with nothing left to
        # bundle). The old assertion special-cased a magic 124 mm width
        # anywhere in the run, which let sub-minimum rips hide
        # (review 2026-07-29).
        from cadquery_furniture.cutlist import RIPS_FIRST_MIN_STRIP_MM
        r = _run(_boxes())
        assert r.cuts
        seen_any = False
        for entries in r.cuts.values():
            widths = [e[8] for e in entries if e[7]]
            seen_any = seen_any or bool(widths)
            tails = [w for w in widths if w < RIPS_FIRST_MIN_STRIP_MM]
            assert len(tails) <= 1, widths
        assert seen_any, "expected declared breakdown rips"

    def test_thin_splits_are_non_breakdown(self):
        r = _run(_boxes())
        thin = [e for entries in r.cuts.values() for e in entries
                if not e[7] and e[2] == "h"]
        assert thin, "expected table-saw stack splits in the plan"
        assert all(e[8] <= RIPS_FIRST_FENCE_LIMIT_MM for e in thin)

    def test_fence_cap_respected_on_stacked_pieces(self):
        # A grain-constrained piece wider than the fence can never be a
        # stacked (table-saw) split — it rides its own strip.
        panels = [
            CutlistPanel("wide", 800, 600, 18, quantity=4,
                         grain_direction="length", material="x"),
            CutlistPanel("narrow", 400, 100, 18, quantity=10,
                         grain_direction="length", material="x"),
        ]
        r = _run(panels, t=18)
        _assert_valid(r, 2440, 1220)
        for entries in (r.cuts or {}).values():
            for e in entries:
                if not e[7] and e[2] == "h":
                    assert e[8] <= RIPS_FIRST_FENCE_LIMIT_MM

    def test_wide_pieces_unbundled(self):
        panels = [CutlistPanel("side", 800, 600, 18, quantity=4,
                               grain_direction="length", material="x")]
        r = _run(panels, t=18)
        widths = [e[8] for entries in r.cuts.values() for e in entries
                  if e[7]]
        assert all(w == 600 for w in widths)

    def test_min_strip_constant_sane(self):
        assert 100 <= RIPS_FIRST_MIN_STRIP_MM <= 300

    def test_grain_constrained_never_rotated(self):
        panels = [CutlistPanel("top", 1183, 451, 18, quantity=6,
                               grain_direction="length", material="x")]
        r = _run(panels, t=18)
        assert all(not p.rotated for p in r.placements)
