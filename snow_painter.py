# -*- coding: utf-8 -*-
"""
Snow Painter  -  Unreal Engine 5.6 editor tool (single Python script, Qt UI)
=============================================================================

Paint snow onto meshes with the mouse; Geometry Script turns the paint into a
real snow mesh that sits on the surface (thick in the middle, soft edges that
sink into the surface, only on faces flat enough to hold snow).

HOW IT WORKS
------------
Unreal's Python can't capture mouse drags in the level viewport, so the brush
is Unreal's own Mesh Paint mode:
1. Select one or more mesh actors and click "Start painting". The tool drapes
   an invisible "paint canvas" over their top surface, found by casting rays
   straight down onto the full-detail mesh (your meshes are never modified).
2. Switch to Mesh Paint mode (the mode dropdown at the top left, e.g. "Selection
   Mode" or "Modeling Mode" > Mesh Paint), pick Colors (Vertex Color) > Paint,
   keep the paint color white and paint with the left mouse button (Shift+LMB
   erases). If nothing reacts, select SnowCanvas_<mesh> in the Outliner.
   Painted areas glow light blue.
3. Each time you release the mouse, the snow is rebuilt with Geometry Script.
   Shape it with the sliders (depth, soft edges, max slope, clumps...).
4. "Bake" turns it into a Static Mesh asset + actor (Nanite optional) and
   removes the canvas.

HOW TO RUN  (enable the "Python Editor Script Plugin", "Geometry Script" and "Mesh
            Paint" plugins - Mesh Paint is missing from the mode dropdown when it's off)
----------
A) Paste: Window > Output Log, set the dropdown left of the input box to
   "Python", paste this whole script, press Enter.
B) File:  Tools > Execute Python Script... and pick this file.
C) Module: put it in <Project>/Content/Python/ and run
      import snow_painter; snow_painter.show()

NOTE: this script never spells out the Python file extension on purpose: when
code is pasted into the Output Log, Unreal treats text containing it as a file
path ("Could not load Python file").

Without Qt (PySide6) it runs in text mode: snow_painter.start(), update(),
bake(), clear_paint(), cancel().
"""

import importlib
import math
import os
import re
import subprocess
import sys
import time
import traceback
import types

try:
    import unreal
except ImportError:          # the geometry core below also works outside Unreal (tests)
    unreal = None

__version__ = "1.1.0"
TOOL_NAME = "Snow Painter"
WINDOW_OBJECT_NAME = "SnowPainterWindow"

# =============================================================================
# CONFIG
# =============================================================================
CONFIG = {
    # --- snow shape (also on the sliders) --------------------------------------------------
    "depth": 12.0,                # cm of snow where fully painted, on flat ground
    "softness": 3,                # edge softening passes (rounder, softer snow edges)
    "max_slope": 55.0,            # degrees: steeper faces hold no snow
    "slope_fade": 25.0,           # degrees over which snow thins out towards max_slope
    "pile_up": 0.6,               # 0 = grow along the surface normal, 1 = pile up vertically
    "clumps": 0.35,               # 0..1 thickness variation
    "clump_size": 80.0,           # cm, size of the thickness variation
    "edge_sink": 1.5,             # cm the snow edge dips under the surface (no visible seam)
    "uv_scale": 200.0,            # cm per UV tile (top-down projection) for the snow material
    "seed": 7,
    # --- paint canvas + snow detail ----------------------------------------------------------------
    "canvas_detail": 10.0,        # cm between paint canvas points (coarsened on big meshes, see canvas_max_points)
    "canvas_max_points": 90000,   # per mesh: the canvas grid is coarsened to stay under this many points
    "canvas_max_angle": 80.0,     # degrees: drops steeper than this (cliffs) get no canvas across them
    "canvas_offset": 2.0,         # cm the canvas floats above the surface (plus the local bumpiness)
    "snow_detail": 5.0,           # cm between snow vertices, independent of the canvas (sampled where painted)
    "snow_max_points": 250000,    # per rebuild: very large painted areas get a coarser snow mesh
    "surface_max_tris": 3000000,  # denser source meshes (Nanite scans) are simplified for the ray casts
    "paint_threshold": 0.02,      # painted red value below this counts as no paint
    # --- live update -------------------------------------------------------------------------------
    "poll_seconds": 0.5,          # how often the canvas paint is checked
    "settle_seconds": 0.4,        # rebuild once the paint stopped changing for this long
    "poll_sample_step": 7,        # check every Nth vertex for changes (a full read follows a change)
    # --- assets ------------------------------------------------------------------------------------
    "asset_folder": "/Game/SnowPainter",
    "snow_material": "",          # empty: the tool's own simple snow material
    "bake_nanite": True,
}


# =============================================================================
# Geometry core (pure Python, no Unreal calls) - positions are (x, y, z) tuples in cm,
# triangles are (a, b, c) index tuples, counter-clockwise seen from the front side.
# =============================================================================
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(a):
    return math.sqrt(_dot(a, a))


def _normalize(a, fallback=(0.0, 0.0, 1.0)):
    n = _length(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else fallback


def _dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _smoothstep(e0, e1, x):
    if e1 == e0:
        return 1.0 if x >= e1 else 0.0
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def face_normal(positions, tri):
    """Unnormalised (length = 2 x area)."""
    a, b, c = positions[tri[0]], positions[tri[1]], positions[tri[2]]
    return _cross(_sub(b, a), _sub(c, a))


def vertex_normals(positions, triangles):
    acc = [[0.0, 0.0, 0.0] for _ in positions]
    for t in triangles:
        n = face_normal(positions, t)
        for v in t:
            a = acc[v]
            a[0] += n[0]
            a[1] += n[1]
            a[2] += n[2]
    return [_normalize(tuple(a)) for a in acc]


def _hash3(ix, iy, iz, seed):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
    h &= 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def value_noise(x, y, z, seed=0):
    """Smooth 3D value noise in [0, 1], deterministic."""
    ix, iy, iz = int(math.floor(x)), int(math.floor(y)), int(math.floor(z))
    fx, fy, fz = x - ix, y - iy, z - iz
    sx, sy, sz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)

    def lerp(a, b, t):
        return a + (b - a) * t

    c = [[[_hash3(ix + i, iy + j, iz + k, seed) for k in (0, 1)] for j in (0, 1)] for i in (0, 1)]
    x00 = lerp(c[0][0][0], c[1][0][0], sx)
    x10 = lerp(c[0][1][0], c[1][1][0], sx)
    x01 = lerp(c[0][0][1], c[1][0][1], sx)
    x11 = lerp(c[0][1][1], c[1][1][1], sx)
    return lerp(lerp(x00, x10, sy), lerp(x01, x11, sy), sz)


# --- the surface seen from above ---------------------------------------------------------------------------
# Snow falls from above, so both the paint canvas and the snow are built from rays cast straight down onto the
# real (full detail) surface: no dependence on how the mesh is triangulated, its winding or its density.
class Surface(object):
    """Top surface of a mesh sampled by downward ray casts on a fine XY lattice (each point cast once, cached).
    raycast(x, y) -> z of the topmost hit or None. Canvas point (i, j) is lattice point (i * k, j * k); the snow
    uses the fine lattice (step / k) where it was painted."""

    def __init__(self, raycast, x0, y0, step, k):
        self.raycast = raycast
        self.x0, self.y0, self.step = float(x0), float(y0), float(step)
        self.k = max(1, int(k))
        self.fine = self.step / self.k
        self.cache = {}
        self.rays = 0

    def xy(self, I, J):
        return self.x0 + I * self.fine, self.y0 + J * self.fine

    def z(self, I, J):
        key = (I, J)
        try:
            return self.cache[key]
        except KeyError:
            pass
        x, y = self.xy(I, J)
        self.rays += 1
        v = self.raycast(x, y)
        self.cache[key] = v
        return v

    def cz(self, i, j):
        return self.z(i * self.k, j * self.k)

    def canvas_index(self, x, y):
        return int(round((x - self.x0) / self.step)), int(round((y - self.y0) / self.step))


def plan_grid(xmin, ymin, xmax, ymax, params=None):
    """Canvas grid over an XY box: (x0, y0, step, k, nx, ny). The step is coarsened so the grid stays under
    canvas_max_points; k (a power of two) subdivides it down to about snow_detail for the snow."""
    cfg = dict(CONFIG)
    cfg.update(params or {})
    w, h = max(1.0, xmax - xmin), max(1.0, ymax - ymin)
    step = max(float(cfg["canvas_detail"]), math.sqrt(w * h / max(1.0, float(cfg["canvas_max_points"]))))
    nx, ny = int(math.floor(w / step)) + 1, int(math.floor(h / step)) + 1
    x0 = xmin + (w - (nx - 1) * step) * 0.5
    y0 = ymin + (h - (ny - 1) * step) * 0.5
    k = 1
    while k < 16 and step / k > float(cfg["snow_detail"]) * 1.5:
        k *= 2
    return x0, y0, step, k, nx, ny


def _cliff(zs, span, max_angle):
    return max(zs) - min(zs) > span * 1.42 * math.tan(math.radians(max_angle))


