"""Tests for the wood-finish option on the HTML viewer.

All tests here exercise the pure-Python HTML templating path — no CadQuery
required — except the final integration test, which is skipped in lite mode.
"""

import json

import pytest

from cadquery_furniture.visualize import (
    DEFAULT_DRAWER_BOX_FINISH,
    WOOD_FINISHES,
    _build_html,
    _finish_params,
    _grain_direction,
)

GLB_B64 = "AAAA"  # placeholder payload; templating never decodes it


def _embedded(key, direction="vertical"):
    """The JSON blob _build_html embeds for a finish key."""
    return json.dumps({**WOOD_FINISHES[key], "grain_direction": direction})


class TestFinishParams:
    def test_none_returns_none(self):
        assert _finish_params(None) is None
        assert _finish_params("") is None
        assert _finish_params("none") is None

    def test_known_keys_resolve(self):
        for key in WOOD_FINISHES:
            assert _finish_params(key) is WOOD_FINISHES[key]

    def test_unknown_key_raises_with_available_list(self):
        with pytest.raises(ValueError, match="Unknown finish 'chrome'"):
            _finish_params("chrome")
        with pytest.raises(ValueError, match="rift_white_oak"):
            _finish_params("chrome")

    def test_preset_structure(self):
        for key, p in WOOD_FINISHES.items():
            assert len(p["base"]) == 3, key
            for c in p["base"]:
                assert c.startswith("#") and len(c) == 7, key
            assert len(p["grain_lo"]) == 3 and len(p["grain_hi"]) == 3, key
            assert len(p["grain_alpha"]) == 2, key
            assert len(p["fleck_rgba"]) == 5, key
            assert p["scale_u"] > 0 and p["scale_v"] > 0, key
            assert 0 < p["roughness"] <= 1, key
            assert p["label"], key
            if "fleck_size" in p:
                assert len(p["fleck_size"]) == 4, key
            if p.get("pattern") == "cathedral":
                assert len(p["arch_gap"]) == 2 and len(p["arch_spread"]) == 2, key

    def test_expected_catalogue(self):
        assert set(WOOD_FINISHES) == {
            "rift_white_oak", "flat_sawn_white_oak", "maple", "walnut",
            "black_walnut", "bamboo", "baltic_birch", "cherry",
        }
        assert WOOD_FINISHES["flat_sawn_white_oak"]["pattern"] == "cathedral"
        assert WOOD_FINISHES["black_walnut"]["label"] == "Black Walnut"
        assert "fleck_size" in WOOD_FINISHES["bamboo"]  # node knuckles


class TestGrainDirection:
    def test_default_and_valid_values(self):
        assert _grain_direction(None) == "vertical"
        assert _grain_direction("") == "vertical"
        assert _grain_direction("vertical") == "vertical"
        assert _grain_direction("horizontal") == "horizontal"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError, match="Unknown grain_direction"):
            _grain_direction("diagonal")

    def test_direction_embedded_as_initial_grain(self):
        html = _build_html(
            "t", GLB_B64, {}, finish="maple", grain_direction="horizontal"
        )
        assert 'const INITIAL_GRAIN = "horizontal";' in html

    def test_drawer_boxes_always_horizontal(self):
        for direction in ("vertical", "horizontal"):
            html = _build_html(
                "t", GLB_B64, {}, finish="maple", grain_direction=direction
            )
            box = _embedded(DEFAULT_DRAWER_BOX_FINISH, "horizontal")
            assert f"const BOX_FINISH = {box};" in html


