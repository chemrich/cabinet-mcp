"""Tests for hardware BOM plumbing (Phase 5).

Covers HardwareLine pack-quantity math, the per-config pull extractors
(drawer, door), the cabinet-level extractor, consolidation, and the
CSV/JSON/console output formats.
"""

import csv
import io
import json

import pytest

from cadquery_furniture.cabinet import CabinetConfig, ColumnConfig
from cadquery_furniture.door import DoorConfig
from cadquery_furniture.drawer import DrawerConfig
from cadquery_furniture.cutlist import (
    HardwareLine,
    consolidate_hardware_lines,
    print_hardware_bom,
    pull_line_from_door,
    pull_line_from_drawer,
    pull_lines_for_cabinet_config,
    to_hardware_csv,
    to_hardware_json,
)


# ─── HardwareLine math ───────────────────────────────────────────────────────


class TestHardwareLineMath:
    def test_single_pack_exact(self):
        line = HardwareLine(
            sku="x", category="pull", name="X", brand="B",
            model_number="M", pieces_needed=4, pack_quantity=1,
        )
        assert line.packs_to_order == 4
        assert line.pieces_ordered == 4
        assert line.leftover == 0

    def test_two_pack_exact(self):
        # 4 pieces needed, 2 per pack → 2 packs, 0 leftover
        line = HardwareLine(
            sku="x", category="pull", name="X", brand="B",
            model_number="M", pieces_needed=4, pack_quantity=2,
        )
        assert line.packs_to_order == 2
        assert line.pieces_ordered == 4
        assert line.leftover == 0

    def test_two_pack_rounds_up(self):
        # 3 pieces needed, 2 per pack → 2 packs, 1 leftover
        line = HardwareLine(
            sku="x", category="pull", name="X", brand="B",
            model_number="M", pieces_needed=3, pack_quantity=2,
        )
        assert line.packs_to_order == 2
        assert line.pieces_ordered == 4
        assert line.leftover == 1

    def test_zero_pieces(self):
        line = HardwareLine(
            sku="x", category="pull", name="X", brand="B",
            model_number="M", pieces_needed=0, pack_quantity=2,
        )
        assert line.packs_to_order == 0
        assert line.pieces_ordered == 0
        assert line.leftover == 0

    def test_zero_pack_quantity_treated_as_one(self):
        # Guard against catalog bugs that leave pack_quantity=0
        line = HardwareLine(
            sku="x", category="pull", name="X", brand="B",
            model_number="M", pieces_needed=5, pack_quantity=0,
        )
        assert line.packs_to_order == 5
        assert line.pieces_ordered == 5
        assert line.leftover == 0


# ─── pull_line_from_drawer ───────────────────────────────────────────────────


class TestPullLineFromDrawer:
    def test_no_pull_returns_none(self):
        d = DrawerConfig(opening_width=500, opening_height=150, opening_depth=500)
        assert pull_line_from_drawer(d) is None

    def test_single_pull(self):
        d = DrawerConfig(
            opening_width=500, opening_height=150, opening_depth=500,
            pull_key="topknobs-hb-128",
        )
        line = pull_line_from_drawer(d)
        assert line is not None
        assert line.sku == "topknobs-hb-128"
        assert line.category == "pull"
        assert line.pieces_needed == 1
        assert line.pack_quantity == 1
        assert line.brand == "Top Knobs"

    def test_dual_pull_count_propagates(self):
        d = DrawerConfig(
            opening_width=500, opening_height=150, opening_depth=500,
            pull_key="topknobs-hb-76",  # short pull — fits dual easily
            pull_count=2,
        )
        line = pull_line_from_drawer(d)
        assert line is not None
        assert line.pieces_needed == 2

    def test_applied_face_false_returns_none(self):
        d = DrawerConfig(
            opening_width=500, opening_height=150, opening_depth=500,
            pull_key="topknobs-hb-128",
            applied_face=False,
        )
        # No face → no placements → no line
        assert pull_line_from_drawer(d) is None

    def test_unknown_pull_key_returns_none(self):
        # pull_placements raises KeyError for unknown keys; the extractor
        # swallows that so unknowns don't crash BOM generation.
        d = DrawerConfig(
            opening_width=500, opening_height=150, opening_depth=500,
            pull_key="not-a-real-pull",
        )
        assert pull_line_from_drawer(d) is None