def make_canvas_grid(surface, nx, ny, params=None, progress=None):
    """Paint canvas: a grid draped over the top surface, lifted a little above it (more where the surface is bumpy
    between grid points), with no faces across cliffs. Returns (positions, triangles, {(i, j): vertex index})."""
    cfg = dict(CONFIG)
    cfg.update(params or {})
    z = {}
    for i in range(nx):
        if progress is not None:
            progress(i, 2 * nx + 2)
        for j in range(ny):
            v = surface.cz(i, j)
            if v is not None:
                z[(i, j)] = v
    cells = []
    for (i, j), z00 in z.items():
        others = (z.get((i + 1, j)), z.get((i + 1, j + 1)), z.get((i, j + 1)))
        if None in others or _cliff((z00,) + others, surface.step, cfg["canvas_max_angle"]):
            continue
        cells.append((i, j))
    k, rough = surface.k, {}
    chunk = max(1, len(cells) // max(1, nx))
    for n, (i, j) in enumerate(cells):
        if progress is not None and n % chunk == 0:
            progress(nx + n // chunk, 2 * nx + 2)
        corners = ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))
        if k >= 2:
            zc = surface.z(i * k + k // 2, j * k + k // 2)       # on the lattice: the snow reuses it
        else:
            x, y = surface.xy(i + 0.5, j + 0.5)
            surface.rays += 1
            zc = surface.raycast(x, y)
        if zc is None:
            continue
        bump = zc - sum(z[c] for c in corners) / 4.0
        if bump > 0:
            for c in corners:
                rough[c] = max(rough.get(c, 0.0), bump)
    off = float(cfg["canvas_offset"])
    index, pos, tris = {}, [], []

    def vid(p):
        n = index.get(p)
        if n is None:
            n = index[p] = len(pos)
            x, y = surface.xy(p[0] * k, p[1] * k)
            pos.append((x, y, z[p] + off + rough.get(p, 0.0)))
        return n

    for i, j in cells:
        a, b, c, d = vid((i, j)), vid((i + 1, j)), vid((i + 1, j + 1)), vid((i, j + 1))
        if abs(z[(i, j)] - z[(i + 1, j + 1)]) <= abs(z[(i + 1, j)] - z[(i, j + 1)]):
            tris += [(a, b, c), (a, c, d)]
        else:
            tris += [(a, b, d), (b, c, d)]
    return pos, tris, index


def build_snow_grid(surface, points, paint, params=None, up=(0.0, 0.0, 1.0)):
    """Snow from paint on the canvas grid.
    surface: Surface of the target; points: canvas points (i, j) that exist; paint: {(i, j): 0..1}.
    Returns {"positions", "normals", "uvs", "colors", "triangles", "painted", "stride"}; empty when nothing is
    painted. Positions are world space."""
    cfg = dict(CONFIG)
    cfg.update(params or {})
    empty = {"positions": [], "normals": [], "uvs": [], "colors": [], "triangles": [], "painted": 0, "stride": 1}
    thr = float(cfg["paint_threshold"])
    painted = {p: min(1.0, float(w)) for p, w in paint.items() if p in points and w >= thr}
    if not painted or surface is None:
        return empty
    s, k = surface.step, surface.k
    max_angle = float(cfg["canvas_max_angle"])
    limit = s * math.tan(math.radians(max_angle))

    def cz(p):
        return surface.cz(p[0], p[1]) if p in points else None

    def linked(p, q, diag=False):
        a, b = cz(p), cz(q)
        return a is not None and b is not None and abs(a - b) <= limit * (1.42 if diag else 1.0)

    normals = {}

    def normal(p):
        n = normals.get(p)
        if n is None:
            i, j = p
            z0 = cz(p)
            g = []
            for (d1, d2) in (((1, 0), (-1, 0)), ((0, 1), (0, -1))):
                qa, qb = (i + d1[0], j + d1[1]), (i + d2[0], j + d2[1])
                za = cz(qa) if linked(p, qa) else None
                zb = cz(qb) if linked(p, qb) else None
                if za is not None and zb is not None:
                    g.append((za - zb) / (2 * s))
                elif za is not None:
                    g.append((za - z0) / s)
                elif zb is not None:
                    g.append((z0 - zb) / s)
                else:
                    g.append(0.0)
            n = normals[p] = _normalize((-g[0], -g[1], 1.0))
        return n

    up = _normalize(up)
    c_max = math.cos(math.radians(cfg["max_slope"]))
    c_full = math.cos(math.radians(max(0.0, cfg["max_slope"] - cfg["slope_fade"])))

    def slope(p):
        return _smoothstep(c_max, c_full, _dot(normal(p), up))

    m = {p: w * slope(p) for p, w in painted.items()}
    m = {p: v for p, v in m.items() if v > 0.0}
    nb8 = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
    for _ in range(int(cfg["softness"])):
        region = set(m)
        for (i, j) in list(m):
            for di, dj in nb8:
                q = (i + di, j + dj)
                if q in points and linked((i, j), q, di and dj):
                    region.add(q)
        new = {}
        for p in region:
            qs = [(p[0] + di, p[1] + dj) for di, dj in nb8]
            qs = [q for q, (di, dj) in zip(qs, nb8) if q in points and linked(p, q, di and dj)]
            avg = sum(m.get(q, 0.0) for q in qs) / len(qs) if qs else 0.0
            v = (0.5 * m.get(p, 0.0) + 0.5 * avg) * slope(p)
            if v > 1e-4:
                new[p] = v
        m = new
    # next to a drop or the edge of the mesh, the snow thins out to nothing (instead of ending in a wall)
    for p in list(m):
        for di, dj in nb8:
            q = (p[0] + di, p[1] + dj)
            if q not in points or not linked(p, q, di and dj):
                m[p] = 0.0
                break
    if not any(v > 0.0 for v in m.values()):
        return empty
    eps = 0.01

    def corners(c):
        i, j = c
        return ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))

    cells = set()
    for (i, j) in m:
        for c in ((i - 1, j - 1), (i, j - 1), (i - 1, j), (i, j)):
            cs = corners(c)
            if all(q in points for q in cs) and not _cliff([cz(q) for q in cs], s, max_angle) \
                    and max(m.get(q, 0.0) for q in cs) > eps:
                cells.add(c)
    if not cells:
        return empty
    stride = 1
    while stride < k and len(cells) * (k // stride + 1) ** 2 > float(cfg["snow_max_points"]):
        stride *= 2                                   # huge painted area: coarser snow, same cached rays
    kk = k // stride
    span = s / kk
    verts, quads = {}, []
    for c in sorted(cells):
        i, j = c
        cs = corners(c)
        mc = [m.get(q, 0.0) for q in cs]
        nc = [normal(q) for q in cs]
        for a in range(kk + 1):
            for b in range(kk + 1):
                key = (i * k + a * stride, j * k + b * stride)
                if key in verts:
                    continue
                z = surface.z(*key)
                if z is None:
                    verts[key] = None
                    continue
                u, v = a / float(kk), b / float(kk)
                w4 = ((1 - u) * (1 - v), u * (1 - v), u * v, (1 - u) * v)
                mm = sum(wt * x for wt, x in zip(w4, mc))
                nrm = _normalize(tuple(sum(wt * n[t] for wt, n in zip(w4, nc)) for t in range(3)))
                x, y = surface.xy(*key)
                verts[key] = [x, y, z, mm, nrm, False]
        for a in range(kk):
            for b in range(kk):
                q = ((i * k + a * stride, j * k + b * stride), (i * k + (a + 1) * stride, j * k + b * stride),
                     (i * k + (a + 1) * stride, j * k + (b + 1) * stride), (i * k + a * stride, j * k + (b + 1) * stride))
                vs = [verts.get(p) for p in q]
                if any(v is None for v in vs) or _cliff([v[2] for v in vs], span, max_angle):
                    for v in vs:
                        if v is not None:
                            v[5] = True                # surface edge or a drop: the snow tapers off here
                    continue
                if max(v[3] for v in vs) > eps:
                    quads.append(q)
    tri_keys = []
    for q in quads:
        z0, z1, z2, z3 = (verts[p][2] for p in q)
        if abs(z0 - z2) <= abs(z1 - z3):
            tri_keys += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
        else:
            tri_keys += [(q[0], q[1], q[3]), (q[1], q[2], q[3])]
    depth, pile = float(cfg["depth"]), max(0.0, min(1.0, float(cfg["pile_up"])))
    clumps, csize = max(0.0, float(cfg["clumps"])), max(1.0, float(cfg["clump_size"]))
    sink, seed = float(cfg["edge_sink"]), int(cfg["seed"])
    order, out_pos, out_col = {}, [], []
    for t in tri_keys:
        for key in t:
            if key in order:
                continue
            x, y, z, mm, nrm, edge = verts[key]
            mm = 0.0 if edge else mm
            if mm > 0.0:
                px, py, pz = x / csize, y / csize, z / csize
                noise = 0.65 * value_noise(px, py, pz, seed) + 0.35 * value_noise(px * 2.03, py * 2.03, pz * 2.03, seed + 1)
                thick = depth * (mm ** 0.7) * max(0.0, 1.0 + clumps * (2.0 * noise - 1.0))
            else:
                thick = 0.0
            d = _normalize((nrm[0] * (1 - pile) + up[0] * pile, nrm[1] * (1 - pile) + up[1] * pile,
                            nrm[2] * (1 - pile) + up[2] * pile), nrm)
            dip = sink * (1.0 - _smoothstep(0.0, 0.3, mm))       # thin edges dip under the surface: no seam
            order[key] = len(out_pos)
            out_pos.append((x + d[0] * thick - nrm[0] * dip, y + d[1] * thick - nrm[1] * dip,
                            z + d[2] * thick - nrm[2] * dip))
            out_col.append((mm, 0.0, 0.0, 1.0))
    out_tris = [(order[a], order[b], order[c]) for a, b, c in tri_keys]
    us = float(cfg["uv_scale"]) or 1.0
    return {"positions": out_pos, "normals": vertex_normals(out_pos, out_tris),
            "uvs": [(p[0] / us, p[1] / us) for p in out_pos], "colors": out_col, "triangles": out_tris,
            "painted": len(painted), "stride": stride}


def bounds_center(positions):
    if not positions:
        return (0.0, 0.0, 0.0)
    lo = [min(p[k] for p in positions) for k in range(3)]
    hi = [max(p[k] for p in positions) for k in range(3)]
    return ((lo[0] + hi[0]) * 0.5, (lo[1] + hi[1]) * 0.5, (lo[2] + hi[2]) * 0.5)


# =============================================================================
# Unreal helpers
# =============================================================================
def _log(msg):
    if unreal is not None:
        unreal.log("[SnowPainter] " + msg)


def _warn(msg):
    if unreal is not None:
        unreal.log_warning("[SnowPainter] " + msg)


def _call_first(*fns):
    last = None
    for fn in fns:
        try:
            return fn()
        except Exception as e:  # noqa
            last = e
    if last is not None:
        raise last
    return None


def _gs(*names):
    """A Geometry Script library class (Python names differ slightly between engine versions)."""
    for name in names:
        cls = getattr(unreal, name, None)
        if cls is not None:
            return cls
    raise RuntimeError("Geometry Script isn't available (%s). Enable the 'Geometry Script' plugin "
                       "(Edit > Plugins) and restart the editor." % names[0])


def _outs(result):
    return result if isinstance(result, tuple) else (result,)


def _find(result, type_name):
    for x in _outs(result):
        if type(x).__name__ == type_name:
            return x
    return None


def _find_instance(result, cls):
    for x in _outs(result):
        if cls is not None and isinstance(x, cls):
            return x
    return None


def _set(obj, names, value):
    """set_editor_property with the first property name that exists (names vary between versions)."""
    last = None
    for n in names:
        try:
            obj.set_editor_property(n, value)
            return n
        except Exception as e:
            last = e
    raise last if last else RuntimeError("no property %s" % (names,))


def _list_to_py(lst, kind):
    """GeometryScript Vector / Triangle / Color list -> plain Python list."""
    fn = {"vector": "convert_vector_list_to_array", "triangle": "convert_triangle_list_to_array",
          "color": "convert_color_list_to_array"}[kind]
    lib = getattr(unreal, "GeometryScript_List", None) or getattr(unreal, "GeometryScript_ListUtils", None)
    arr = _call_first(lambda: getattr(lib, fn)(lst), lambda: getattr(lst, fn)())
    return arr[0] if isinstance(arr, tuple) else arr


def _outcome_ok(result):
    pins = getattr(unreal, "GeometryScriptOutcomePins", None)
    oc = _find(result, "GeometryScriptOutcomePins")
    return oc is None or pins is None or oc == pins.SUCCESS


def _asset_folder(sub=""):
    folder = "/" + str(CONFIG["asset_folder"]).strip("/")
    if not re.match(r"^/Game(/[A-Za-z0-9_]{1,64}){0,6}$", folder):
        raise RuntimeError("asset_folder must be a folder under /Game: %r" % folder)
    return folder + ("/" + sub if sub else "")


def _actor_sub():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _alive(obj):
    if obj is None:
        return False
    try:
        return bool(unreal.SystemLibrary.is_valid(obj))
    except Exception:
        try:
            obj.get_name()
            return True
        except Exception:
            return False


def _tags(actor):
    try:
        return [str(t) for t in (actor.get_editor_property("tags") or [])]
    except Exception:
        return []


def _set_tags(actor, tags):
    try:
        actor.set_editor_property("tags", [unreal.Name(t) for t in tags])
    except Exception:
        actor.set_editor_property("tags", list(tags))


TAG_CANVAS, TAG_SNOW, TAG_TARGET = "SnowPainterCanvas", "SnowPainterSnow", "SnowPainterTarget:"
TAG_GRID = "SnowPainterGrid:"           # x0;y0;step;k of the canvas grid, so a session can be resumed


def _is_ours(actor):
    return any(t in (TAG_CANVAS, TAG_SNOW) for t in _tags(actor))


def _mesh_component(actor):
    if actor is None:
        return None
    for fn in (lambda: actor.get_component_by_class(unreal.StaticMeshComponent),
               lambda: actor.get_editor_property("static_mesh_component"),
               lambda: (actor.get_components_by_class(unreal.StaticMeshComponent) or [None])[0]):
        try:
            c = fn()
            if c is not None:
                return c
        except Exception:
            pass
    return None


# --- reading / writing meshes ---------------------------------------------------------------------------
def read_component(comp, want_colors=False):
    """Copy a StaticMeshComponent into a DynamicMesh (world space). want_colors: render data + the per-instance
    vertex colors Mesh Paint writes. Returns the unreal.DynamicMesh."""
    scene = _gs("GeometryScript_SceneUtils")
    opts = unreal.GeometryScriptCopyMeshFromComponentOptions()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod_type = unreal.GeometryScriptLODType
    lod.set_editor_property("lod_type", lod_type.RENDER_DATA if want_colors else lod_type.MAX_AVAILABLE)
    opts.set_editor_property("requested_lod", lod)
    if want_colors:
        opts.set_editor_property("want_instance_colors", True)
    mesh = unreal.DynamicMesh()
    res = scene.copy_mesh_from_component(comp, mesh, opts, True)
    if not _outcome_ok(res):
        raise RuntimeError("Could not copy the mesh of %s" % comp.get_name())
    return _find_instance(res, unreal.DynamicMesh) or mesh


def mesh_geometry(mesh):
    """(positions, triangles) of a DynamicMesh; positions are indexed by vertex ID."""
    q = _gs("GeometryScript_MeshQueries")
    vl = _find(q.get_all_vertex_positions(mesh, False), "GeometryScriptVectorList")
    tl = _find(q.get_all_triangle_indices(mesh, False), "GeometryScriptTriangleList")
    positions = [(v.x, v.y, v.z) for v in _list_to_py(vl, "vector")]
    tris = []
    for t in _list_to_py(tl, "triangle"):
        a, b, c = t.x, t.y, t.z
        if a >= 0 and b >= 0 and c >= 0:
            tris.append((a, b, c))
    return positions, tris


def mesh_bounds(mesh):
    """((xmin, ymin, zmin), (xmax, ymax, zmax)) of a DynamicMesh."""
    q = _gs("GeometryScript_MeshQueries")
    box = next((x for x in _outs(q.get_mesh_bounding_box(mesh)) if hasattr(x, "min") or hasattr(x, "get_editor_property")),
               None)
    lo = _call_first(lambda: box.get_editor_property("min"), lambda: box.min)
    hi = _call_first(lambda: box.get_editor_property("max"), lambda: box.max)
    return (lo.x, lo.y, lo.z), (hi.x, hi.y, hi.z)


def make_raycaster(mesh, z_top, length):
    """raycast(x, y) -> z of the topmost surface of `mesh` below (x, y, z_top), or None (Geometry Script BVH)."""
    sp = _gs("GeometryScript_MeshSpatial")
    bvh = _find(sp.build_bvh_for_mesh(mesh), "GeometryScriptDynamicMeshBVH")
    if bvh is None:
        raise RuntimeError("Could not build the ray-query structure (Geometry Script BVH)")
    opts = unreal.GeometryScriptSpatialQueryOptions()
    try:
        opts.set_editor_property("max_distance", float(length))
    except Exception:
        pass
    down = unreal.Vector(0.0, 0.0, -1.0)
    pins = getattr(unreal, "GeometryScriptSearchOutcomePins", None)
    found = getattr(pins, "FOUND", None) if pins is not None else None

    def raycast(x, y):
        res = sp.find_nearest_ray_intersection_with_mesh(mesh, bvh, unreal.Vector(x, y, z_top), down, opts)
        hit = _find(res, "GeometryScriptRayHitResult")
        if hit is None:
            return None
        oc = _find(res, "GeometryScriptSearchOutcomePins")
        if oc is not None and found is not None:
            if oc != found:
                return None
        else:
            flag = _call_first(lambda: hit.get_editor_property("hit"), lambda: hit.get_editor_property("b_hit"))
            if not flag:
                return None
        return hit.get_editor_property("hit_position").z

    return raycast


def mesh_colors(mesh):
    """unreal.Array of LinearColor indexed by vertex ID (empty when the mesh has no colors)."""
    vc = _gs("GeometryScript_VertexColors")
    res = vc.get_mesh_per_vertex_colors(mesh, True)
    cl = _find(res, "GeometryScriptColorList")
    valid = [x for x in _outs(res) if isinstance(x, bool)]
    if cl is None or (valid and not valid[0]):
        return []
    return _list_to_py(cl, "color")


def planar_uvs(positions, scale=None):
    """Top-down UVs (one tile per `scale` cm)."""
    s = float(scale or CONFIG["uv_scale"]) or 1.0
    return [(p[0] / s, p[1] / s) for p in positions]


def write_mesh(mesh, data, center=(0.0, 0.0, 0.0)):
    """Replace the contents of a DynamicMesh with `data` (see build_snow), shifted by -center.
    Always writes a UV set: Unreal asserts (crashes the editor) when a Static Mesh is built without UVs."""
    _call_first(lambda: mesh.reset_mesh(), lambda: mesh.reset())
    if not data["triangles"]:
        return mesh
    if not data.get("uvs") or len(data["uvs"]) != len(data["positions"]):
        data = dict(data, uvs=planar_uvs(data["positions"]))
    cx, cy, cz = center
    buf = unreal.GeometryScriptSimpleMeshBuffers()
    buf.set_editor_property("vertices", [unreal.Vector(p[0] - cx, p[1] - cy, p[2] - cz) for p in data["positions"]])
    if data.get("normals"):
        buf.set_editor_property("normals", [unreal.Vector(*nv) for nv in data["normals"]])
    _set(buf, ("uv0", "u_v0"), [unreal.Vector2D(u, v) for u, v in data["uvs"]])
    if data.get("colors"):
        buf.set_editor_property("vertex_colors", [unreal.LinearColor(*c) for c in data["colors"]])
    _set(buf, ("triangles", "triangle_indices"), [unreal.IntVector(a, b, c) for a, b, c in data["triangles"]])
    edits = _gs("GeometryScript_MeshEdits", "GeometryScript_MeshBasicEdits")
    edits.append_buffers_to_mesh(mesh, buf, 0, False)
    return mesh


# --- materials -------------------------------------------------------------------------------------------
def _material(name, build):
    path = "%s/%s" % (_asset_folder("Materials"), name)
    lib = unreal.EditorAssetLibrary
    if lib.does_asset_exist(path):
        return lib.load_asset(path)
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, _asset_folder("Materials"), unreal.Material, unreal.MaterialFactoryNew())
    if mat is None:
        raise RuntimeError("Could not create %s" % path)
    build(mat)
    unreal.MaterialEditingLibrary.recompile_material(mat)
    return mat


