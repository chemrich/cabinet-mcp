"""Drawer-box assembly correctness.

For every DrawerJoineryStyle and a sweep of opening sizes, verifies:

  1. Assembled bbox = cfg.box_width × box_depth × box_height.
  2. Side clearance to the cabinet opening = slide.nominal_side_clearance.
  3. No material interference between any pair of wall panels.
  4. The bottom panel sits in each wall's dado at the expected engagement
     volume (intersection with the wall's *uncut envelope*, not the cut wall —
     the dado removes material exactly where the bottom sits).
  5. The bottom panel is contained within the carcass exterior.
  6. For non-BUTT styles, the sub-front actually engages the side rabbet
     (regression check for the 'decorative joinery' bug).
"""

import importlib.util

import pytest


cq_missing = importlib.util.find_spec("cadquery") is None
skipif_no_cq = pytest.mark.skipif(cq_missing, reason="cadquery not installed")

if not cq_missing:
    import cadquery as cq

from cadquery_furniture.drawer import (
    DrawerConfig,
    make_drawer_bottom,
    make_drawer_front_back,
    make_drawer_side,
)
from cadquery_furniture.joinery import DrawerJoineryStyle


OPENING_SIZES = [
    (600, 200, 500),
    (900, 305, 600),
    (400, 125, 400),
]


def _placed(panel_wp, x, y, z):
    return panel_wp.val().translate(cq.Vector(x, y, z))


def _envelope(x0, y0, z0, dx, dy, dz):
    return (cq.Workplane("XY").transformed(offset=(x0, y0, z0))
            .box(dx, dy, dz, centered=False).val())


def _vol(shape):
    try:
        return shape.Volume()
    except Exception:
        return float("nan")


def _intersect_vol(a, b):
    try:
        return _vol(a.intersect(b))
    except Exception:
        return float("nan")


def _build_placed(cfg):
    """Return (LS, RS, SF, BK, BT) at their world-coordinate positions inside
    a cabinet opening with x_offset = slide.nominal_side_clearance."""
    x0 = cfg.slide.nominal_side_clearance
    t_s = cfg.side_thickness
    t_fb = cfg.front_back_thickness
    bd = cfg.box_depth
    bw = cfg.box_width
    bdd = cfg.bottom_dado_depth
    dz = cfg.bottom_dado_inset
    engagement_x = cfg.joinery.engagement_x
    fb_x = x0 + t_s - engagement_x

    ls = _placed(make_drawer_side(cfg, side="left"), x0, 0, 0)
    rs = _placed(make_drawer_side(cfg, side="right"), x0 + bw - t_s, 0, 0)
    sf = _placed(make_drawer_front_back(cfg, position="front"), fb_x, 0, 0)
    bk = _placed(make_drawer_front_back(cfg, position="back"),
                 fb_x, bd - t_fb, 0)
    bt = _placed(make_drawer_bottom(cfg),
                 x0 + t_s - bdd, t_fb - bdd, dz)
    return ls, rs, sf, bk, bt


@pytest.fixture(params=[s for s in DrawerJoineryStyle], ids=lambda s: s.value)
def style(request):
    return request.param


@pytest.fixture(params=OPENING_SIZES, ids=lambda s: f"{s[0]}x{s[1]}x{s[2]}")
def opening(request):
    return request.param


@pytest.fixture
def cfg(style, opening):
    w, h, d = opening
    return DrawerConfig(
        opening_width=w, opening_height=h, opening_depth=d,
        joinery_style=style,
    )


@skipif_no_cq
class TestAssembledSize:
    def test_bbox_matches_box_dims(self, cfg):
        ls, rs, sf, bk, _ = _build_placed(cfg)
        union = ls.fuse(rs).fuse(sf).fuse(bk)
        bb = union.BoundingBox()
        assert bb.xlen == pytest.approx(cfg.box_width, abs=0.5)
        assert bb.ylen == pytest.approx(cfg.box_depth, abs=0.5)
        assert bb.zlen == pytest.approx(cfg.box_height, abs=0.5)


@skipif_no_cq
class TestCabinetClearance:
    def test_left_and_right_clearance(self, cfg):
        ls, rs, sf, bk, _ = _build_placed(cfg)
        union = ls.fuse(rs).fuse(sf).fuse(bk)
        bb = union.BoundingBox()
        opening_w = cfg.opening_width
        clr = cfg.slide.nominal_side_clearance
        assert bb.xmin == pytest.approx(clr, abs=0.5)
        assert opening_w - bb.xmax == pytest.approx(clr, abs=0.5)


@skipif_no_cq
class TestNoWallInterference:
    @pytest.mark.parametrize("pair", ["LS-SF", "LS-BK", "RS-SF", "RS-BK",
                                      "LS-RS", "SF-BK"])
    def test_pair_no_overlap(self, cfg, pair):
        ls, rs, sf, bk, _ = _build_placed(cfg)
        lookup = {"LS": ls, "RS": rs, "SF": sf, "BK": bk}
        a, b = pair.split("-")
        v = _intersect_vol(lookup[a], lookup[b])
        assert v == pytest.approx(0.0, abs=0.5), \
            f"{pair} interference {v:.1f} mm³ for joinery={cfg.joinery_style.value}"


