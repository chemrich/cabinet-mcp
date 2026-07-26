"""Tests for assembly.py — carcass assembly instructions — and the Domino
thickness rule they share with the hardware BOM."""

import pytest

from cadquery_furniture.assembly import (
    DRY_FIT_TENON_URL,
    build_assembly_plan,
    generate_assembly_html,
)
from cadquery_furniture.cabinet import CabinetConfig, CarcassJoinery, ColumnConfig
from cadquery_furniture.joinery import (
    DOMINO_SIZES,
    carcass_domino_size_for_thickness,
)


def _box(**kw) -> CabinetConfig:
    return CabinetConfig(width=800, height=700, depth=457, **kw)


def _two_col(**kw) -> CabinetConfig:
    return CabinetConfig(
        width=800, height=700, depth=457,
        columns=[
            ColumnConfig(width_mm=373, openings=(),
                         fixed_shelf_positions=(320,)),
            ColumnConfig(width_mm=373, openings=()),
        ], **kw)


# ─── Thickness rule + catalog data ───────────────────────────────────────────


class TestDominoThicknessRule:
    def test_18mm_ply_uses_5x30(self):
        assert carcass_domino_size_for_thickness(18.0) == "5x30"

    def test_19mm_boundary_still_5x30(self):
        assert carcass_domino_size_for_thickness(19.0) == "5x30"

    def test_thicker_stock_uses_8x40(self):
        assert carcass_domino_size_for_thickness(19.1) == "8x40"
        assert carcass_domino_size_for_thickness(25.0) == "8x40"

    def test_5x30_part_number_is_494938(self):
        # 498889 was wrong; D 5x30/300 BU is 494938 (verified Jul 2026).
        assert DOMINO_SIZES["5x30"].part_number == "494938"

    def test_5x30_pack_priced(self):
        from cadquery_furniture.hardware import price_for
        assert price_for("festool-494938") == 25.00


class TestJoineryBomFollowsRule:
    def _domino_line(self, cfg):
        from cadquery_furniture.cutlist import (
            joinery_lines_for_cabinet_config,
        )
        lines = joinery_lines_for_cabinet_config(cfg, None)
        assert len(lines) == 1
        return lines[0]

    def test_18mm_carcass_orders_5x30(self):
        line = self._domino_line(_box())
        assert line.model_number == "494938"
        assert line.pack_quantity == 300
        assert "5×30" in line.name

    def test_25mm_carcass_orders_8x40(self):
        line = self._domino_line(_box(side_thickness=25.0))
        assert line.model_number == "493298"
        assert line.pack_quantity == 780


# ─── Plan construction ───────────────────────────────────────────────────────


class TestAssemblyPlan:
    def test_simple_box_has_four_joints(self):
        plan = build_assembly_plan(_box())
        assert [j.name for j in plan.joints] == [
            "bottom ↔ left side", "bottom ↔ right side",
            "top ↔ left side", "top ↔ right side"]

    def test_edge_vs_face_parts(self):
        plan = build_assembly_plan(_box())
        j = plan.joints[0]
        assert j.edge_part == "bottom"
        assert j.face_part == "left side"

    def test_two_column_census_matches_bom(self):
        # 4 top/bottom↔side + 2 divider + 2 column-shelf = 8 — the same
        # count the hardware BOM uses (4 + 2·dividers + 2·shelves).
        plan = build_assembly_plan(_two_col())
        assert len(plan.joints) == 8

    def test_positions_measured_from_front(self):
        plan = build_assembly_plan(_box())
        s = plan.size
        first = s.min_edge_distance + s.mortise_length / 2
        assert plan.positions[0] == pytest.approx(first, abs=0.1)
        assert plan.positions[-1] == pytest.approx(plan.span - first, abs=0.1)
        assert list(plan.positions) == sorted(plan.positions)

    def test_span_is_interior_depth(self):
        cfg = _box()
        plan = build_assembly_plan(cfg)
        assert plan.span == pytest.approx(cfg.interior_depth)

    def test_18mm_plan_uses_5x30(self):
        plan = build_assembly_plan(_box())
        assert plan.size_key == "5x30"
        assert plan.size.part_number == "494938"

    def test_consumables_math(self):
        plan = build_assembly_plan(_two_col(), copies=3)
        assert plan.tenons_per_cabinet == plan.per_joint * 8
        assert plan.tenons_total == plan.tenons_per_cabinet * 3
        # PETG dry-fit prints cover one cabinet at a time.
        assert plan.dry_fit_tenons_needed == plan.tenons_per_cabinet

    def test_non_tenon_carcass_rejected(self):
        with pytest.raises(ValueError, match="floating-tenon"):
            build_assembly_plan(
                _box(carcass_joinery=CarcassJoinery.DADO_RABBET))

    def test_divider_map_uses_interior_height(self):
        cfg = _two_col()
        plan = build_assembly_plan(cfg)
        div = next(p for p in plan.panels if "divider" in p.panel)
        assert div.draw_height == pytest.approx(cfg.interior_height)

    def test_part_ids_flow_to_maps(self):
        plan = build_assembly_plan(_box(), id_map={"side": "A-S1"})
        side = next(p for p in plan.panels if p.panel.startswith("side"))
        assert side.part_id == "A-S1"

    def test_dry_fit_precedes_glue_up(self):
        plan = build_assembly_plan(_box())
        titles = [s.title for s in plan.steps]
        dry = next(i for i, t in enumerate(titles) if "DRY FIT" in t)
        glue = next(i for i, t in enumerate(titles) if "Glue up" in t)
        assert dry < glue


# ─── Renderers ───────────────────────────────────────────────────────────────


class TestRenderers:
    def test_html_cites_dry_fit_model(self):
        plan = build_assembly_plan(_box())
        html = generate_assembly_html([plan], "proj")
        assert DRY_FIT_TENON_URL in html
        assert "paulengel" in html
        assert "DRY FIT" in html

    def test_html_shows_positions_and_part_number(self):
        plan = build_assembly_plan(_box())
        html = generate_assembly_html([plan], "proj")
        assert "494938" in html
        for p in plan.positions:
            assert f"{p:.0f}" in html

    def test_pdf_renders(self):
        pytest.importorskip("reportlab")
        from cadquery_furniture.assembly import generate_assembly_pdf
        plan = build_assembly_plan(_two_col())
        pdf = generate_assembly_pdf([plan], "proj")
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 5000


# ─── Cutlist divider construction ────────────────────────────────────────────


class TestDividerConstruction:
    def _divider(self, cfg):
        from cadquery_furniture.server import _raw_panels_for_cabinet
        carcass, _, _, _ = _raw_panels_for_cabinet(
            cfg, [{"width_mm": 373, "openings": [],
                   "fixed_shelf_positions": []},
                  {"width_mm": 373, "openings": []}])
        return next(p for p in carcass if p.name == "column_divider")

    def test_tenon_divider_cut_to_interior_height(self):
        div = self._divider(_two_col())
        assert div.length == pytest.approx(700 - 18 - 18)

    def test_dado_divider_keeps_full_height(self):
        div = self._divider(
            _two_col(carcass_joinery=CarcassJoinery.DADO_RABBET))
        assert div.length == pytest.approx(700)