def _canvas_material():
    def build(mat):
        mel = unreal.MaterialEditingLibrary
        mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
        mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
        vc = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -600, 0)
        mul = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -400, 0)
        mul.set_editor_property("const_b", 0.5)
        add = mel.create_material_expression(mat, unreal.MaterialExpressionAdd, -250, 0)
        add.set_editor_property("const_b", 0.03)         # a faint tint shows where you can paint
        col = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -400, -200)
        col.set_editor_property("constant", unreal.LinearColor(0.35, 0.75, 1.0, 1.0))
        mel.connect_material_expressions(vc, "R", mul, "A")
        mel.connect_material_expressions(mul, "", add, "A")
        mel.connect_material_property(add, "", unreal.MaterialProperty.MP_OPACITY)
        mel.connect_material_property(col, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    return _material("M_SnowPainter_Canvas", build)


def _default_snow_material():
    def build(mat):
        mel = unreal.MaterialEditingLibrary
        col = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -400, -100)
        col.set_editor_property("constant", unreal.LinearColor(0.92, 0.94, 0.97, 1.0))
        rough = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 100)
        rough.set_editor_property("r", 0.55)
        mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
        mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    return _material("M_SnowPainter_Snow", build)


def snow_material():
    path = str(CONFIG.get("snow_material") or "").strip()
    if path:
        mat = unreal.EditorAssetLibrary.load_asset(path)
        if mat is not None:
            return mat
        _warn("Snow material %s not found - using the default snow material." % path)
    return _default_snow_material()


