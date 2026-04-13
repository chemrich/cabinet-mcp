"""GLTF export and browser-based 3D viewer for cabinet assemblies.

Exports a CadQuery Assembly to GLB (binary GLTF) format and generates a
self-contained HTML file with a Three.js orbit viewer.  No server or internet
connection required at view-time — just open the HTML in any modern browser.

Requires CadQuery ≥ 2.4 for GLB export (``pip install cadquery``).

Typical usage
-------------
::

    from cadquery_furniture.cabinet import CabinetConfig
    from cadquery_furniture.visualize import build_and_visualize

    cfg = CabinetConfig(width=600, height=720, depth=550)
    result = build_and_visualize(cfg, output_dir="~/Desktop/cabinet_view")
    # Opens browser automatically; result["html"] has the path.
"""

from __future__ import annotations

import base64
import tempfile
import webbrowser
from pathlib import Path
from typing import Optional, TYPE_CHECKING

try:
    import cadquery as cq
except ImportError:
    cq = None  # CadQuery is an optional dependency


def _require_cq() -> None:
    if cq is None:
        raise ImportError(
            "cadquery is required for 3D export. "
            "Install with: pip install cadquery"
        )


# ── Public API ────────────────────────────────────────────────────────────────

def export_glb(
    assy: "cq.Assembly",
    output_path: "Path | str",
    tolerance: float = 0.1,
    angular_tolerance: float = 0.1,
) -> Path:
    """Export a CadQuery Assembly to GLB (binary GLTF).

    The output format is determined by the ``.glb`` extension.
    Colors assigned in the assembly are preserved as vertex colours.

    Args:
        assy: The CadQuery Assembly to export.
        output_path: Destination file (must end in ``.glb``).
        tolerance: Linear deflection tolerance for mesh tessellation (mm).
            Smaller = finer mesh, larger file.  0.05–0.2 is a good range.
        angular_tolerance: Angular deflection in radians.

    Returns:
        Resolved ``Path`` to the written file.
    """
    _require_cq()
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    assy.save(str(output_path), tolerance=tolerance, angularTolerance=angular_tolerance)
    return output_path


def generate_viewer_html(
    glb_path: "Path | str",
    output_html: "Path | str",
    title: str = "Cabinet Viewer",
    cabinet_info: Optional[dict] = None,
) -> Path:
    """Generate a self-contained Three.js HTML viewer with the GLB embedded.

    The binary GLB data is base64-encoded and inlined as a JavaScript string,
    so the resulting HTML file is completely standalone — no server, no network
    access needed when opening it.

    Args:
        glb_path: Path to the source ``.glb`` file.
        output_html: Destination ``.html`` file.
        title: Title shown in the browser tab and info panel.
        cabinet_info: Optional dict with display info.  Recognised keys:
            ``width``, ``height``, ``depth`` (all in mm), plus any arbitrary
            string keys whose values will be displayed verbatim.

    Returns:
        Resolved ``Path`` to the written HTML file.
    """
    glb_path = Path(glb_path).expanduser().resolve()
    output_html = Path(output_html).expanduser().resolve()
    output_html.parent.mkdir(parents=True, exist_ok=True)

    glb_b64 = base64.b64encode(glb_path.read_bytes()).decode("ascii")
    html = _build_html(title, glb_b64, cabinet_info or {})
    output_html.write_text(html, encoding="utf-8")
    return output_html


def visualize_assembly(
    assy: "cq.Assembly",
    parts: list,
    output_dir: "Path | str" = "~/.cabinet-mcp/visualizations",
    name: str = "cabinet",
    open_browser: bool = True,
    tolerance: float = 0.1,
    angular_tolerance: float = 0.1,
    info: Optional[dict] = None,
) -> dict:
    """Export a pre-built CadQuery Assembly to GLB and generate an HTML viewer.

    Use this when you have already called a builder function (e.g.
    ``build_multi_bay_cabinet``) and just need the export step.

    Args:
        assy:        Pre-built CadQuery Assembly.
        parts:       Parts list (used for part count).
        output_dir:  Directory for output files.
        name:        Base filename stem.
        open_browser: If True, open the HTML file in the default browser.
        tolerance:   Mesh tessellation tolerance in mm.
        angular_tolerance: Angular tessellation tolerance in radians.
        info:        Optional dict of key/value pairs shown in the info panel.

    Returns:
        Dict with keys ``glb``, ``html``, ``parts``, ``glb_size_kb``.
    """
    _require_cq()

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    glb_path  = output_dir / f"{name}.glb"
    html_path = output_dir / f"{name}_viewer.html"

    export_glb(assy, glb_path, tolerance=tolerance, angular_tolerance=angular_tolerance)

    panel_info = dict(info) if info else {}
    panel_info.setdefault("parts", len(parts))

    generate_viewer_html(
        glb_path,
        html_path,
        title=name.replace("_", " ").title(),
        cabinet_info=panel_info,
    )

    if open_browser:
        webbrowser.open(html_path.as_uri())

    return {
        "glb":         str(glb_path),
        "html":        str(html_path),
        "parts":       len(parts),
        "glb_size_kb": round(glb_path.stat().st_size / 1024, 1),
    }


