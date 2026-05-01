"""Drawer panel orientation tests.

Verify that the bottom dado and side-panel rabbet land on the INSIDE face of
every drawer panel after placement in the assembly.  The same panel-builder
function is called for both left/right sides; previously the cuts ended up on
the outside face for one of the two side panels (and the sub-front).

The sub-front / back panels no longer carry corner channels — in the simplified
rabbet model the side rabbet alone forms the joint and the f/b body fills it.
See ``test_drawer_assembly.py`` for the full assembly-level verification.
"""

import importlib.util

import pytest

from cadquery_furniture.drawer import (
    DrawerConfig,
    make_drawer_front_back,
    make_drawer_side,
)
from cadquery_furniture.joinery import DrawerJoineryStyle


cq_missing = importlib.util.find_spec("cadquery") is None
skipif_no_cq = pytest.mark.skipif(cq_missing, reason="cadquery not installed")


def _slab(x, y, z, dx, dy, dz):
    import cadquery as cq
    return (
        cq.Workplane("XY")
        .transformed(offset=(x, y, z))
        .box(dx, dy, dz, centered=False)
    )


def _intersect_volume(panel_wp, probe_wp) -> float:
    """Volume of material common to ``panel_wp`` and ``probe_wp`` (mm³).

    Returns 0.0 when the intersection is empty.
    """
    result = panel_wp.val().intersect(probe_wp.val())
    try:
        return result.Volume()
    except Exception:
        return 0.0


@pytest.fixture
def cfg_butt():
    return DrawerConfig(
        opening_width=600, opening_height=200, opening_depth=500,
        joinery_style=DrawerJoineryStyle.BUTT,
    )


@pytest.fixture
def cfg_half_lap():
    return DrawerConfig(
        opening_width=600, opening_height=200, opening_depth=500,
        joinery_style=DrawerJoineryStyle.HALF_LAP,
    )


# ── Bottom-dado face (BUTT joinery, so corner cuts don't interfere) ─────────

@skipif_no_cq
class TestBottomDadoOnInsideFace:
    """Each panel's bottom dado must be cut into its inside face."""

    def test_left_side(self, cfg_butt):
        cfg = cfg_butt
        panel = make_drawer_side(cfg, side="left")
        bdd, bt, dz = cfg.bottom_dado_depth, cfg.bottom_thickness, cfg.bottom_dado_inset
        t_s, bd = cfg.side_thickness, cfg.box_depth

        # Inside face = HIGH X (panel-local), where left side meets the drawer interior.
        inside = _slab(t_s - bdd, 0, dz, bdd, bd, bt)
        assert _intersect_volume(panel, inside) < 1.0

        outside = _slab(0, 0, dz, bdd, bd, bt)
        assert _intersect_volume(panel, outside) == pytest.approx(bdd * bd * bt, abs=1.0)

    def test_right_side(self, cfg_butt):
        cfg = cfg_butt
        panel = make_drawer_side(cfg, side="right")
        bdd, bt, dz = cfg.bottom_dado_depth, cfg.bottom_thickness, cfg.bottom_dado_inset
        t_s, bd = cfg.side_thickness, cfg.box_depth

        # Inside face = LOW X (panel-local) for the right wall.
        inside = _slab(0, 0, dz, bdd, bd, bt)
        assert _intersect_volume(panel, inside) < 1.0

        outside = _slab(t_s - bdd, 0, dz, bdd, bd, bt)
        assert _intersect_volume(panel, outside) == pytest.approx(bdd * bd * bt, abs=1.0)

    def test_back(self, cfg_butt):
        cfg = cfg_butt
        panel = make_drawer_front_back(cfg, position="back")
        bdd, bt, dz = cfg.bottom_dado_depth, cfg.bottom_thickness, cfg.bottom_dado_inset
        t_fb = cfg.front_back_thickness
        interior = cfg.box_width - 2 * cfg.side_thickness

        # Inside face = LOW Y (panel-local) for the back wall.
        inside = _slab(0, 0, dz, interior, bdd, bt)
        assert _intersect_volume(panel, inside) < 1.0

        outside = _slab(0, t_fb - bdd, dz, interior, bdd, bt)
        assert _intersect_volume(panel, outside) == pytest.approx(interior * bdd * bt, abs=1.0)

    def test_sub_front(self, cfg_butt):
        cfg = cfg_butt
        panel = make_drawer_front_back(cfg, position="front")
        bdd, bt, dz = cfg.bottom_dado_depth, cfg.bottom_thickness, cfg.bottom_dado_inset
        t_fb = cfg.front_back_thickness
        interior = cfg.box_width - 2 * cfg.side_thickness

        # Inside face = HIGH Y (panel-local) for the sub-front.
        inside = _slab(0, t_fb - bdd, dz, interior, bdd, bt)
        assert _intersect_volume(panel, inside) < 1.0

        outside = _slab(0, 0, dz, interior, bdd, bt)
        assert _intersect_volume(panel, outside) == pytest.approx(interior * bdd * bt, abs=1.0)