@skipif_no_cq
class TestBottomDadoEngagement:
    """The bottom panel intersected with each wall's pre-cut *envelope* (not the
    cut wall — the dado removes wall material where the bottom sits) should
    equal the theoretical engagement volume = dado_depth × span × bt_thickness."""

    def test_engages_all_four_walls(self, cfg):
        x0 = cfg.slide.nominal_side_clearance
        t_s = cfg.side_thickness
        t_fb = cfg.front_back_thickness
        bd = cfg.box_depth
        bw = cfg.box_width
        bh = cfg.box_height
        bdd = cfg.bottom_dado_depth
        bt_thk = cfg.bottom_thickness
        engagement_x = cfg.joinery.engagement_x
        interior_w = bw - 2 * (t_s - engagement_x)

        _, _, _, _, bt = _build_placed(cfg)

        ls_env = _envelope(x0, 0, 0, t_s, bd, bh)
        rs_env = _envelope(x0 + bw - t_s, 0, 0, t_s, bd, bh)
        sf_env = _envelope(x0 + t_s - engagement_x, 0, 0, interior_w, t_fb, bh)
        bk_env = _envelope(x0 + t_s - engagement_x, bd - t_fb, 0,
                           interior_w, t_fb, bh)

        # Sides: bottom span = bottom_panel_depth (front/back take the rest).
        bp_d = cfg.bottom_panel_depth
        # Front/back span: bottom is bottom_panel_width wide; the f/b dado
        # spans interior_w. The narrower of the two bounds engagement.
        bp_w = cfg.bottom_panel_width
        fb_span = min(bp_w, interior_w)

        exp_lr = bdd * bp_d * bt_thk
        exp_fb = bdd * fb_span * bt_thk

        assert _intersect_vol(bt, ls_env) == pytest.approx(exp_lr, abs=5.0)
        assert _intersect_vol(bt, rs_env) == pytest.approx(exp_lr, abs=5.0)
        assert _intersect_vol(bt, sf_env) == pytest.approx(exp_fb, abs=5.0)
        assert _intersect_vol(bt, bk_env) == pytest.approx(exp_fb, abs=5.0)


@skipif_no_cq
class TestBottomContainedInCarcass:
    def test_no_overhang(self, cfg):
        x0 = cfg.slide.nominal_side_clearance
        bw = cfg.box_width
        bd = cfg.box_depth
        _, _, _, _, bt = _build_placed(cfg)
        bb = bt.BoundingBox()
        # Bottom should sit inside the carcass exterior on all four edges.
        assert bb.xmin >= x0 - 0.1
        assert bb.xmax <= x0 + bw + 0.1
        assert bb.ymin >= -0.1
        assert bb.ymax <= bd + 0.1


@skipif_no_cq
class TestJointEngagement:
    """For non-BUTT styles the sub-front material must occupy the side
    panel's front-end rabbet — proves the joint actually engages."""

    def test_sub_front_fills_left_side_rabbet(self, cfg):
        if cfg.joinery_style == DrawerJoineryStyle.BUTT:
            pytest.skip("BUTT has no rabbet to fill")
        x0 = cfg.slide.nominal_side_clearance
        t_s = cfg.side_thickness
        t_fb = cfg.front_back_thickness
        bh = cfg.box_height
        engagement_x = cfg.joinery.engagement_x

        # The left-side rabbet zone in world coords:
        rabbet = _envelope(x0 + t_s - engagement_x, 0, 0,
                           engagement_x, t_fb, bh)

        _, _, sf, _, _ = _build_placed(cfg)
        # The sub-front fills the rabbet (less the bottom dado slot in z).
        # Expected fill: rabbet volume minus the slot the bottom dado removes.
        bdd = cfg.bottom_dado_depth
        bt_thk = cfg.bottom_thickness
        rabbet_vol = engagement_x * t_fb * bh
        # The sub-front bottom dado intersects the rabbet zone too:
        # in panel-local (sub-front placed at fb_x = x0 + t_s - engagement_x),
        # the rabbet's panel-local X is 0..engagement_x. The dado runs the full
        # interior_width in X (which includes 0..engagement_x). In Y the dado
        # at the inside face is t_fb-bdd..t_fb. In Z it's dz..dz+bt_thk.
        dado_in_rabbet = engagement_x * bdd * bt_thk
        expected = rabbet_vol - dado_in_rabbet

        actual = _intersect_vol(sf, rabbet)
        assert actual == pytest.approx(expected, abs=5.0), (
            f"joint engagement {actual:.1f} mm³ vs expected {expected:.1f} mm³ "
            f"for {cfg.joinery_style.value}"
        )
