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
import json
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


# ── Wood finishes ─────────────────────────────────────────────────────────────
#
# Parameter sets for the viewer's procedural grain generator (see
# _FINISH_JS below).  All colour panels in the scene get the texture; pull
# hardware keeps its metal material.  Keys are exposed as the `finish`
# parameter on visualize_cabinet / visualize_project.
#
#   base        — three hex colours for the horizontal background gradient
#   grain_lo/hi — RGB endpoints; each grain line lerps between them
#   grain_alpha — [min, range] stroke opacity
#   line_gap    — [min, range] px between grain lines (512 px ≈ scale_u mm)
#   line_width  — [min, range] px stroke width
#   waviness    — [min, range] px lateral drift (low = rift-sawn straightness)
#   fleck_count / fleck_rgba — pore flecks: count and [r, g, b, a_min, a_range]
#   roughness   — PBR roughness applied with the texture
#   scale_u/v   — mm of wood covered by one texture tile (across / along grain)

WOOD_FINISHES: dict[str, dict] = {
    "rift_white_oak": {
        "label": "Rift-Sawn White Oak",
        "base": ["#e6d9bd", "#ddcfae", "#e2d4b6"],
        "grain_lo": [116, 98, 65],
        "grain_hi": [166, 141, 98],
        "grain_alpha": [0.16, 0.24],
        "line_gap": [2, 9],
        "line_width": [0.6, 1.6],
        "waviness": [1.2, 1.8],
        "fleck_count": 900,
        "fleck_rgba": [120, 95, 60, 0.04, 0.07],
        "roughness": 0.62,
        "scale_u": 250,
        "scale_v": 1000,
    },
    "walnut": {
        "label": "Black Walnut",
        "base": ["#6b543f", "#5f4936", "#66503b"],
        "grain_lo": [40, 30, 22],
        "grain_hi": [92, 74, 54],
        "grain_alpha": [0.20, 0.30],
        "line_gap": [3, 12],
        "line_width": [0.8, 2.2],
        "waviness": [2.0, 3.0],
        "fleck_count": 500,
        "fleck_rgba": [32, 24, 17, 0.05, 0.08],
        "roughness": 0.55,
        "scale_u": 250,
        "scale_v": 1000,
    },
    "maple": {
        "label": "Hard Maple",
        "base": ["#f0e7d4", "#ece1cb", "#eee4d0"],
        "grain_lo": [196, 180, 150],
        "grain_hi": [220, 205, 176],
        "grain_alpha": [0.10, 0.14],
        "line_gap": [4, 14],
        "line_width": [0.6, 1.4],
        "waviness": [2.0, 4.0],
        "fleck_count": 200,
        "fleck_rgba": [180, 162, 132, 0.03, 0.05],
        "roughness": 0.60,
        "scale_u": 250,
        "scale_v": 1000,
    },
    "cherry": {
        "label": "American Cherry",
        "base": ["#b57a5a", "#aa7052", "#b17656"],
        "grain_lo": [118, 68, 46],
        "grain_hi": [160, 100, 70],
        "grain_alpha": [0.14, 0.20],
        "line_gap": [3, 10],
        "line_width": [0.6, 1.6],
        "waviness": [1.8, 3.0],
        "fleck_count": 400,
        "fleck_rgba": [96, 54, 36, 0.04, 0.06],
        "roughness": 0.58,
        "scale_u": 250,
        "scale_v": 1000,
    },
}


def _finish_params(finish: Optional[str]) -> Optional[dict]:
    """Resolve a finish key to its parameter dict, or None for the default
    flat vertex-colour rendering.  Raises ValueError on unknown keys."""
    if not finish or finish == "none":
        return None
    if finish not in WOOD_FINISHES:
        raise ValueError(
            f"Unknown finish {finish!r}. Available: {', '.join(sorted(WOOD_FINISHES))}"
        )
    return WOOD_FINISHES[finish]


