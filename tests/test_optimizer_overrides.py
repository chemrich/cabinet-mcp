"""Per-group optimizer mixing — resolution precedence and behavior."""

import asyncio
import json

import pytest

from cabineteer.server import (
    _parse_optimizer_overrides,
    _resolve_group_algorithm,
    _tool_generate_cutlist,
)


def _await(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    # The cutlist tool writes real files under Path.home()/.cabineteer —
    # keep every run out of the user's actual store (review 2026-07-29 M9).
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


class TestResolution:
    OV = {"baltic_birch@6": "opcut", "rift_white_oak_ply": "rips_first",
          "@12": "strip"}

    def test_material_at_thickness_wins(self):
        assert _resolve_group_algorithm(
            "baltic_birch", 6, self.OV, "auto") == "opcut"

    def test_material_matches_any_thickness(self):
        assert _resolve_group_algorithm(
            "rift_white_oak_ply", 18, self.OV, "auto") == "rips_first"

    def test_thickness_wildcard(self):
        assert _resolve_group_algorithm(
            "baltic_birch_prefinished", 12, self.OV, "auto") == "strip"

    def test_default_when_no_match(self):
        assert _resolve_group_algorithm(
            "baltic_birch", 18, self.OV, "opcut") == "opcut"
        assert _resolve_group_algorithm("x", 9, {}, "auto") == "auto"

    def test_precedence_order(self):
        ov = {"baltic_birch@6": "opcut", "baltic_birch": "strip",
              "@6": "rips_first"}
        assert _resolve_group_algorithm("baltic_birch", 6, ov, "auto") == "opcut"
        del ov["baltic_birch@6"]
        assert _resolve_group_algorithm("baltic_birch", 6, ov, "auto") == "strip"
        del ov["baltic_birch"]
        assert _resolve_group_algorithm(
            "baltic_birch", 6, ov, "auto") == "rips_first"

    def test_bad_algorithm_rejected(self):
        with pytest.raises(ValueError, match="must be one of"):
            _parse_optimizer_overrides({"@6": "fastest"})


class TestMixedRun:
    def test_groups_use_their_own_algorithms(self):
        d = json.loads(_await(_tool_generate_cutlist({
            "name": "eval_optmix", "width": 800, "height": 700, "depth": 457,
            "carcass_material": "rift_white_oak_ply",
            "drawer_config": [[300, "drawer"], [364, "drawer"]],
            "optimizer": "rips_first",
            # 'strip' is always installed, so this test runs in lite CI;
            # Charlie's real mix uses opcut for the 6 mm groups.
            "optimizer_overrides": {"@6": "strip"},
        }))[0].text)
        algs = {g["material"]: g.get("algorithm")
                for g in d.get("sheet_goods", [])
                if g.get("sheets_used") is not None}
        oak = next(v for k, v in algs.items() if "Oak" in k)
        six = next(v for k, v in algs.items() if '1/4"' in k)
        assert oak == "rips_first"
        assert six == "strip"