def build_and_visualize(
    cfg: "CabinetConfig",  # type: ignore[name-defined]
    output_dir: "Path | str" = "~/.cabinet-mcp/visualizations",
    name: str = "cabinet",
    open_browser: bool = True,
    tolerance: float = 0.1,
    angular_tolerance: float = 0.1,
) -> dict:
    """Build a full cabinet assembly, export GLB, and generate the HTML viewer.

    Args:
        cfg: Cabinet configuration (``CabinetConfig`` instance).
        output_dir: Directory for output files (created if absent).
            Defaults to ``~/.cabinet-mcp/visualizations``.
        name: Base filename stem (e.g. ``"kitchen_base"`` →
            ``kitchen_base.glb`` + ``kitchen_base_viewer.html``).
        open_browser: If ``True``, open the HTML file in the default browser.
        tolerance: Mesh tessellation tolerance in mm (lower = finer, bigger).
        angular_tolerance: Angular tessellation tolerance in radians.

    Returns:
        Dict with keys:
        - ``"glb"``   — absolute path to the exported GLB file
        - ``"html"``  — absolute path to the generated HTML viewer
        - ``"parts"`` — number of parts in the assembly
        - ``"glb_size_kb"`` — GLB file size in KB
    """
    _require_cq()
    from .cabinet import build_cabinet

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    assy, parts = build_cabinet(cfg)

    glb_path = output_dir / f"{name}.glb"
    html_path = output_dir / f"{name}_viewer.html"

    export_glb(assy, glb_path, tolerance=tolerance, angular_tolerance=angular_tolerance)

    cabinet_info = {
        "width":  cfg.width,
        "height": cfg.height,
        "depth":  cfg.depth,
        "parts":  len(parts),
    }
    if cfg.drawer_config:
        cabinet_info["openings"] = len(cfg.drawer_config)

    generate_viewer_html(
        glb_path,
        html_path,
        title=name.replace("_", " ").title(),
        cabinet_info=cabinet_info,
    )

    if open_browser:
        webbrowser.open(html_path.as_uri())

    return {
        "glb":         str(glb_path),
        "html":        str(html_path),
        "parts":       len(parts),
        "glb_size_kb": round(glb_path.stat().st_size / 1024, 1),
    }


# ── HTML builder ──────────────────────────────────────────────────────────────

def _build_html(title: str, glb_b64: str, info: dict) -> str:
    """Construct the self-contained HTML viewer string.

    Uses Three.js r165 via importmap from the jsDelivr CDN.  The GLB data
    is embedded verbatim as a base64 string constant.
    """
    # Build info panel rows
    info_rows: list[str] = []
    if "width" in info:
        info_rows.append(f'<div class="row">W <span>{info["width"]:.0f} mm</span></div>')
    if "height" in info:
        info_rows.append(f'<div class="row">H <span>{info["height"]:.0f} mm</span></div>')
    if "depth" in info:
        info_rows.append(f'<div class="row">D <span>{info["depth"]:.0f} mm</span></div>')
    for k, v in info.items():
        if k not in ("width", "height", "depth"):
            label = k.replace("_", " ").capitalize()
            info_rows.append(f'<div class="row">{label} <span>{v}</span></div>')
    info_html = "\n    ".join(info_rows)

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ background: #16162a; overflow: hidden; font-family: system-ui, -apple-system, sans-serif; }}
    canvas {{ display: block; }}

    #panel {{
      position: absolute; top: 16px; left: 16px;
      background: rgba(10, 10, 25, 0.72);
      color: #ccc;
      padding: 14px 18px; border-radius: 10px;
      font-size: 13px; line-height: 1.0;
      backdrop-filter: blur(8px);
      border: 1px solid rgba(255, 255, 255, 0.09);
      min-width: 170px;
      user-select: none;
    }}
    #panel h2 {{
      font-size: 14px; font-weight: 600; color: #fff;
      margin-bottom: 10px; letter-spacing: 0.02em;
    }}
    .row {{
      display: flex; justify-content: space-between;
      gap: 16px; padding: 3px 0;
      color: #999; font-size: 12px;
    }}
    .row span {{ color: #f0c060; font-weight: 500; }}

    #help {{
      position: absolute; bottom: 16px; right: 20px;
      color: rgba(255, 255, 255, 0.28);
      font-size: 11px; text-align: right; line-height: 1.9;
      user-select: none;
    }}

    #loading {{
      position: absolute; top: 50%; left: 50%;
      transform: translate(-50%, -50%);
      color: #666; font-size: 15px; letter-spacing: 0.06em;
    }}
  </style>