# JavaScript for the procedural wood-grain finish.  Kept as a plain string
# (NOT part of the _build_html f-string) so its braces need no doubling; it is
# interpolated into the template as an opaque value.  Reads the FINISH const
# injected alongside it — a no-op when FINISH is null.
_FINISH_JS = """\
function applyWoodFinish(root) {
  if (!FINISH) return;
  try {
    const cvs = document.createElement('canvas');
    cvs.width = 512; cvs.height = 2048;
    const ctx = cvs.getContext('2d');
    const grad = ctx.createLinearGradient(0, 0, 512, 0);
    grad.addColorStop(0,   FINISH.base[0]);
    grad.addColorStop(0.5, FINISH.base[1]);
    grad.addColorStop(1,   FINISH.base[2]);
    ctx.fillStyle = grad; ctx.fillRect(0, 0, 512, 2048);
    // Deterministic LCG so the grain is identical on every load.
    let seed = 42;
    const rnd  = () => (seed = (seed * 1103515245 + 12345) | 0, ((seed >>> 16) & 0x7fff) / 32768);
    const lerp = (a, b, t) => a + (b - a) * t;
    let x = 0;
    while (x < 512) {
      x += FINISH.line_gap[0] + rnd() * FINISH.line_gap[1];
      const t = rnd();
      const r = Math.round(lerp(FINISH.grain_lo[0], FINISH.grain_hi[0], t));
      const g = Math.round(lerp(FINISH.grain_lo[1], FINISH.grain_hi[1], t));
      const b = Math.round(lerp(FINISH.grain_lo[2], FINISH.grain_hi[2], t));
      const a = FINISH.grain_alpha[0] + rnd() * FINISH.grain_alpha[1];
      ctx.strokeStyle = `rgba(${r},${g},${b},${a.toFixed(3)})`;
      ctx.lineWidth = FINISH.line_width[0] + rnd() * FINISH.line_width[1];
      ctx.beginPath();
      let y = -20, gx = x;
      ctx.moveTo(gx, y);
      while (y < 2068) {
        y += 60 + rnd() * 80;
        gx = x + Math.sin(y * 0.004 + x) * (FINISH.waviness[0] + rnd() * FINISH.waviness[1]);
        ctx.lineTo(gx, y);
      }
      ctx.stroke();
    }
    const [fr, fg, fb, fa0, fa1] = FINISH.fleck_rgba;
    for (let i = 0; i < FINISH.fleck_count; i++) {
      ctx.fillStyle = `rgba(${fr},${fg},${fb},${(fa0 + rnd() * fa1).toFixed(3)})`;
      ctx.fillRect(rnd() * 512, rnd() * 2048, 0.8 + rnd() * 1.2, 3 + rnd() * 10);
    }
    const tex = new THREE.CanvasTexture(cvs);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = renderer.capabilities.getMaxAnisotropy();

    // The GLB meshes carry no UVs, so box-project them in the CadQuery local
    // frame (X=width, Y=depth, Z=up — the root node's -90° X rotation maps
    // this to GLTF Y-up).  v = along-grain: vertical on fronts and sides,
    // across the width on tops/bottoms.
    function boxUV(geo) {
      if (!geo.attributes.normal) geo.computeVertexNormals();
      const pos = geo.attributes.position, nrm = geo.attributes.normal;
      const uv = new Float32Array(pos.count * 2);
      for (let i = 0; i < pos.count; i++) {
        const nx = Math.abs(nrm.getX(i)), ny = Math.abs(nrm.getY(i)), nz = Math.abs(nrm.getZ(i));
        const px = pos.getX(i), py = pos.getY(i), pz = pos.getZ(i);
        let u, v;
        if (ny >= nx && ny >= nz)      { u = px; v = pz; }
        else if (nx >= nz)             { u = py; v = pz; }
        else                           { u = py; v = px; }
        uv[i * 2] = u / FINISH.scale_u; uv[i * 2 + 1] = v / FINISH.scale_v;
      }
      geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    }
    root.traverse(obj => {
      if (!obj.isMesh) return;
      // Pull hardware keeps its metal material — skip pull/doorpull ancestry.
      let n = obj, isHardware = false;
      for (let d = 0; d < 5 && n; d++, n = n.parent) {
        if (/pull/i.test(n.name || '')) { isHardware = true; break; }
      }
      if (isHardware) return;
      boxUV(obj.geometry);
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
      mats.forEach(m => {
        if (!m) return;
        m.map = tex; m.color = new THREE.Color(0xffffff);
        m.vertexColors = false; m.roughness = FINISH.roughness; m.metalness = 0.0;
        m.needsUpdate = true;
      });
    });
  } catch (e) {
    console.error('wood finish failed:', e);
  }
}"""


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
    finish: Optional[str] = None,
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
        finish: Optional wood finish key (see ``WOOD_FINISHES``).  When set,
            the viewer textures every non-hardware mesh with a procedural
            grain instead of the flat vertex colours.

    Returns:
        Resolved ``Path`` to the written HTML file.
    """
    glb_path = Path(glb_path).expanduser().resolve()
    output_html = Path(output_html).expanduser().resolve()
    output_html.parent.mkdir(parents=True, exist_ok=True)

    glb_b64 = base64.b64encode(glb_path.read_bytes()).decode("ascii")
    html = _build_html(title, glb_b64, cabinet_info or {}, finish=finish)
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
    finish: Optional[str] = None,
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
        finish:      Optional wood finish key (see ``WOOD_FINISHES``).

    Returns:
        Dict with keys ``glb``, ``html``, ``parts``, ``glb_size_kb``.
    """
    _require_cq()
    finish_params = _finish_params(finish)  # validate before the slow export

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    glb_path  = output_dir / f"{name}.glb"
    html_path = output_dir / f"{name}_viewer.html"

    export_glb(assy, glb_path, tolerance=tolerance, angular_tolerance=angular_tolerance)

    panel_info = dict(info) if info else {}
    panel_info.setdefault("parts", len(parts))
    if finish_params:
        panel_info.setdefault("finish", finish_params["label"])

    generate_viewer_html(
        glb_path,
        html_path,
        title=name.replace("_", " ").title(),
        cabinet_info=panel_info,
        finish=finish,
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
    finish: Optional[str] = None,
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
        finish: Optional wood finish key (see ``WOOD_FINISHES``).

    Returns:
        Dict with keys:
        - ``"glb"``   — absolute path to the exported GLB file
        - ``"html"``  — absolute path to the generated HTML viewer
        - ``"parts"`` — number of parts in the assembly
        - ``"glb_size_kb"`` — GLB file size in KB
    """
    _require_cq()
    from .cabinet import build_cabinet

    finish_params = _finish_params(finish)  # validate before the slow build

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
    if cfg.openings:
        cabinet_info["openings"] = len(cfg.openings)
    if finish_params:
        cabinet_info["finish"] = finish_params["label"]

    generate_viewer_html(
        glb_path,
        html_path,
        title=name.replace("_", " ").title(),
        cabinet_info=cabinet_info,
        finish=finish,
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

def _build_html(title: str, glb_b64: str, info: dict, finish: Optional[str] = None) -> str:
    """Construct the self-contained HTML viewer string.

    Uses Three.js r165 via importmap from the jsDelivr CDN.  The GLB data
    is embedded verbatim as a base64 string constant.  When ``finish`` names
    a ``WOOD_FINISHES`` key its parameters are embedded as the FINISH const
    and the procedural grain is applied at load time.
    """
    finish_json = json.dumps(_finish_params(finish))  # "null" when no finish
    finish_js = _FINISH_JS

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

    #clip-ui {{
      position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%);
      display: none; flex-direction: column; align-items: center; gap: 6px;
      background: rgba(10, 10, 25, 0.72); backdrop-filter: blur(8px);
      border: 1px solid rgba(255,255,255,0.09); border-radius: 10px;
      padding: 10px 18px; user-select: none;
    }}
    #clip-ui.active {{ display: flex; }}
    #clip-label {{
      color: rgba(240,192,96,0.85); font-size: 11px; letter-spacing: 0.06em;
    }}
    #clip-axis-btns {{ display: flex; gap: 8px; }}
    #clip-axis-btns button {{
      background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.15);
      color: #ccc; border-radius: 5px; padding: 2px 10px; font-size: 11px; cursor: pointer;
    }}
    #clip-axis-btns button.sel {{
      background: rgba(240,192,96,0.22); border-color: rgba(240,192,96,0.55); color: #f0c060;
    }}
    #clip-range {{
      width: 260px; accent-color: #f0c060;
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
    Scroll&nbsp;&nbsp;zoom<br>
    <span style="color: rgba(240, 192, 96, 0.55);">X</span>&nbsp;&nbsp;x-ray fronts<br>
    <span style="color: rgba(240, 192, 96, 0.55);">O</span>&nbsp;&nbsp;open drawers<br>
    <span style="color: rgba(240, 192, 96, 0.55);">C</span>&nbsp;&nbsp;clip plane<br>
    <span style="color: rgba(240, 192, 96, 0.55);">V</span>&nbsp;&nbsp;diag colors
  </div>

  <div id="clip-ui">
    <div id="clip-label">CLIP PLANE</div>
    <div id="clip-axis-btns">
      <button id="btn-x" onclick="setClipAxis('x')">X</button>
      <button id="btn-y" onclick="setClipAxis('y')">Y  depth</button>
      <button id="btn-z" class="sel" onclick="setClipAxis('z')">Z  height</button>
    </div>
    <input id="clip-range" type="range" min="0" max="100" step="0.1" value="50"
           oninput="updateClipPlane()">
    <div id="clip-pos" style="color:#f0c060;font-size:11px;font-variant-numeric:tabular-nums;letter-spacing:0.04em;">— mm</div>
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

// ── Wood finish (optional; see WOOD_FINISHES in visualize.py) ─────────────────
const FINISH = {finish_json};
{finish_js}

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

// Suppress the browser context menu so right-drag pan works.
renderer.domElement.addEventListener('contextmenu', e => e.preventDefault());

// ── Load model ────────────────────────────────────────────────────────────────
// Drawer pair bookkeeping for the X-ray & Open toggles.
// Names come from cabinet.py:  "bay{{i}}_drawer{{j}}" (box)  +  "bay{{i}}_face{{j}}" (front).
const drawerFronts  = [];
const pullMeshes    = [];
const doorFaces     = [];   // bay{{i}}_door{{j}} and bay{{i}}_door{{j}}_{{k}}
const doorPullMeshes = [];  // bay{{i}}_doorpull{{j}}_...
const drawerPairs  = new Map();       // key "i_j" → {{ box, face, pullVec }}

function _pairFor(key) {{
  if (!drawerPairs.has(key)) drawerPairs.set(key, {{}});
  return drawerPairs.get(key);
}}

let cabinetRoot = null;
new GLTFLoader().parse(b64ToBuffer(GLB_B64), '', (gltf) => {{
  const model = gltf.scene;
  cabinetRoot = model;

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

    // Bucket drawer meshes by (bay, slot) for the X-ray + Open toggles.
    // Three.js GLTFLoader wraps multi-primitive meshes in a Group, adding one
    // extra level vs the GLTF JSON: leaf mesh → _part Group → panel Group →
    // bay{{i}}_drawer{{j}} Group.  Search 4 levels to cover all node types.
    const p1 = obj.parent;
    const p2 = p1 ? p1.parent : null;
    const p3 = p2 ? p2.parent : null;
    const searchNames = [obj.name, p1 ? p1.name : '', p2 ? p2.name : '', p3 ? p3.name : ''];
    const searchNodes = [obj, p1, p2, p3];
    for (let si = 0; si < searchNames.length; si++) {{
      const nm = searchNames[si];
      if (!nm) continue;

      // Drawer face (bay_i_face_j) or box (bay_i_drawer_j) — $ ensures we
      // match the group node name exactly, not leaf mesh names like bay0_face0_part_0
      const dm = nm.match(/^bay(\\d+)_(face|drawer)(\\d+)$/);
      if (dm) {{
        const key = dm[1] + '_' + dm[3];
        const pair = _pairFor(key);
        if (dm[2] === 'face') {{
          pair.face = searchNodes[si];  // group whose name matched — moves whole face
          drawerFronts.push(obj);       // mesh ref kept for x-ray material swap
        }} else {{
          // Store the group whose name matched so position.add() moves all
          // child meshes together.
          if (!pair.box) pair.box = searchNodes[si];
        }}
        break;
      }}

      // Pull hardware (bay_i_pull_j_k) — keyed the same as the drawer face
      const pm = nm.match(/^bay(\\d+)_pull(\\d+)_\\d+/);
      if (pm) {{
        const key = pm[1] + '_' + pm[2];
        const pair = _pairFor(key);
        if (!pair.pulls) pair.pulls = [];
        pair.pulls.push(obj);
        pullMeshes.push(obj);  // also track for x-ray toggle
        break;
      }}

      // Door faces (bay_i_door_j or bay_i_door_j_k — single door or pair leaf)
      if (/^bay\\d+_door\\d+(_\\d+)?$/.test(nm)) {{
        doorFaces.push(obj);
        break;
      }}

      // Door pull hardware (bay_i_doorpull_j_...)
      if (/^bay\\d+_doorpull\\d+/.test(nm)) {{
        doorPullMeshes.push(obj);
        break;
      }}
    }}
  }});

  // Compute each drawer's pull vector in CadQuery local space so that
  // position.add() works correctly.  The root node has a -90° X rotation
  // (CadQuery Z-up → GLTF Y-up); world-space direction vectors do not match
  // the local-space positions we are adding to.  Drawers always open in the
  // local -Y direction (CadQuery depth axis / cabinet front).
  // After the -90° X rotation, local Y ↔ world Z, so world Z extent == local Y depth.
  for (const pair of drawerPairs.values()) {{
    if (!pair.box || !pair.face) continue;
    const dir    = new THREE.Vector3(0, -1, 0);          // local -Y = pull out
    const boxBB  = new THREE.Box3().setFromObject(pair.box);
    const depth  = boxBB.getSize(new THREE.Vector3()).z;  // world Z = local Y
    pair.pullVec = dir.multiplyScalar(depth * 0.70);
  }}

  applyWoodFinish(model);
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

  initDiagColors();
  document.getElementById('loading').style.display = 'none';

}}, err => {{
  const el = document.getElementById('loading');
  el.textContent = 'Error loading model: ' + (err.message || err);
  el.style.color = '#f06060';
  console.error(err);
}});

// ── Toggles (X = x-ray fronts, O = open drawers) ──────────────────────────────
let xrayOn       = false;
let drawersOpen  = false;
const xrayCache  = new WeakMap();    // mesh → {{ orig, xray }}

function _makeXrayMaterial(src) {{
  const x = src.clone();
  x.transparent      = true;
  x.opacity          = 0.28;
  x.depthWrite       = false;
  x.alphaToCoverage  = true;   // routes alpha through MSAA — much smoother edges
  x.side             = THREE.FrontSide;  // DoubleSide doubles fragments and worsens aliasing
  return x;
}}

function toggleXray() {{
  xrayOn = !xrayOn;
  for (const mesh of [...drawerFronts, ...pullMeshes, ...doorFaces, ...doorPullMeshes]) {{
    if (!xrayCache.has(mesh)) {{
      const orig = mesh.material;
      const xray = Array.isArray(orig) ? orig.map(_makeXrayMaterial) : _makeXrayMaterial(orig);
      xrayCache.set(mesh, {{ orig, xray }});
    }}
    const c = xrayCache.get(mesh);
    mesh.material   = xrayOn ? c.xray : c.orig;
    mesh.castShadow = !xrayOn;
  }}
}}

function toggleOpenDrawers() {{
  const sign = drawersOpen ? -1 : 1;
  for (const pair of drawerPairs.values()) {{
    if (!pair.pullVec || !pair.box || !pair.face) continue;
    const delta = pair.pullVec.clone().multiplyScalar(sign);
    pair.box.position.add(delta);
    pair.face.position.add(delta);
    if (pair.pulls) {{
      for (const pull of pair.pulls) pull.position.add(delta);
    }}
  }}
  drawersOpen = !drawersOpen;
}}

// ── Clipping plane ────────────────────────────────────────────────────────────
let clipActive = false;
let clipAxis   = 'z';
const clipPlane = new THREE.Plane(new THREE.Vector3(0, 0, -1), 0);

function axisSpan(box, axis) {{
  if (axis === 'x') return {{ span: box.max.x - box.min.x, min: box.min.x }};
  if (axis === 'y') return {{ span: box.max.z - box.min.z, min: box.min.z }};  // cabinet Y = Three.js Z
  return {{ span: box.max.y - box.min.y, min: box.min.y }};                    // cabinet Z = Three.js Y
}}

function setSliderStep(axis) {{
  const box = new THREE.Box3().setFromObject(cabinetRoot || scene);
  const {{ span }} = axisSpan(box, axis);
  // Target 1 mm per slider step
  const step = Math.max(0.001, Math.min(1, 100 / span));
  document.getElementById('clip-range').step = step.toFixed(4);
}}

function setClipAxis(axis) {{
  clipAxis = axis;
  document.querySelectorAll('#clip-axis-btns button').forEach(b => b.classList.remove('sel'));
  document.getElementById('btn-' + axis).classList.add('sel');
  setSliderStep(axis);
  updateClipPlane();
}}

function updateClipPlane() {{
  if (!clipActive) return;
  const t = parseFloat(document.getElementById('clip-range').value) / 100;
  const box = new THREE.Box3().setFromObject(cabinetRoot || scene);
  const {{ span, min }} = axisSpan(box, clipAxis);
  const v = min + t * span;
  let normal, constant, axisLabel;
  if (clipAxis === 'x') {{
    normal = new THREE.Vector3(-1, 0, 0); constant = v; axisLabel = 'from left';
  }} else if (clipAxis === 'y') {{
    normal = new THREE.Vector3(0, 0, -1); constant = v; axisLabel = 'from front';
  }} else {{
    normal = new THREE.Vector3(0, -1, 0); constant = v; axisLabel = 'from bottom';
  }}
  clipPlane.set(normal, constant);
  const posEl = document.getElementById('clip-pos');
  if (posEl) posEl.textContent = Math.round(t * span) + ' mm ' + axisLabel;
}}

function toggleClip() {{
  clipActive = !clipActive;
  const ui = document.getElementById('clip-ui');
  if (clipActive) {{
    ui.classList.add('active');
    renderer.clippingPlanes = [clipPlane];
    renderer.localClippingEnabled = true;
    setSliderStep(clipAxis);
    updateClipPlane();
  }} else {{
    ui.classList.remove('active');
    renderer.clippingPlanes = [];
  }}
}}

window.setClipAxis  = setClipAxis;
window.updateClipPlane = updateClipPlane;

window.addEventListener('keydown', (e) => {{
  // Ignore when modifier keys are held so we don't clash with browser shortcuts.
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === 'x' || e.key === 'X') {{ toggleXray();        e.preventDefault(); }}
  if (e.key === 'o' || e.key === 'O') {{ toggleOpenDrawers(); e.preventDefault(); }}
  if (e.key === 'c' || e.key === 'C') {{ toggleClip();        e.preventDefault(); }}
  if (e.key === 'v' || e.key === 'V') {{ toggleDiagColors(); e.preventDefault(); }}
}});

// ── Diagnostic colors (V key) ─────────────────────────────────────────────────
// Vivid per-panel-type colors for drawer box inspection.
// Three.js deduplicates node names across the scene (back → back_1, back_2, …)
// so we strip the numeric suffix before looking up the panel type.
const PINK   = new THREE.Color(1.00, 0.25, 0.60);
const YELLOW = new THREE.Color(1.00, 0.85, 0.10);
const GREEN  = new THREE.Color(0.10, 0.82, 0.40);
const BLUE   = new THREE.Color(0.25, 0.55, 1.00);
const ORANGE = new THREE.Color(1.00, 0.60, 0.15);

// Drawer box panels (inside bay{{i}}_drawer{{j}} groups)
const DRAWER_DIAG_COLS = {{
  side_L: PINK, side_R: PINK,
  sub_front: YELLOW, back: YELLOW,
  bottom: GREEN,
}};
// Carcass panels (inside bay_{{i}} groups)
const CARCASS_DIAG_COLS = {{
  left_side: BLUE, right_side: BLUE,
  top: ORANGE, bottom: ORANGE,
}};

let diagOn = false;
const diagMeshes = [];

function _diagAncestorColor(obj, table) {{
  let cur = obj.parent;
  for (let i = 0; i < 5; i++) {{
    if (!cur) return null;
    const base = cur.name.replace(/_\\d+$/, '');
    if (table[base]) return table[base];
    cur = cur.parent;
  }}
  return null;
}}

function isInDrawerGroup(obj) {{
  let cur = obj.parent;
  for (let i = 0; i < 7; i++) {{
    if (!cur) return false;
    if (/^bay\\d+_drawer\\d+$/.test(cur.name)) return true;
    cur = cur.parent;
  }}
  return false;
}}

function isInCarcassGroup(obj) {{
  let cur = obj.parent;
  for (let i = 0; i < 7; i++) {{
    if (!cur) return false;
    if (/^bay_\\d+$/.test(cur.name)) return true;
    cur = cur.parent;
  }}
  return false;
}}

function initDiagColors() {{
  (cabinetRoot || scene).traverse(obj => {{
    if (!obj.isMesh || !obj.material) return;
    let diagCol = null;
    if (isInDrawerGroup(obj))  diagCol = _diagAncestorColor(obj, DRAWER_DIAG_COLS);
    else if (isInCarcassGroup(obj)) diagCol = _diagAncestorColor(obj, CARCASS_DIAG_COLS);
    if (diagCol) {{
      const diagMat = obj.material.clone();
      diagMat.color.copy(diagCol);
      diagMat.roughness = 0.45;
      diagMeshes.push({{ mesh: obj, origMat: obj.material, diagMat }});
    }}
  }});
}}

function toggleDiagColors() {{
  diagOn = !diagOn;
  for (const {{ mesh, origMat, diagMat }} of diagMeshes) {{
    mesh.material = diagOn ? diagMat : origMat;
  }}
}}

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
