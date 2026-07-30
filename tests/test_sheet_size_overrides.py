"""Per-material sheet-size overrides — only the named stock changes size."""

import asyncio
import json


def _await(coro):
    # Match the repo's loop convention (test_visualize uses get_event_loop);
    # asyncio.run() would close the thread loop and break later test files.
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

import pytest

from cabineteer.server import (
    _parse_sheet_size_overrides,
    _tool_generate_cutlist,
)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    # The cutlist tool writes real files under Path.home()/.cabineteer —
    # keep every run out of the user's actual store (review 2026-07-29 M9).
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


def _run(extra):
    args = {
        "name": "eval_sheetsize", "width": 1219.2, "height": 663.6,
        "depth": 457, "carcass_material": "rift_white_oak_ply",
        "drawer_config": [[300, "drawer"], [327.6, "drawer"]],
        # Deliberately too short for the 1219.2-wide cabinet's panels so
        # only an override can place the oak group.
        "sheet_length": 1000, "sheet_width": 1234,
        **extra,
    }
    d = json.loads(_await(_tool_generate_cutlist(args))[0].text)
    groups = {}
    for g in d.get("sheet_goods", []):
        groups[str(g.get("material"))] = g
    return groups


class TestSheetSizeOverrides:
    def test_oak_unplaced_without_override(self):
        groups = _run({})
        oak = next(v for k, v in groups.items() if "oak" in k.lower())
        assert oak["unplaced"], "1219 mm panels cannot fit a 1000 mm sheet"

    def test_override_rescues_only_named_material(self):
        groups = _run({"sheet_size_overrides":
                       {"rift_white_oak_ply": [2453, 1234]}})
        oak = next(v for k, v in groups.items() if "oak" in k.lower())
        assert oak["unplaced"] == []
        # Baltic birch groups still pack on the small default sheet.
        bb = [v for k, v in groups.items() if "oak" not in k.lower() and v.get("sheets_used") is not None]
        assert bb and all(g["unplaced"] == [] for g in bb)

    def test_non_matching_override_changes_nothing(self):
        base = _run({})
        other = _run({"sheet_size_overrides": {"walnut_ply": [2453, 1234]}})
        oak_b = next(v for k, v in base.items() if "oak" in k.lower())
        oak_o = next(v for k, v in other.items() if "oak" in k.lower())
        assert oak_b["sheets_used"] == oak_o["sheets_used"]
        assert bool(oak_b["unplaced"]) and bool(oak_o["unplaced"])


class TestOverrideParsing:
    def test_valid(self):
        out = _parse_sheet_size_overrides(
            {"rift_white_oak_ply": [2453, 1234]})
        assert out == {"rift_white_oak_ply": (2453.0, 1234.0)}

    def test_none_empty(self):
        assert _parse_sheet_size_overrides(None) == {}
        assert _parse_sheet_size_overrides({}) == {}

    def test_bad_shape_rejected(self):
        with pytest.raises(ValueError, match="must be \\[length_mm"):
            _parse_sheet_size_overrides({"oak": [2453]})

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            _parse_sheet_size_overrides({"oak": [-1, 1234]})