# --- static mesh assets ------------------------------------------------------------------------------
def _uv_set_count(mesh):
    q = getattr(unreal, "GeometryScript_MeshQueries", None)
    try:
        res = q.get_num_uv_sets(mesh)
        return int(next(x for x in _outs(res) if isinstance(x, int) and not isinstance(x, bool)))
    except Exception:
        return None


def _ensure_uvs(mesh):
    """Never hand Unreal a mesh without UVs to build a Static Mesh from: that's an engine assertion (editor crash),
    not an error the script could catch."""
    n = _uv_set_count(mesh)
    if n is None or n > 0:
        return
    try:
        _gs("GeometryScript_UVs").set_num_uv_sets(mesh, 1)
    except Exception:
        pass
    if not _uv_set_count(mesh):
        raise RuntimeError("The generated mesh has no UV set - not creating the Static Mesh (Unreal would crash). "
                           "Please report this with the Output Log.")


def _new_static_mesh(mesh, sub, base_name, nanite=False, collision=False):
    _ensure_uvs(mesh)
    newu = _gs("GeometryScript_NewAssetUtils", "GeometryScript_AssetUtils")
    res = newu.create_unique_new_asset_path_name(_asset_folder(sub), base_name,
                                                 unreal.GeometryScriptUniqueAssetNameOptions())
    path = next((x for x in _outs(res) if isinstance(x, str) and x.startswith("/")), None)
    if path is None:
        raise RuntimeError("Could not pick an asset name in %s" % _asset_folder(sub))
    opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
    for prop, val in (("enable_nanite", bool(nanite)), ("enable_collision", bool(collision))):
        try:
            opts.set_editor_property(prop, val)
        except Exception:
            pass
    out = newu.create_new_static_mesh_asset_from_mesh(mesh, path, opts)
    sm = _find_instance(out, unreal.StaticMesh)
    if sm is None or not _outcome_ok(out):
        raise RuntimeError("Could not create the static mesh %s" % path)
    return sm


def _set_mesh_material(sm, mat, actor=None):
    """Material on the asset (adding a slot when Geometry Script created none) and on the placed actor."""
    try:
        slots = sm.get_editor_property("static_materials")
    except Exception:
        slots = None
    if slots is not None and len(slots) == 0:
        _call_first(lambda: sm.set_editor_property("static_materials", [
            unreal.StaticMaterial(material_interface=mat, material_slot_name="Snow")]), lambda: None)
    else:
        _call_first(lambda: sm.set_material(0, mat), lambda: None)
    comp = _mesh_component(actor) if actor is not None else None
    if comp is not None:
        _call_first(lambda: comp.set_material(0, mat), lambda: None)


def _delete_asset(obj):
    """Delete an asset this tool created (only inside its own folder)."""
    try:
        pkg = obj.get_outermost().get_name()
    except Exception:
        return
    if pkg.startswith(_asset_folder() + "/"):
        try:
            unreal.EditorAssetLibrary.delete_asset(pkg)
        except Exception as e:
            _warn("Could not delete %s: %s" % (pkg, e))


# =============================================================================
# Session: targets, canvases, live snow
# =============================================================================
class Target(object):
    def __init__(self, actor):
        self.actor = actor
        self.label = _call_first(lambda: actor.get_actor_label(), lambda: actor.get_name())
        self.canvas = None          # StaticMeshActor with the paint canvas
        self.canvas_mesh = None     # its StaticMesh asset
        self.snow = None            # DynamicMeshActor with the live snow
        self.center = (0.0, 0.0, 0.0)
        self.grid = None            # (x0, y0, step, k) of the canvas grid
        self.nx = self.ny = None    # its size (known when this session laid it out)
        self.surface = None         # Surface: ray casts onto the target (built lazily after a resume)
        self.mesh = None            # the target's full-detail DynamicMesh (kept alive for its BVH)
        self.points = set()         # canvas points (i, j)
        self.map = None             # canvas render vertex -> (i, j)
        self.map_key = None
        self.paint = {}             # (i, j) -> painted value
        self.sample = None          # cheap paint signature (every Nth vertex)
        self.changed_at = None
        self.diag = None            # what the last paint read found (see paint_report)
        self.stats = {}


_S = {"targets": [], "tick": None, "next_poll": 0.0, "live": True, "listeners": [], "busy": False}


def _notify(msg):
    _log(msg)
    for fn in list(_S["listeners"]):
        try:
            fn(msg)
        except Exception:
            pass


def active():
    return bool(_S["targets"])


def _snow_data(t):
    if not t.paint:
        return build_snow_grid(None, set(), {})
    _ensure_surface(t)
    return build_snow_grid(t.surface, t.points, t.paint, CONFIG)


def _ensure_surface(t, plan=False):
    """Ray casts onto the target's full-detail mesh (world space). plan=True also lays out a new canvas grid."""
    if t.surface is not None and not plan:
        return t.surface
    comp = _mesh_component(t.actor)
    if comp is None:
        raise RuntimeError("%s has no Static Mesh component" % t.label)
    mesh = read_component(comp)
    n = mesh.get_triangle_count()
    if n <= 0:
        raise RuntimeError("%s has no triangles" % t.label)
    if n > CONFIG["surface_max_tris"]:
        _gs("GeometryScript_MeshSimplification").apply_simplify_to_triangle_count(
            mesh, int(CONFIG["surface_max_tris"]), unreal.GeometryScriptSimplifyMeshOptions())
    lo, hi = mesh_bounds(mesh)
    ray = make_raycaster(mesh, hi[2] + 100.0, (hi[2] - lo[2]) + 200.0)
    if plan or t.grid is None:
        x0, y0, step, k, nx, ny = plan_grid(lo[0], lo[1], hi[0], hi[1], CONFIG)
        t.grid, t.nx, t.ny = (x0, y0, step, k), nx, ny
    t.surface = Surface(ray, *t.grid)
    t.mesh = mesh
    return t.surface


