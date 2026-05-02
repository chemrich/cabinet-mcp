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
    if cfg.openings:
        cabinet_info["openings"] = len(cfg.openings)

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
    // CadQuery wraps each shape in a Group + _part mesh, so the named node
    // may be the mesh itself (si=0), its parent (si=1), or its grandparent
    // (si=2 — drawer box parts are 2 levels deep: bay0_drawer0/side_L/side_L_part).
    const p1 = obj.parent;
    const p2 = p1 ? p1.parent : null;
    const searchNames = [obj.name, p1 ? p1.name : '', p2 ? p2.name : ''];
    const searchNodes = [obj, p1, p2];
    for (let si = 0; si < searchNames.length; si++) {{
      const nm = searchNames[si];
      if (!nm) continue;

      // Drawer face (bay_i_face_j) or box (bay_i_drawer_j)
      const dm = nm.match(/^bay(\\d+)_(face|drawer)(\\d+)/);
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