# ── Side rabbet on inside face (HALF_LAP, the default style) ─────────────────

@skipif_no_cq
class TestSideRabbetOnInsideFace:
    """The side panel's rabbet (engagement_x deep, full front_back_thickness
    deep in Y) must be cut on the inside face for both left and right panels.

    The probe sits above the bottom dado so the bottom-dado cut never
    interferes with the rabbet-volume calculation.
    """

    def _z_probe(self, cfg):
        return cfg.bottom_dado_inset + cfg.bottom_thickness + 1.0

    def test_left_side(self, cfg_half_lap):
        cfg = cfg_half_lap
        panel = make_drawer_side(cfg, side="left")
        dx = cfg.joinery.engagement_x
        dy = cfg.front_back_thickness
        t_s = cfg.side_thickness
        z, h = self._z_probe(cfg), 5.0

        # Inside face (high-X) front corner rabbet is empty.
        inside = _slab(t_s - dx, 0, z, dx, dy, h)
        assert _intersect_volume(panel, inside) < 1.0

        # Outside face (low-X) at the same Y/Z is solid.
        outside = _slab(0, 0, z, dx, dy, h)
        assert _intersect_volume(panel, outside) == pytest.approx(dx * dy * h, abs=1.0)

    def test_right_side(self, cfg_half_lap):
        cfg = cfg_half_lap
        panel = make_drawer_side(cfg, side="right")
        dx = cfg.joinery.engagement_x
        dy = cfg.front_back_thickness
        t_s = cfg.side_thickness
        z, h = self._z_probe(cfg), 5.0

        inside = _slab(0, 0, z, dx, dy, h)
        assert _intersect_volume(panel, inside) < 1.0

        outside = _slab(t_s - dx, 0, z, dx, dy, h)
        assert _intersect_volume(panel, outside) == pytest.approx(dx * dy * h, abs=1.0)


# ── Sub-front / back have no corner channel ──────────────────────────────────

@skipif_no_cq
class TestSubFrontBackNoCornerChannel:
    """In the simplified rabbet model the sub-front / back is a solid panel
    (modulo the bottom dado).  No corner notch should be present."""

    def test_sub_front_corners_solid(self, cfg_half_lap):
        cfg = cfg_half_lap
        panel = make_drawer_front_back(cfg, position="front")
        engagement_x = cfg.joinery.engagement_x
        # Probe a slab at the LEFT corner above the bottom dado on both faces.
        z = cfg.bottom_dado_inset + cfg.bottom_thickness + 1.0
        h = 5.0
        cy = cfg.front_back_thickness / 2  # arbitrary half-thickness probe
        inside = _slab(0, cfg.front_back_thickness - cy, z, engagement_x, cy, h)
        outside = _slab(0, 0, z, engagement_x, cy, h)
        # Both faces should be full material — no channel cut.
        assert _intersect_volume(panel, inside) == pytest.approx(
            engagement_x * cy * h, abs=1.0
        )
        assert _intersect_volume(panel, outside) == pytest.approx(
            engagement_x * cy * h, abs=1.0
        )


# ── Argument validation ─────────────────────────────────────────────────────

class TestArgValidation:
    def test_make_drawer_side_rejects_bad_side(self, cfg_butt):
        with pytest.raises(ValueError, match="left.*right"):
            make_drawer_side(cfg_butt, side="middle")

    def test_make_drawer_front_back_rejects_bad_position(self, cfg_butt):
        with pytest.raises(ValueError, match="front.*back"):
            make_drawer_front_back(cfg_butt, position="top")