def _make_canvas(t):
    surface = _ensure_surface(t, plan=t.surface is None)
    with unreal.ScopedSlowTask(2 * t.nx + 2, "Snow Painter: draping the paint canvas over %s..." % t.label) as task:
        task.make_dialog(True)

        def progress(i, n):
            if task.should_cancel():
                raise RuntimeError("Cancelled.")
            task.enter_progress_frame(1)

        cpos, ctris, index = make_canvas_grid(surface, t.nx, t.ny, CONFIG, progress)
    if not ctris:
        raise RuntimeError("%s has no surface facing up (seen from above)" % t.label)
    t.points = set(index)
    t.center = bounds_center(cpos)
    black = [(0.0, 0.0, 0.0, 1.0)] * len(cpos)      # Mesh Paint starts from these colors: unpainted
    canvas_dm = write_mesh(unreal.DynamicMesh(), {"positions": cpos, "normals": vertex_normals(cpos, ctris),
                                                  "uvs": planar_uvs(cpos), "colors": black, "triangles": ctris},
                           t.center)
    sm = _new_static_mesh(canvas_dm, "Canvas", "SM_SnowCanvas_%s" % _safe_name(t.label))
    try:
        sm.set_editor_property("allow_cpu_access", True)     # the paint is read back from its render data
    except Exception:
        pass
    actor = _actor_sub().spawn_actor_from_object(sm, unreal.Vector(*t.center), unreal.Rotator(0.0, 0.0, 0.0))
    if actor is None:
        _delete_asset(sm)
        raise RuntimeError("Could not place the paint canvas for %s" % t.label)
    _set_mesh_material(sm, _canvas_material(), actor)
    actor.set_actor_label("SnowCanvas_%s" % t.label)
    x0, y0, step, k = t.grid
    _set_tags(actor, [TAG_CANVAS, TAG_TARGET + t.actor.get_path_name(),
                      TAG_GRID + "%.4f;%.4f;%.4f;%d" % (x0, y0, step, k)])
    _call_first(lambda: actor.set_folder_path("SnowPainter"), lambda: None)
    _call_first(lambda: actor.set_actor_hidden_in_game(True), lambda: None)
    comp = _mesh_component(actor)
    if comp is not None:
        _call_first(lambda: comp.set_cast_shadow(False), lambda: None)
    t.canvas, t.canvas_mesh = actor, sm
    t.paint, t.map, t.map_key, t.sample = {}, None, None, None
    t.stats = {"canvas_points": len(cpos), "canvas_detail": step, "snow_detail": surface.fine,
               "coarsened": step > CONFIG["canvas_detail"] + 1e-6}


def _make_snow_actor(t):
    actor = _actor_sub().spawn_actor_from_class(unreal.DynamicMeshActor, unreal.Vector(*t.center),
                                                unreal.Rotator(0.0, 0.0, 0.0))
    if actor is None:
        raise RuntimeError("Could not place the snow actor for %s" % t.label)
    actor.set_actor_label("Snow_%s" % t.label)
    _set_tags(actor, [TAG_SNOW, TAG_TARGET + t.actor.get_path_name()])
    _call_first(lambda: actor.set_folder_path("SnowPainter"), lambda: None)
    _snow_component(actor).set_material(0, snow_material())
    t.snow = actor


def _snow_component(actor):
    return _call_first(lambda: actor.get_editor_property("dynamic_mesh_component"),
                       lambda: actor.get_dynamic_mesh_component())


def _safe_name(label):
    return re.sub(r"[^A-Za-z0-9_]", "_", str(label))[:48] or "Mesh"


def _selection():
    return [a for a in (_actor_sub().get_selected_level_actors() or []) if a is not None]


def start(actors=None):
    """Lay paint canvases over the given (default: selected) mesh actors and start the live snow."""
    if _S["targets"]:
        raise RuntimeError("A painting session is already running (Bake or Cancel it first).")
    actors = [a for a in (actors if actors is not None else _selection()) if not _is_ours(a) and _mesh_component(a)]
    if not actors:
        raise RuntimeError("Select one or more Static Mesh actors first.")
    done = []
    with unreal.ScopedSlowTask(len(actors), "Snow Painter: preparing paint canvases...") as task:
        task.make_dialog(True)
        for a in actors:
            t = Target(a)
            task.enter_progress_frame(1, "Canvas for %s" % t.label)
            try:
                _make_canvas(t)
                _make_snow_actor(t)
                done.append(t)
            except Exception as e:
                _warn("%s: %s" % (t.label, e))
                _drop(t)
                if not isinstance(e, RuntimeError):
                    _warn(traceback.format_exc())
    if not done:
        raise RuntimeError("No paint canvas could be made (see the Output Log).")
    _S["targets"] = done
    _actor_sub().set_selected_level_actors([t.canvas for t in done])
    _start_tick()
    coarse = ["%s (%.0f cm)" % (t.label, t.stats["canvas_detail"]) for t in done if t.stats.get("coarsened")]
    _notify("Painting %d mesh(es). Mode dropdown (top left) > Mesh Paint > Colors > Paint, then paint with the "
            "left mouse button in white (Shift = erase).%s" % (len(done), (" Big mesh: paint grid coarsened on %s (the snow "
                                                             "itself keeps its detail)."
                                                             % ", ".join(coarse)) if coarse else ""))
    return done


def resume():
    """Reconnect to canvases left in the level by an earlier session (e.g. after reopening the tool)."""
    if _S["targets"]:
        return _S["targets"]
    try:
        actors = _actor_sub().get_all_level_actors() or []
    except Exception:
        return []
    by_target = {}
    for a in actors:
        tags = _tags(a)
        tpath = next((x[len(TAG_TARGET):] for x in tags if x.startswith(TAG_TARGET)), None)
        if tpath is None:
            continue
        entry = by_target.setdefault(tpath, {})
        if TAG_CANVAS in tags:
            entry["canvas"] = a
        elif TAG_SNOW in tags:
            entry["snow"] = a
    found = []
    for tpath, e in by_target.items():
        target = next((a for a in actors if a.get_path_name() == tpath), None)
        if target is None or "canvas" not in e:
            continue
        grid = next((x[len(TAG_GRID):] for x in _tags(e["canvas"]) if x.startswith(TAG_GRID)), None)
        try:
            vals = grid.split(";")
            grid = (float(vals[0]), float(vals[1]), float(vals[2]), int(vals[3]))
        except Exception:
            _warn("%s: canvas from an older version - Cancel it and Start painting again." % e["canvas"].get_name())
            continue
        t = Target(target)
        t.grid = grid
        t.canvas = e["canvas"]
        comp = _mesh_component(t.canvas)
        t.canvas_mesh = _call_first(lambda: comp.get_editor_property("static_mesh"), lambda: None) if comp else None
        loc = t.canvas.get_actor_location()
        t.center = (loc.x, loc.y, loc.z)
        if e.get("snow") is not None:
            t.snow = e["snow"]
        else:
            _make_snow_actor(t)
        found.append(t)
    if found:
        _S["targets"] = found
        _start_tick()
        refresh(force=True)
        _notify("Resumed painting on %d mesh(es)." % len(found))
    return found


def _read_paint(t, full=False):
    """Read the canvas paint. Returns True when it changed since the last read."""
    comp = _mesh_component(t.canvas)
    mesh = read_component(comp, want_colors=True)
    colors = mesh_colors(mesh)
    loc = t.canvas.get_actor_location()
    key = (len(colors), mesh.get_triangle_count(), round(loc.x, 2), round(loc.y, 2), round(loc.z, 2))
    step = max(1, int(CONFIG["poll_sample_step"]))
    sample = sum(colors[i].r for i in range(0, len(colors), step)) if colors else 0.0
    if not full and t.map_key == key and t.sample is not None and abs(sample - t.sample) < 1e-6:
        return False
    if t.map_key != key:
        x0, y0, gstep, _k = t.grid
        pos, tris = mesh_geometry(mesh)
        t.map = [(int(round((p[0] - x0) / gstep)), int(round((p[1] - y0) / gstep))) for p in pos]
        used = {v for tri in tris for v in tri}
        t.points = {t.map[v] for v in used}
        t.map_key = key
        t.stats.setdefault("canvas_points", len(t.points))
        t.stats.setdefault("canvas_detail", gstep)
    paint = {}
    for idx, c in zip(t.map, colors):
        r = c.r
        if r > paint.get(idx, 0.0):
            paint[idx] = r
    t.diag = {"colors": len(colors), "vertices": len(t.map or []), "points": len(t.points),
              "painted": sum(1 for v in paint.values() if v >= CONFIG["paint_threshold"]),
              "brightest": max(paint.values()) if paint else 0.0}
    changed = paint != t.paint
    t.paint, t.sample = paint, sample
    return changed


def _rebuild(t):
    data = _snow_data(t)
    comp = _snow_component(t.snow)
    dm = comp.get_dynamic_mesh()
    loc = t.snow.get_actor_location()
    write_mesh(dm, data, (loc.x, loc.y, loc.z))
    _call_first(lambda: comp.notify_mesh_updated(), lambda: None)
    t.stats["snow_triangles"] = len(data["triangles"])
    return data