class TestBuildHtml:
    def test_default_embeds_null_initial_finish(self):
        html = _build_html("t", GLB_B64, {})
        assert "const INITIAL_FINISH = null;" in html
        # The full catalogue ships regardless so the dropdown works, and the
        # boxes carry baltic birch for when a finish is picked live.
        assert f"const FINISHES = {json.dumps(WOOD_FINISHES)};" in html
        box = _embedded(DEFAULT_DRAWER_BOX_FINISH, "horizontal")
        assert f"const BOX_FINISH = {box};" in html
        assert "function setShowFinish(key)" in html
        assert "classifyWood(model);" in html

    def test_finish_sets_initial_selection(self):
        for key in WOOD_FINISHES:
            html = _build_html("t", GLB_B64, {}, finish=key)
            assert f'const INITIAL_FINISH = "{key}";' in html, key

    def test_unknown_finish_raises(self):
        with pytest.raises(ValueError, match="Unknown finish"):
            _build_html("t", GLB_B64, {}, finish="chrome")

    def test_explicit_drawer_box_finish_overrides_default(self):
        html = _build_html(
            "t", GLB_B64, {}, finish="rift_white_oak", drawer_box_finish="walnut"
        )
        assert f"const BOX_FINISH = {_embedded('walnut', 'horizontal')};" in html

    def test_unknown_drawer_box_finish_raises(self):
        with pytest.raises(ValueError, match="Unknown finish"):
            _build_html("t", GLB_B64, {}, finish="cherry", drawer_box_finish="chrome")

    def test_finish_js_braces_survive_templating(self):
        # The JS block is interpolated into an f-string template; a stray
        # doubled brace would corrupt it.  Spot-check literal JS fragments.
        html = _build_html("t", GLB_B64, {}, finish="rift_white_oak")
        assert "tex.wrapS = tex.wrapT = THREE.RepeatWrapping;" in html
        assert "geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));" in html
        assert "if (/pull/i.test(nm)) { isHardware = true; break; }" in html
        assert r"/^bay\d+_drawer\d+(?:_\d+)?$/" in html  # drawer-box ancestry regex


class TestViewerControls:
    def test_ui_elements_present(self):
        html = _build_html("t", GLB_B64, {})
        assert 'id="finish-sel"' in html
        assert 'id="grain-btn"' in html
        assert 'id="cutlist-btn"' in html
        assert 'id="cutlist-modal"' in html
        assert "initFinishUI();" in html

    def test_cutlist_prompt_embedded(self):
        html = _build_html(
            "t", GLB_B64, {}, cutlist_prompt="Generate the project cutlist for 'x'."
        )
        assert (
            "const CUTLIST_PROMPT = \"Generate the project cutlist for 'x'.\";"
            in html
        )

    def test_cutlist_prompt_defaults_generic(self):
        html = _build_html("t", GLB_B64, {})
        assert 'const CUTLIST_PROMPT = "Generate the cutlist for this design.";' in html

    def test_keyboard_shortcuts_guard_form_controls(self):
        html = _build_html("t", GLB_B64, {})
        assert "/^(SELECT|INPUT|TEXTAREA|BUTTON)$/.test(e.target.tagName)" in html


class TestVisualizeCabinetHandler:
    def test_handler_forwards_finish(self, tmp_path):
        pytest.importorskip("cadquery")
        import asyncio

        from cadquery_furniture import server as srv

        out = asyncio.run(srv._tool_visualize_cabinet({
            "width": 305, "height": 300, "depth": 300,
            "drawer_config": [[264, "drawer"]],
            "finish": "rift_white_oak",
            "name": "finish_test",
            "output_dir": str(tmp_path),
            "open_browser": False,
        }))
        result = json.loads(out[0].text)
        html = (tmp_path / "finish_test_viewer.html").read_text()
        assert "Rift-Sawn White Oak" in html
        assert '"scale_u": 250'.replace(" ", "") in html.replace(" ", "")
        # Drawer boxes default to baltic birch and show in the info panel.
        assert "Baltic Birch (WB urethane)" in html
        assert "Drawer boxes" in html
        # The cutlist button carries a cabinet-specific request.
        assert "Generate the cutlist for cabinet 'finish_test'" in html
        assert result["parts"] > 0