# ─── pull_line_from_door ─────────────────────────────────────────────────────


class TestPullLineFromDoor:
    def test_no_pull_returns_none(self):
        d = DoorConfig(opening_width=400, opening_height=720)
        assert pull_line_from_door(d) is None

    def test_single_door(self):
        d = DoorConfig(
            opening_width=400, opening_height=720,
            pull_key="topknobs-hb-96",
        )
        line = pull_line_from_door(d)
        assert line is not None
        assert line.sku == "topknobs-hb-96"
        assert line.pieces_needed == 1

    def test_door_pair_doubles(self):
        d = DoorConfig(
            opening_width=600, opening_height=720, num_doors=2,
            pull_key="topknobs-hb-96",
        )
        line = pull_line_from_door(d)
        assert line is not None
        # total_pull_count = placements_per_leaf * num_doors = 1 * 2
        assert line.pieces_needed == 2

    def test_unknown_pull_key_returns_none(self):
        d = DoorConfig(
            opening_width=400, opening_height=720,
            pull_key="also-not-real",
        )
        assert pull_line_from_door(d) is None

    def test_ikea_pack_quantity_propagates(self):
        # IKEA 2-pack → pack_quantity=2 should carry through
        d = DoorConfig(
            opening_width=400, opening_height=720,
            pull_key="ikea-hackas-anthracite-128",
        )
        line = pull_line_from_door(d)
        assert line is not None
        assert line.pack_quantity == 2
        assert line.pieces_needed == 1
        assert line.packs_to_order == 1
        assert line.leftover == 1


# ─── pull_lines_for_cabinet_config ───────────────────────────────────────────


class TestPullLinesForCabinetConfig:
    def test_empty_cabinet_returns_empty(self):
        cab = CabinetConfig()
        assert pull_lines_for_cabinet_config(cab) == []

    def test_cabinet_with_no_pulls_returns_empty(self):
        cab = CabinetConfig(drawer_config=[(150, "drawer"), (150, "drawer")])
        assert pull_lines_for_cabinet_config(cab) == []

    def test_drawer_stack_with_pull_consolidates(self):
        cab = CabinetConfig(
            width=600, height=720, depth=550,
            drawer_config=[(150, "drawer"), (150, "drawer"), (300, "drawer")],
            drawer_pull="topknobs-hb-128",
        )
        lines = pull_lines_for_cabinet_config(cab)
        assert len(lines) == 1
        assert lines[0].sku == "topknobs-hb-128"
        assert lines[0].pieces_needed == 3

    def test_mixed_drawer_and_door_layout(self):
        cab = CabinetConfig(
            width=600, height=720, depth=550,
            drawer_config=[(150, "drawer"), (570, "door")],
            drawer_pull="topknobs-hb-128",
            door_pull="topknobs-hb-96",
        )
        lines = pull_lines_for_cabinet_config(cab)
        skus = {l.sku: l.pieces_needed for l in lines}
        assert skus == {"topknobs-hb-128": 1, "topknobs-hb-96": 1}

    def test_door_pair_counts_two(self):
        cab = CabinetConfig(
            width=800, height=720, depth=550,
            drawer_config=[(720, "door_pair")],
            door_pull="topknobs-hb-96",
        )
        lines = pull_lines_for_cabinet_config(cab)
        assert len(lines) == 1
        assert lines[0].pieces_needed == 2

    def test_shelf_and_open_slots_contribute_nothing(self):
        cab = CabinetConfig(
            width=600, height=720, depth=550,
            drawer_config=[(300, "shelf"), (300, "open"), (120, "drawer")],
            drawer_pull="topknobs-hb-128",
        )
        lines = pull_lines_for_cabinet_config(cab)
        assert len(lines) == 1
        assert lines[0].pieces_needed == 1

    def test_unknown_keys_are_silently_skipped(self):
        # Unknown pull keys don't crash the extractor. (The evaluator's
        # pull_unknown check is responsible for warning the user.)
        cab = CabinetConfig(
            width=600, height=720, depth=550,
            drawer_config=[(150, "drawer")],
            drawer_pull="ghost-pull",
        )
        assert pull_lines_for_cabinet_config(cab) == []

    def test_column_layout_walks_columns(self):
        # Two columns: left is a drawer stack, right is a single door.
        # interior_width = 600 - 2·18 = 564, so columns must sum to 564.
        left = ColumnConfig(
            width_mm=282.0,
            drawer_config=((150.0, "drawer"), (150.0, "drawer")),
        )
        right = ColumnConfig(
            width_mm=282.0,
            drawer_config=((600.0, "door"),),
        )
        cab = CabinetConfig(
            width=600, height=720, depth=550,
            columns=[left, right],
            drawer_pull="topknobs-hb-128",
            door_pull="topknobs-hb-96",
        )
        lines = pull_lines_for_cabinet_config(cab)
        skus = {l.sku: l.pieces_needed for l in lines}
        assert skus == {"topknobs-hb-128": 2, "topknobs-hb-96": 1}