def _check_targets():
    alive = []
    for t in _S["targets"]:
        if _alive(t.actor) and _alive(t.canvas) and _alive(t.snow):
            alive.append(t)
        else:
            keep = _alive(t.snow)
            _notify("%s: its mesh, canvas or snow actor was deleted - dropped from the session.%s" % (
                t.label, " Its snow stays in the level as a Dynamic Mesh actor." if keep else ""))
            _drop(t, keep_snow=keep)
            if keep:
                _set_tags(t.snow, [])          # no longer part of a session (resume ignores it)
    _S["targets"] = alive
    if not alive:
        _stop_tick()


def refresh(force=False):
    """Re-read the paint (force: even if the cheap check sees no change) and rebuild the snow."""
    _check_targets()
    n = 0
    for t in _S["targets"]:
        try:
            _read_paint(t, full=True) if force else _read_paint(t)
            _rebuild(t)
            n += 1
        except Exception as e:
            _warn("%s: %s\n%s" % (t.label, e, traceback.format_exc()))
    return n


def paint_report():
    """What the last paint read found, per mesh (to tell 'not painted' from 'paint not readable')."""
    out = []
    for t in _S["targets"]:
        d = getattr(t, "diag", None)
        if d is None:
            out.append("%s: paint not read yet" % t.label)
        elif not d["colors"]:
            out.append("%s: the canvas has no readable vertex colors (Mesh Paint may be painting a texture, or "
                       "another mesh)" % t.label)
        else:
            out.append("%s: %d of %d canvas points painted (brightest red %.2f)%s" % (
                t.label, d["painted"], d["points"], d["brightest"],
                "" if d["painted"] else " - is Mesh Paint painting this canvas, in white, with Red ticked?"))
    return out


def update():
    """Rebuild the snow now from the current paint (and resume live updates if an error paused them)."""
    n = refresh(force=True)
    _S["live"] = True
    report = paint_report()
    for line in report:
        _log(line)
    _notify("Snow updated. " + " | ".join(report) if report else "Snow updated on %d mesh(es)." % n)
    return n


def set_params(**kw):
    """Change shape settings (depth, softness, max_slope, pile_up, clumps, clump_size, edge_sink...) and rebuild
    from the paint already read - no re-read needed."""
    for k, v in kw.items():
        if k not in CONFIG:
            raise KeyError(k)
        CONFIG[k] = type(CONFIG[k])(v) if not isinstance(CONFIG[k], str) else str(v)
    for t in _S["targets"]:
        try:
            if "snow_material" in kw:
                _snow_component(t.snow).set_material(0, snow_material())
            _rebuild(t)
        except Exception as e:
            _warn("%s: %s" % (t.label, e))


def _tick(_dt):
    if _S["busy"] or not _S["targets"]:
        return
    now = time.time()
    if now < _S["next_poll"]:
        return
    _S["next_poll"] = now + float(CONFIG["poll_seconds"])
    if not _S["live"]:
        return
    _S["busy"] = True
    try:
        _check_targets()
        for t in _S["targets"]:
            try:
                if _read_paint(t):
                    t.changed_at = now           # still painting: wait until the stroke ends
                elif t.changed_at is not None and now - t.changed_at >= float(CONFIG["settle_seconds"]):
                    t.changed_at = None
                    data = _rebuild(t)
                    _notify("%s: snow rebuilt (%d triangles)." % (t.label, len(data["triangles"])))
            except Exception as e:
                t.changed_at = None
                _S["live"] = False               # don't repeat the same error twice a second
                _warn("%s: %s\n%s" % (t.label, e, traceback.format_exc()))
                _notify("Live update paused: %s: %s. Press Update now to retry." % (t.label, e))
                break
    finally:
        _S["busy"] = False


def _start_tick():
    if _S["tick"] is None:
        _S["tick"] = unreal.register_slate_post_tick_callback(_tick)


def _stop_tick():
    if _S["tick"] is not None:
        try:
            unreal.unregister_slate_post_tick_callback(_S["tick"])
        except Exception:
            pass
        _S["tick"] = None


def _drop(t, keep_snow=False):
    """Remove a target's canvas (actor + asset) and, unless keep_snow, its live snow actor."""
    sub = _actor_sub()
    for actor in ([t.canvas] + ([] if keep_snow else [t.snow])):
        if _alive(actor):
            try:
                sub.destroy_actor(actor)
            except Exception as e:
                _warn("Could not remove %s: %s" % (actor.get_name(), e))
    if t.canvas_mesh is not None:
        _delete_asset(t.canvas_mesh)
    t.canvas = t.canvas_mesh = None
    if not keep_snow:
        t.snow = None


def clear_paint():
    """Start over: fresh, unpainted canvases (the snow disappears)."""
    if not _S["targets"]:
        return 0
    for t in _S["targets"]:
        _drop(t, keep_snow=True)
        if t.nx is None:
            t.surface = None                  # resumed session: re-plan the grid
        _make_canvas(t)
        _rebuild(t)
    _actor_sub().set_selected_level_actors([t.canvas for t in _S["targets"]])
    _notify("Paint cleared.")
    return len(_S["targets"])


def bake(nanite=None):
    """Turn the snow into Static Mesh assets + actors, then end the session (canvases removed).
    Returns the new actors."""
    if not _S["targets"]:
        raise RuntimeError("No painting session.")
    nanite = CONFIG["bake_nanite"] if nanite is None else bool(nanite)
    refresh(force=True)
    out = []
    mat = snow_material()
    for t in list(_S["targets"]):
        data = _snow_data(t)
        if not data["triangles"]:
            _notify("%s: nothing painted - no snow baked." % t.label)
            continue
        dm = write_mesh(unreal.DynamicMesh(), data, t.center)
        sm = _new_static_mesh(dm, "Baked", "SM_Snow_%s" % _safe_name(t.label), nanite=nanite, collision=True)
        _set_mesh_material(sm, mat)
        actor = _actor_sub().spawn_actor_from_object(sm, unreal.Vector(*t.center), unreal.Rotator(0.0, 0.0, 0.0))
        if actor is not None:
            _set_mesh_material(sm, mat, actor)
            actor.set_actor_label("Snow_%s" % t.label)
            _call_first(lambda: actor.set_folder_path("SnowPainter"), lambda: None)
            out.append(actor)
    for t in _S["targets"]:
        _drop(t)
    _S["targets"] = []
    _stop_tick()
    if out:
        _actor_sub().set_selected_level_actors(out)
    _notify("Baked %d snow mesh(es) into %s. Save to keep them." % (len(out), _asset_folder("Baked")))
    return out


def cancel():
    """End the session without baking: canvases and live snow are removed."""
    for t in _S["targets"]:
        _drop(t)
    n = len(_S["targets"])
    _S["targets"] = []
    _stop_tick()
    _notify("Session cancelled.")
    return n


def stats():
    return [dict(t.stats, label=t.label, painted=sum(1 for w in t.paint.values() if w >= CONFIG["paint_threshold"]))
            for t in _S["targets"]]


# =============================================================================
# Qt loading (PySide6 / PyQt6 / PySide2 / PyQt5). The install folder is shared with World Performance Audit.
# =============================================================================
_QT = None


def _deps_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "UnrealWorldPerfAudit", "py%d%d" % sys.version_info[:2], "site-packages")


def _load_qt():
    global _QT
    if _QT is not None:
        return _QT
    d = _deps_dir()
    if os.path.isdir(d) and d not in sys.path:
        sys.path.append(d)      # appended (never shadows engine modules); no .pth files are executed
    for binding in ("PySide6", "PyQt6", "PySide2", "PyQt5"):
        try:
            mods = [importlib.import_module("%s.%s" % (binding, m)) for m in ("QtCore", "QtGui", "QtWidgets")]
            _QT = tuple(mods)
            return _QT
        except Exception:
            continue
    return None


def install_pyside6():
    """pip-install PySide6 (Essentials) into a per-user folder, outside the project. One time only."""
    target = _deps_dir()
    if not os.path.isdir(target):
        os.makedirs(target)
    py = unreal.get_interpreter_executable_path()
    cmd = [py, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--upgrade",
           "--isolated", "--index-url", "https://pypi.org/simple",
           "--only-binary=:all:", "--target", target, "PySide6-Essentials>=6.5,<7"]
    _log("Installing PySide6: %s" % " ".join(cmd))
    with unreal.ScopedSlowTask(1, "Installing PySide6 for %s (one-time, ~100 MB)..." % TOOL_NAME) as task:
        task.make_dialog(False)
        task.enter_progress_frame(1)
        kw = {}
        if sys.platform == "win32":
            kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
    out = proc.stdout.decode("utf-8", "replace") if proc.stdout else ""
    if proc.returncode != 0:
        _warn("pip failed (%d):\n%s" % (proc.returncode, out))
        unreal.EditorDialog.show_message(TOOL_NAME, "PySide6 install failed - see the Output Log.", unreal.AppMsgType.OK)
        return False
    importlib.invalidate_caches()
    return _load_qt() is not None


