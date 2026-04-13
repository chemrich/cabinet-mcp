"""Tests for the visualize module.

The generate_viewer_html / _build_html path works without CadQuery installed
(only needs file I/O + base64).  Tests that require CadQuery geometry are
skipped when the library is not present.
"""

from __future__ import annotations

import base64
import json
import struct
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cadquery_furniture.visualize import _build_html, generate_viewer_html


# ── Helpers ───────────────────────────────────────────────────────────────────

def _minimal_glb() -> bytes:
    """Construct a minimal valid GLB so tests do not need real CadQuery output."""
    # JSON chunk
    json_data = json.dumps({
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": []}],
        "nodes": [],
    }).encode("utf-8")
    pad = (4 - len(json_data) % 4) % 4
    json_data += b" " * pad

    json_chunk = struct.pack("<II", len(json_data), 0x4E4F534A) + json_data  # type JSON
    total = 12 + len(json_chunk)
    header = struct.pack("<III", 0x46546C67, 2, total)  # magic, version, length
    return header + json_chunk


# ── _build_html ───────────────────────────────────────────────────────────────

class TestBuildHtml:
    def test_returns_doctype(self):
        html = _build_html("My Cabinet", "ZmFrZQ==", {})
        assert html.strip().startswith("<!DOCTYPE html>")

    def test_contains_title(self):
        html = _build_html("Kitchen Base", "ZmFrZQ==", {})
        assert "Kitchen Base" in html

    def test_embeds_b64_data(self):
        b64 = "SGVsbG9Xb3JsZA=="
        html = _build_html("Test", b64, {})
        assert b64 in html

    def test_width_height_depth_in_panel(self):
        html = _build_html("Test", "ZmFrZQ==", {"width": 600, "height": 720, "depth": 550})
        assert "600" in html
        assert "720" in html
        assert "550" in html

    def test_unknown_info_keys_rendered(self):
        html = _build_html("Test", "ZmFrZQ==", {"openings": 3})
        assert "3" in html

    def test_closes_html_tag(self):
        html = _build_html("Test", "ZmFrZQ==", {})
        assert "</html>" in html

    def test_importmap_present(self):
        html = _build_html("Test", "ZmFrZQ==", {})
        assert "importmap" in html
        assert "three" in html

    def test_gltfloader_present(self):
        html = _build_html("Test", "ZmFrZQ==", {})
        assert "GLTFLoader" in html

    def test_orbit_controls_present(self):
        html = _build_html("Test", "ZmFrZQ==", {})
        assert "OrbitControls" in html


# ── generate_viewer_html ──────────────────────────────────────────────────────

class TestGenerateViewerHtml:
    def test_creates_html_file(self, tmp_path):
        glb = tmp_path / "model.glb"
        glb.write_bytes(_minimal_glb())
        html = tmp_path / "viewer.html"

        result = generate_viewer_html(glb, html, title="Test Cabinet")

        assert result == html
        assert html.exists()

    def test_returns_resolved_path(self, tmp_path):
        glb = tmp_path / "model.glb"
        glb.write_bytes(_minimal_glb())
        html = tmp_path / "viewer.html"

        result = generate_viewer_html(glb, html)

        assert result.is_absolute()

    def test_embeds_glb_as_base64(self, tmp_path):
        glb_data = _minimal_glb()
        glb = tmp_path / "model.glb"
        glb.write_bytes(glb_data)
        html = tmp_path / "viewer.html"

        generate_viewer_html(glb, html)

        expected_b64 = base64.b64encode(glb_data).decode("ascii")
        content = html.read_text()
        assert expected_b64 in content

    def test_title_appears_in_html(self, tmp_path):
        glb = tmp_path / "model.glb"
        glb.write_bytes(_minimal_glb())
        html = tmp_path / "viewer.html"

        generate_viewer_html(glb, html, title="My Fancy Cabinet")

        assert "My Fancy Cabinet" in html.read_text()

    def test_cabinet_info_dimensions_appear(self, tmp_path):
        glb = tmp_path / "model.glb"
        glb.write_bytes(_minimal_glb())
        html = tmp_path / "viewer.html"

        generate_viewer_html(
            glb, html,
            cabinet_info={"width": 900, "height": 800, "depth": 600},
        )

        content = html.read_text()
        assert "900" in content
        assert "800" in content
        assert "600" in content

    def test_creates_parent_directories(self, tmp_path):
        glb = tmp_path / "model.glb"
        glb.write_bytes(_minimal_glb())
        nested = tmp_path / "a" / "b" / "c" / "viewer.html"

        generate_viewer_html(glb, nested)

        assert nested.exists()

    def test_no_info_dict_produces_valid_html(self, tmp_path):
        glb = tmp_path / "model.glb"
        glb.write_bytes(_minimal_glb())
        html = tmp_path / "viewer.html"

        generate_viewer_html(glb, html)  # no cabinet_info

        content = html.read_text()
        assert "<!DOCTYPE html>" in content

    def test_string_paths_accepted(self, tmp_path):
        """Path-like strings should work as well as Path objects."""
        glb = tmp_path / "model.glb"
        glb.write_bytes(_minimal_glb())
        html_str = str(tmp_path / "viewer.html")

        result = generate_viewer_html(str(glb), html_str)

        assert Path(result).exists()

    def test_utf8_encoding(self, tmp_path):
        glb = tmp_path / "model.glb"
        glb.write_bytes(_minimal_glb())
        html = tmp_path / "viewer.html"

        generate_viewer_html(glb, html, title="Küche")

        # Must be readable as UTF-8 without exception
        content = html.read_text(encoding="utf-8")
        assert "Küche" in content