</head>
<body>
  <div id="loading">Loading model…</div>

  <div id="panel">
    <h2>{title}</h2>
    {info_html}
  </div>

  <div id="help">
    Left-drag&nbsp;&nbsp;rotate<br>
    Right-drag&nbsp;&nbsp;pan<br>
    Scroll&nbsp;&nbsp;zoom
  </div>

  <script type="importmap">
  {{
    "imports": {{
      "three":          "https://cdn.jsdelivr.net/npm/three@0.165.0/build/three.module.js",
      "three/addons/":  "https://cdn.jsdelivr.net/npm/three@0.165.0/examples/jsm/"
    }}
  }}
  </script>

  <script type="module">
import * as THREE from 'three';
import {{ GLTFLoader }}    from 'three/addons/loaders/GLTFLoader.js';
import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';

// ── Embedded GLB (base64) ─────────────────────────────────────────────────────
const GLB_B64 = `{glb_b64}`;

function b64ToBuffer(b64) {{
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return buf.buffer;
}}

// ── Renderer ──────────────────────────────────────────────────────────────────
const renderer = new THREE.WebGLRenderer({{ antialias: true }});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
document.body.appendChild(renderer.domElement);

// ── Scene ─────────────────────────────────────────────────────────────────────
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x16162a);

// ── Camera ────────────────────────────────────────────────────────────────────
const camera = new THREE.PerspectiveCamera(
  40, window.innerWidth / window.innerHeight, 1, 50000
);

// ── Lights ────────────────────────────────────────────────────────────────────
scene.add(new THREE.AmbientLight(0xfff5ee, 0.65));

const key = new THREE.DirectionalLight(0xfff0cc, 1.9);
key.position.set(1000, 1600, 800);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.camera.near = 10;
key.shadow.camera.far  = 12000;
key.shadow.camera.left = key.shadow.camera.bottom = -2500;
key.shadow.camera.right = key.shadow.camera.top   =  2500;
scene.add(key);

const fill = new THREE.DirectionalLight(0xc0d0ff, 0.55);
fill.position.set(-800, 400, -600);
scene.add(fill);

const rim = new THREE.DirectionalLight(0xffe0a0, 0.35);
rim.position.set(0, -200, -1000);
scene.add(rim);

// ── Grid ──────────────────────────────────────────────────────────────────────
const grid = new THREE.GridHelper(5000, 50, 0x2e2e50, 0x222238);
scene.add(grid);

// ── Controls ──────────────────────────────────────────────────────────────────
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping    = true;
controls.dampingFactor    = 0.055;
controls.screenSpacePanning = true;
controls.minDistance      = 50;
controls.maxDistance      = 20000;
controls.maxPolarAngle    = Math.PI / 2 + 0.18;

// ── Load model ────────────────────────────────────────────────────────────────
new GLTFLoader().parse(b64ToBuffer(GLB_B64), '', (gltf) => {{
  const model = gltf.scene;

  model.traverse(obj => {{
    if (!obj.isMesh) return;
    obj.castShadow    = true;
    obj.receiveShadow = true;
    const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
    mats.forEach(m => {{
      if (!m) return;
      // Preserve CadQuery vertex colours; add realistic PBR properties.
      m.roughness  = 0.72;
      m.metalness  = 0.0;
    }});
  }});

  scene.add(model);

  // Sit model on grid and centre camera
  const box  = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  model.position.y -= box.min.y;          // floor it
  box.setFromObject(model);
  const centre = box.getCenter(new THREE.Vector3());

  const maxDim = Math.max(size.x, size.y, size.z);
  const fov    = camera.fov * (Math.PI / 180);
  const dist   = (maxDim / (2 * Math.tan(fov / 2))) * 2.0;

  camera.position.set(
    centre.x + dist * 0.75,
    centre.y + dist * 0.55,
    centre.z + dist * 0.75
  );
  camera.lookAt(centre);
  controls.target.copy(centre);
  controls.update();

  document.getElementById('loading').style.display = 'none';

}}, err => {{
  const el = document.getElementById('loading');
  el.textContent = 'Error loading model: ' + (err.message || err);
  el.style.color = '#f06060';
  console.error(err);
}});

// ── Render loop ───────────────────────────────────────────────────────────────
(function animate() {{
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}})();

window.addEventListener('resize', () => {{
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}});
  </script>
</body>
</html>"""