# =============================================================================
# Qt UI
# =============================================================================
_STYLE = """
* { font-family: "Segoe UI", "Inter", "Roboto", sans-serif; font-size: 9pt; }
QWidget#SnowRoot { background: #18181b; }
QWidget { color: #e4e4e7; }
QFrame#Header { background: #111113; border-bottom: 1px solid #27272a; }
QLabel#Logo { background: #38bdf8; color: #0b1220; border-radius: 6px; font-weight: 800; font-size: 10pt; }
QLabel#Title { font-size: 13pt; font-weight: 600; color: #fafafa; }
QLabel#Muted, QLabel#Subtitle { color: #8e8e96; }
QFrame#Card { background: #1f1f23; border: 1px solid #2a2a2e; border-radius: 6px; }
QLabel#Step { color: #38bdf8; font-weight: 700; font-size: 8pt; }
QLabel#CardTitle { color: #fafafa; font-weight: 600; font-size: 10pt; }
QLabel#Value { color: #e4e4e7; font-weight: 600; min-width: 46px; }
QPushButton { background: #27272a; color: #e4e4e7; border: 1px solid #34343a; border-radius: 5px; padding: 6px 14px; }
QPushButton:hover { background: #303036; border-color: #45454d; }
QPushButton:disabled { color: #5c5c63; background: #1f1f23; border-color: #2a2a2e; }
QPushButton#Primary { background: #0284c7; border-color: #0284c7; color: #ffffff; font-weight: 600; }
QPushButton#Primary:hover { background: #0ea5e9; }
QPushButton#Primary:disabled { background: #123247; border-color: #123247; color: #7c9cb3; }
QPushButton#Danger { background: transparent; border-color: #52262b; color: #fca5a5; }
QPushButton#Danger:hover { background: #3b1d21; }
QLineEdit, QDoubleSpinBox { background: #111113; color: #e4e4e7; border: 1px solid #34343a; border-radius: 5px; padding: 4px 8px; }
QLineEdit:focus, QDoubleSpinBox:focus { border-color: #0284c7; }
QSlider::groove:horizontal { height: 4px; background: #34343a; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #0ea5e9; border-radius: 2px; }
QSlider::handle:horizontal { background: #e4e4e7; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; }
QCheckBox { spacing: 6px; color: #c4c4cc; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #45454d; border-radius: 3px; background: #111113; }
QCheckBox::indicator:checked { background: #0284c7; border-color: #0284c7; }
QFrame#StatusBar { background: #111113; border-top: 1px solid #27272a; }
QToolTip { background: #27272a; color: #e4e4e7; border: 1px solid #3f3f46; padding: 4px; }
"""

# (config key, label, minimum, maximum, step, tooltip)
_SLIDERS = [
    ("depth", "Depth (cm)", 1.0, 60.0, 0.5, "Snow thickness where fully painted, on flat ground."),
    ("softness", "Soft edges", 0, 8, 1, "Edge softening passes: rounder, softer snow edges (also spreads a little)."),
    ("max_slope", "Max slope (\u00b0)", 10.0, 85.0, 1.0, "Faces steeper than this hold no snow."),
    ("pile_up", "Pile up", 0.0, 1.0, 0.05, "0: snow grows along the surface. 1: it piles up vertically."),
    ("clumps", "Clumps", 0.0, 1.0, 0.05, "Thickness variation."),
    ("clump_size", "Clump size (cm)", 10.0, 400.0, 5.0, "Size of the thickness variation."),
    ("edge_sink", "Edge sink (cm)", 0.0, 5.0, 0.1, "How far the thin snow edge dips under the surface (hides the seam)."),
]