# ── export_glb (requires CadQuery) ───────────────────────────────────────────

class TestExportGlb:
    def test_raises_without_cadquery(self, tmp_path):
        """ImportError when cadquery is not installed."""
        import cadquery_furniture.visualize as viz

        original = viz.cq
        viz.cq = None
        try:
            with pytest.raises(ImportError, match="cadquery is required"):
                viz.export_glb(MagicMock(), tmp_path / "out.glb")
        finally:
            viz.cq = original

    @pytest.mark.skipif(
        __import__("importlib").util.find_spec("cadquery") is None,
        reason="cadquery not installed",
    )
    def test_export_produces_glb(self, tmp_path):
        """Integration: build a real cabinet and export to GLB."""
        import cadquery as cq
        from cadquery_furniture.cabinet import CabinetConfig, build_cabinet
        from cadquery_furniture.visualize import export_glb

        cfg = CabinetConfig(width=400, height=500, depth=350)
        assy, _ = build_cabinet(cfg)
        glb = tmp_path / "test.glb"
        result = export_glb(assy, glb)

        assert result == glb
        assert glb.exists()
        assert glb.stat().st_size > 0
        # GLB magic number: 0x46546C67 ("glTF")
        magic = glb.read_bytes()[:4]
        assert magic == b"glTF"


# ── build_and_visualize (requires CadQuery) ───────────────────────────────────

class TestBuildAndVisualize:
    def test_raises_without_cadquery(self, tmp_path):
        import cadquery_furniture.visualize as viz

        original = viz.cq
        viz.cq = None
        try:
            from cadquery_furniture.cabinet import CabinetConfig
            with pytest.raises(ImportError, match="cadquery is required"):
                viz.build_and_visualize(CabinetConfig(), output_dir=tmp_path)
        finally:
            viz.cq = original

    @pytest.mark.skipif(
        __import__("importlib").util.find_spec("cadquery") is None,
        reason="cadquery not installed",
    )
    def test_returns_correct_keys(self, tmp_path):
        from cadquery_furniture.cabinet import CabinetConfig
        from cadquery_furniture.visualize import build_and_visualize

        cfg = CabinetConfig(width=400, height=500, depth=350)
        result = build_and_visualize(cfg, output_dir=tmp_path, open_browser=False)

        assert "glb"  in result
        assert "html" in result
        assert "parts" in result
        assert "glb_size_kb" in result

    @pytest.mark.skipif(
        __import__("importlib").util.find_spec("cadquery") is None,
        reason="cadquery not installed",
    )
    def test_output_files_exist(self, tmp_path):
        from cadquery_furniture.cabinet import CabinetConfig
        from cadquery_furniture.visualize import build_and_visualize

        cfg = CabinetConfig(width=400, height=500, depth=350)
        result = build_and_visualize(
            cfg, output_dir=tmp_path, name="test_cab", open_browser=False
        )

        assert Path(result["glb"]).exists()
        assert Path(result["html"]).exists()

    @pytest.mark.skipif(
        __import__("importlib").util.find_spec("cadquery") is None,
        reason="cadquery not installed",
    )
    def test_html_is_self_contained(self, tmp_path):
        """The HTML must not reference the GLB by file path — only via base64."""
        from cadquery_furniture.cabinet import CabinetConfig
        from cadquery_furniture.visualize import build_and_visualize

        cfg = CabinetConfig(width=400, height=500, depth=350)
        result = build_and_visualize(
            cfg, output_dir=tmp_path, name="check_cab", open_browser=False
        )

        html_content = Path(result["html"]).read_text()
        glb_filename  = Path(result["glb"]).name
        # The viewer should NOT load the GLB by filename — it's embedded
        assert f'"{glb_filename}"' not in html_content
        assert f"'{glb_filename}'" not in html_content
        # Instead it must contain base64 data
        assert "GLB_B64" in html_content
