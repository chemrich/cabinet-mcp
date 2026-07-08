"""Tests for the wood-finish option on the HTML viewer.

All tests here exercise the pure-Python HTML templating path — no CadQuery
required — except the final integration test, which is skipped in lite mode.
"""

import json

import pytest

from cadquery_furniture.visualize import (
    WOOD_FINISHES,
    _build_html,
    _finish_params,
)

GLB_B64 = "AAAA"  # placeholder payload; templating never decodes it


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


class TestBuildHtml:
    def test_default_embeds_null_finish(self):
        html = _build_html("t", GLB_B64, {})
        assert "const FINISH = null;" in html
        # The applicator ships regardless but is a no-op on null.
        assert "function applyWoodFinish(root)" in html
        assert "applyWoodFinish(model);" in html

    def test_finish_embeds_params(self):
        for key, params in WOOD_FINISHES.items():
            html = _build_html("t", GLB_B64, {}, finish=key)
            assert f"const FINISH = {json.dumps(params)};" in html, key

    def test_unknown_finish_raises(self):
        with pytest.raises(ValueError, match="Unknown finish"):
            _build_html("t", GLB_B64, {}, finish="chrome")

    def test_finish_js_braces_survive_templating(self):
        # The JS block is interpolated into an f-string template; a stray
        # doubled brace would corrupt it.  Spot-check literal JS fragments.
        html = _build_html("t", GLB_B64, {}, finish="rift_white_oak")
        assert "tex.wrapS = tex.wrapT = THREE.RepeatWrapping;" in html
        assert "geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));" in html
        assert "if (/pull/i.test(n.name || ''))" in html


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
        assert result["parts"] > 0