def _make_window_class(QtCore, QtGui, QtWidgets):
    Qt = QtCore.Qt

    class SnowWindow(QtWidgets.QWidget):
        def __init__(self):
            super(SnowWindow, self).__init__(None)
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("%s %s" % (TOOL_NAME, __version__))
            self.setWindowFlags(Qt.WindowType.Window)
            self.resize(470, 860)
            self.setMinimumWidth(420)
            self._values = {}
            self._sliders = {}
            self._timer = QtCore.QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.setInterval(250)
            self._timer.timeout.connect(self._apply_params)
            self._pending = {}
            root = QtWidgets.QWidget(self)
            root.setObjectName("SnowRoot")
            outer = QtWidgets.QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(root)
            self._build(root)
            self.setStyleSheet(_STYLE)
            _S["listeners"].append(self._on_event)
            try:
                resume()
            except Exception as e:
                _warn("Resume failed: %s" % e)
            self._refresh()

        # ------------------------------------------------------------------ layout
        def _btn(self, text, slot, name=None, tip=None):
            b = QtWidgets.QPushButton(text)
            if name:
                b.setObjectName(name)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(lambda *_a: slot())
            b.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))
            return b

        def _card(self, lay, step, title):
            card = QtWidgets.QFrame()
            card.setObjectName("Card")
            v = QtWidgets.QVBoxLayout(card)
            v.setContentsMargins(14, 10, 14, 12)
            v.setSpacing(8)
            s = QtWidgets.QLabel(step)
            s.setObjectName("Step")
            t = QtWidgets.QLabel(title)
            t.setObjectName("CardTitle")
            v.addWidget(s)
            v.addWidget(t)
            lay.addWidget(card)
            return v

        def _build(self, root):
            lay = QtWidgets.QVBoxLayout(root)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            header = QtWidgets.QFrame()
            header.setObjectName("Header")
            hl = QtWidgets.QHBoxLayout(header)
            hl.setContentsMargins(16, 12, 16, 12)
            logo = QtWidgets.QLabel("SP")
            logo.setObjectName("Logo")
            logo.setFixedSize(34, 34)
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            titles = QtWidgets.QVBoxLayout()
            titles.setSpacing(0)
            t = QtWidgets.QLabel(TOOL_NAME)
            t.setObjectName("Title")
            st = QtWidgets.QLabel("v%s  \u00b7  paint snow \u00b7 Geometry Script" % __version__)
            st.setObjectName("Subtitle")
            titles.addWidget(t)
            titles.addWidget(st)
            hl.addWidget(logo)
            hl.addSpacing(10)
            hl.addLayout(titles)
            hl.addStretch(1)
            lay.addWidget(header)

            body = QtWidgets.QWidget()
            bl = QtWidgets.QVBoxLayout(body)
            bl.setContentsMargins(14, 12, 14, 12)
            bl.setSpacing(10)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            scroll.setWidget(body)
            scroll.setStyleSheet("QScrollArea { background: #18181b; } QScrollArea > QWidget > QWidget { background: #18181b; }")
            lay.addWidget(scroll, 1)

            c1 = self._card(bl, "STEP 1", "Pick the meshes")
            self.lbl_targets = QtWidgets.QLabel("")
            self.lbl_targets.setWordWrap(True)
            self.lbl_targets.setTextFormat(Qt.TextFormat.PlainText)
            self.lbl_targets.setObjectName("Muted")
            c1.addWidget(self.lbl_targets)
            row = QtWidgets.QHBoxLayout()
            self.btn_start = self._btn("Start painting", self.on_start, "Primary",
                                       "Lays a paint canvas over the selected Static Mesh actors (they aren't changed).")
            row.addWidget(self.btn_start)
            row.addStretch(1)
            c1.addLayout(row)

            c2 = self._card(bl, "STEP 2", "Paint in the viewport")
            howto = QtWidgets.QLabel(
                "1. Open the mode dropdown at the top left of the editor (it says e.g. <i>Selection Mode</i> or "
                "<i>Modeling Mode</i>) and pick <b>Mesh Paint</b>. Not in the list? Edit &gt; Plugins, search "
                "<i>Mesh Paint</i>, enable it and restart the editor.<br>"
                "2. Pick <b>Colors</b> (<i>Vertex Color</i>) &gt; <b>Paint</b>, keep the paint color white, and paint "
                "with the left mouse button; hold Shift to erase. Nothing happens? Select <b>SnowCanvas_...</b> in "
                "the Outliner (folder SnowPainter).<br>"
                "3. Painted areas glow light blue. The snow appears when you release the mouse.")
            howto.setWordWrap(True)
            howto.setTextFormat(Qt.TextFormat.RichText)
            c2.addWidget(howto)
            row = QtWidgets.QHBoxLayout()
            self.chk_live = QtWidgets.QCheckBox("Live update")
            self.chk_live.setChecked(True)
            self.chk_live.toggled.connect(lambda on: _S.__setitem__("live", bool(on)))
            self.btn_update = self._btn("Update now", self.on_update)
            self.btn_clear = self._btn("Clear paint", self.on_clear, None, "Start over with an unpainted canvas.")
            row.addWidget(self.chk_live)
            row.addStretch(1)
            row.addWidget(self.btn_clear)
            row.addWidget(self.btn_update)
            c2.addLayout(row)

            c3 = self._card(bl, "STEP 3", "Shape the snow")
            grid = QtWidgets.QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(6)
            for r, (key, label, lo, hi, step, tip) in enumerate(_SLIDERS):
                lab = QtWidgets.QLabel(label)
                lab.setToolTip(tip)
                s = QtWidgets.QSlider(Qt.Orientation.Horizontal)
                n = int(round((hi - lo) / step))
                s.setRange(0, n)
                s.setValue(int(round((float(CONFIG[key]) - lo) / step)))
                s.setToolTip(tip)
                val = QtWidgets.QLabel("")
                val.setObjectName("Value")
                val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                s.valueChanged.connect(lambda v, key=key, lo=lo, step=step: self._slider(key, lo + v * step))
                grid.addWidget(lab, r, 0)
                grid.addWidget(s, r, 1)
                grid.addWidget(val, r, 2)
                self._sliders[key] = s
                self._values[key] = val
                self._show_value(key, CONFIG[key])
            c3.addLayout(grid)
            mrow = QtWidgets.QHBoxLayout()
            self.txt_mat = QtWidgets.QLineEdit(str(CONFIG["snow_material"]))
            self.txt_mat.setPlaceholderText("Snow material (empty: built-in)")
            self.txt_mat.editingFinished.connect(lambda: self._queue("snow_material", self.txt_mat.text().strip()))
            use = self._btn("Use selected", self.on_use_material, None,
                            "Use the material selected in the Content Browser.")
            mrow.addWidget(self.txt_mat, 1)
            mrow.addWidget(use)
            c3.addLayout(mrow)
            drow = QtWidgets.QHBoxLayout()
            dl = QtWidgets.QLabel("Paint grid / snow detail (cm)")
            dl.setToolTip("Paint grid: precision of the paint (coarsened automatically on big meshes).\n"
                          "Snow detail: spacing of the snow vertices where you painted.\nBoth apply to the next "
                          "Start painting.")
            self.spin_detail = QtWidgets.QDoubleSpinBox()
            self.spin_detail.setRange(2.0, 100.0)
            self.spin_detail.setSingleStep(1.0)
            self.spin_detail.setValue(float(CONFIG["canvas_detail"]))
            self.spin_detail.valueChanged.connect(lambda v: CONFIG.__setitem__("canvas_detail", float(v)))
            self.spin_snow = QtWidgets.QDoubleSpinBox()
            self.spin_snow.setRange(1.0, 50.0)
            self.spin_snow.setSingleStep(1.0)
            self.spin_snow.setValue(float(CONFIG["snow_detail"]))
            self.spin_snow.valueChanged.connect(lambda v: CONFIG.__setitem__("snow_detail", float(v)))
            drow.addWidget(dl)
            drow.addStretch(1)
            drow.addWidget(self.spin_detail)
            drow.addWidget(self.spin_snow)
            c3.addLayout(drow)

            c4 = self._card(bl, "STEP 4", "Finish")
            frow = QtWidgets.QHBoxLayout()
            self.chk_nanite = QtWidgets.QCheckBox("Nanite")
            self.chk_nanite.setChecked(bool(CONFIG["bake_nanite"]))
            self.chk_nanite.toggled.connect(lambda on: CONFIG.__setitem__("bake_nanite", bool(on)))
            self.btn_bake = self._btn("Bake to Static Mesh", self.on_bake, "Primary",
                                      "Creates a Static Mesh asset + actor per painted mesh in %s/Baked and removes "
                                      "the canvases. Save to keep it." % CONFIG["asset_folder"])
            self.btn_cancel = self._btn("Cancel", self.on_cancel, "Danger", "Remove the canvases and the live snow.")
            frow.addWidget(self.chk_nanite)
            frow.addStretch(1)
            frow.addWidget(self.btn_cancel)
            frow.addWidget(self.btn_bake)
            c4.addLayout(frow)
            bl.addStretch(1)

            sb = QtWidgets.QFrame()
            sb.setObjectName("StatusBar")
            sbl = QtWidgets.QHBoxLayout(sb)
            sbl.setContentsMargins(14, 6, 14, 6)
            self.lbl_status = QtWidgets.QLabel("Select mesh actors, then Start painting.")
            self.lbl_status.setTextFormat(Qt.TextFormat.PlainText)
            self.lbl_status.setWordWrap(True)
            sbl.addWidget(self.lbl_status, 1)
            lay.addWidget(sb)

        # ------------------------------------------------------------------ state
        def _show_value(self, key, v):
            self._values[key].setText(("%d" % v) if isinstance(CONFIG[key], int) else ("%.2f" % v).rstrip("0").rstrip("."))

        def _slider(self, key, v):
            v = int(round(v)) if isinstance(CONFIG[key], int) else round(float(v), 3)
            self._show_value(key, v)
            self._queue(key, v)

        def _queue(self, key, v):
            self._pending[key] = v
            self._timer.start()          # rebuild once the slider stops moving

        def _apply_params(self):
            kw, self._pending = self._pending, {}
            if not kw:
                return
            try:
                set_params(**kw)
            except Exception as e:
                self._set_status("Settings: %s" % e)

        def _set_status(self, text):
            self.lbl_status.setText(text)

        def _on_event(self, text):
            self._set_status(text)
            self._refresh()

        def _refresh(self):
            on = active()
            if self.chk_live.isChecked() != bool(_S["live"]):
                self.chk_live.blockSignals(True)
                self.chk_live.setChecked(bool(_S["live"]))
                self.chk_live.blockSignals(False)
            self.btn_start.setEnabled(not on)
            for b in (self.btn_update, self.btn_clear, self.btn_bake, self.btn_cancel):
                b.setEnabled(on)
            if on:
                lines = []
                for s in stats():
                    parts = []
                    if s.get("canvas_points"):
                        parts.append("paint grid %s points every %.0f cm" % (
                            "{:,}".format(s["canvas_points"]), s.get("canvas_detail", 0.0)))
                    if s.get("snow_detail"):
                        parts.append("snow detail %.1f cm" % s["snow_detail"])
                    if s.get("snow_triangles"):
                        parts.append("snow %s triangles" % "{:,}".format(s["snow_triangles"]))
                    lines.append("%s%s" % (s["label"], (" \u2013 " + ", ".join(parts)) if parts else ""))
                self.lbl_targets.setText("Painting:\n" + "\n".join(lines))
            else:
                self.lbl_targets.setText("Select one or more Static Mesh actors in the level (rocks, roofs, "
                                         "ledges...). Your meshes aren't modified.")

        def _run(self, fn, ok_text=None):
            try:
                res = fn()
                if ok_text:
                    self._set_status(ok_text(res) if callable(ok_text) else ok_text)
            except Exception as e:
                self._set_status(str(e))
                if not isinstance(e, RuntimeError):
                    _warn(traceback.format_exc())
            self._refresh()

        # ------------------------------------------------------------------ actions
        def on_start(self):
            self._run(start)

        def on_update(self):
            self._run(update)

        def on_clear(self):
            self._run(clear_paint)

        def on_bake(self):
            self._run(lambda: bake(self.chk_nanite.isChecked()))

        def on_cancel(self):
            self._run(cancel)

        def on_use_material(self):
            try:
                sel = [a for a in (unreal.EditorUtilityLibrary.get_selected_assets() or [])
                       if isinstance(a, unreal.MaterialInterface)]
            except Exception:
                sel = []
            if not sel:
                self._set_status("Select a material in the Content Browser first.")
                return
            path = sel[0].get_path_name().split(".")[0]
            self.txt_mat.setText(path)
            self._queue("snow_material", path)
            self._set_status("Snow material: %s" % path)

        def closeEvent(self, event):
            try:
                _S["listeners"].remove(self._on_event)
            except ValueError:
                pass
            _stop_qt_tick()
            super(SnowWindow, self).closeEvent(event)

    return SnowWindow


_TICK = {"handle": None}


def _start_qt_tick(QtWidgets):
    # Windows: Unreal's message pump already drives Qt windows. Elsewhere Qt needs a nudge every frame.
    if sys.platform == "win32" or _TICK["handle"] is not None:
        return

    def _qt_tick(_dt):
        try:
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass
    _TICK["handle"] = unreal.register_slate_post_tick_callback(_qt_tick)


def _stop_qt_tick():
    if _TICK["handle"] is not None:
        try:
            unreal.unregister_slate_post_tick_callback(_TICK["handle"])
        except Exception:
            pass
        _TICK["handle"] = None


def show(reuse=True):
    """Open the tool window (offers to install PySide6 if Qt is missing)."""
    qt = _load_qt()
    if qt is None:
        r = unreal.EditorDialog.show_message(
            TOOL_NAME, "The panel needs Qt for Python (PySide6), which Unreal doesn't ship.\n\n"
            "Yes: install PySide6 now (one-time, ~100 MB, into\n%s)\n"
            "No: text mode - use snow_painter.start(), update(), bake(), cancel() in the Output Log." % _deps_dir(),
            unreal.AppMsgType.YES_NO_CANCEL)
        if r == unreal.AppReturnType.YES and install_pyside6():
            qt = _load_qt()
        if qt is None:
            _log("Text mode: select meshes, then snow_painter.start(); paint in Mesh Paint mode; "
                 "snow_painter.bake() when done.")
            return None
    QtCore, QtGui, QtWidgets = qt
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    for w in app.topLevelWidgets():
        if w.objectName() == WINDOW_OBJECT_NAME:
            if reuse:
                w.show()
                w.raise_()
                w.activateWindow()
                return w
            w.close()
            w.deleteLater()
    win = _make_window_class(QtCore, QtGui, QtWidgets)()
    win.show()
    try:
        unreal.parent_external_window_to_slate(int(win.winId()))
    except Exception:
        pass
    _start_qt_tick(QtWidgets)
    keep = sys.__dict__.setdefault("_snow_painter_keep", {})
    keep["app"], keep["window"] = app, win
    return win


if unreal is not None and not __name__.endswith("snow_painter"):
    # Pasted into the Output Log or run as a script file: register this code as the module "snow_painter" so
    # snow_painter.bake() etc. work afterwards, then open the panel.
    _old = sys.modules.get("snow_painter")
    if _old is not None:                     # pasted again: stop the previous copy's live-update tick
        try:
            _old._stop_tick()
        except Exception:
            pass
    _module = types.ModuleType("snow_painter")
    _module.__dict__.update(globals())
    _module.__name__ = "snow_painter"
    sys.modules["snow_painter"] = _module
    show(reuse=False)