# ─── consolidate_hardware_lines ──────────────────────────────────────────────


class TestConsolidateHardwareLines:
    def _mk(self, sku, pieces, pq=1, notes=""):
        return HardwareLine(
            sku=sku, category="pull", name=sku, brand="B",
            model_number="M", pieces_needed=pieces, pack_quantity=pq,
            notes=notes,
        )

    def test_merges_same_sku(self):
        a = self._mk("x", 2)
        b = self._mk("x", 3)
        out = consolidate_hardware_lines([a, b])
        assert len(out) == 1
        assert out[0].pieces_needed == 5

    def test_preserves_first_seen_order(self):
        out = consolidate_hardware_lines([
            self._mk("b", 1), self._mk("a", 1), self._mk("b", 1),
        ])
        assert [l.sku for l in out] == ["b", "a"]

    def test_does_not_mutate_inputs(self):
        a = self._mk("x", 2)
        b = self._mk("x", 3)
        consolidate_hardware_lines([a, b])
        assert a.pieces_needed == 2
        assert b.pieces_needed == 3

    def test_concatenates_notes(self):
        a = self._mk("x", 1, notes="drawer-0")
        b = self._mk("x", 1, notes="drawer-1")
        [merged] = consolidate_hardware_lines([a, b])
        assert "drawer-0" in merged.notes
        assert "drawer-1" in merged.notes


# ─── Output formats ──────────────────────────────────────────────────────────


class TestOutputFormats:
    def _lines(self):
        return [
            HardwareLine(
                sku="topknobs-hb-128", category="pull",
                name="Top Knobs HB 128", brand="Top Knobs",
                model_number="TK-HB-128", pieces_needed=3, pack_quantity=1,
            ),
            HardwareLine(
                sku="ikea-hackas-anthracite-128", category="pull",
                name="IKEA HACKÅS", brand="IKEA",
                model_number="hackas-128", pieces_needed=3, pack_quantity=2,
                notes="door pair slot",
            ),
        ]

    def test_csv_roundtrip(self):
        csv_text = to_hardware_csv(self._lines())
        rows = list(csv.reader(io.StringIO(csv_text)))
        # Header + two data rows
        assert len(rows) == 3
        assert rows[0][0] == "SKU"
        # Row 1: pack=1, needed=3 → packs_to_order=3, leftover=0
        assert rows[1][0] == "topknobs-hb-128"
        assert rows[1][5] == "3"   # pieces_needed
        assert rows[1][7] == "3"   # packs_to_order
        assert rows[1][9] == "0"   # leftover
        # Row 2: pack=2, needed=3 → packs_to_order=2, pieces_ordered=4, leftover=1
        assert rows[2][0] == "ikea-hackas-anthracite-128"
        assert rows[2][7] == "2"
        assert rows[2][8] == "4"
        assert rows[2][9] == "1"

    def test_json_structure(self):
        doc = json.loads(to_hardware_json(self._lines()))
        assert set(doc.keys()) == {"lines", "totals"}
        assert len(doc["lines"]) == 2
        # Derived fields present
        assert doc["lines"][1]["packs_to_order"] == 2
        assert doc["lines"][1]["leftover"] == 1
        # Totals aggregate
        assert doc["totals"]["line_count"] == 2
        assert doc["totals"]["pieces_needed"] == 6
        assert doc["totals"]["packs_to_order"] == 5  # 3 + 2

    def test_print_handles_empty(self, capsys):
        print_hardware_bom([])
        captured = capsys.readouterr()
        assert "no hardware" in captured.out.lower()

    def test_print_emits_summary(self, capsys):
        print_hardware_bom(self._lines())
        captured = capsys.readouterr()
        assert "topknobs-hb-128" in captured.out
        assert "2 lines" in captured.out
