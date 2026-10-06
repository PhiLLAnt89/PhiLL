"""Snow Painter geometry core (pure Python): canvas refinement, canvas faces, snow surface."""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import snow_painter as S


def quad(size, z=0.0, x0=0.0, y0=0.0):
    p = [(x0, y0, z), (x0 + size, y0, z), (x0 + size, y0 + size, z), (x0, y0 + size, z)]
    return p, [(0, 1, 2), (0, 2, 3)]


def edges(tris):
    count = {}
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            k = (min(u, v), max(u, v))
            count[k] = count.get(k, 0) + 1
    return count


def on_border(p, q, lo, hi):
    return any(abs(p[k] - e) < 1e-6 and abs(q[k] - e) < 1e-6 for k in (0, 1) for e in (lo, hi))


# --- refine: conforming, even, same shape -----------------------------------------------------------------
pos, tris = quad(100.0)
rp, rt, reached = S.refine(pos, tris, 8.0)
assert reached
assert all(math.sqrt(S._dist2(rp[u], rp[v])) <= 8.0 + 1e-9 for u, v in edges(rt)), "edge longer than the detail"
assert abs(S.triangle_area(rp, rt) - 10000.0) < 1e-6, "shape / area must not change"
for (u, v), n in edges(rt).items():
    assert n <= 2
    if n == 1:
        assert on_border(rp[u], rp[v], 0.0, 100.0), "open edge inside the mesh = crack / T-junction"
assert all(S.face_normal(rp, t)[2] > 0 for t in rt), "winding preserved"
print("refine square: %d -> %d triangles" % (len(tris), len(rt)))

# irregular triangulation (fan + slivers): still conforming
random.seed(3)
pts = [(0.0, 0.0, 0.0), (300.0, 0.0, 0.0), (300.0, 200.0, 0.0), (0.0, 200.0, 0.0), (150.0, 100.0, 0.0),
       (290.0, 10.0, 0.0)]
irr = [(0, 1, 5), (0, 5, 4), (5, 2, 4), (5, 1, 2), (2, 3, 4), (3, 0, 4)]
rp, rt, _ok = S.refine(pts, irr, 11.0)
for (u, v), n in edges(rt).items():
    assert n <= 2
    if n == 1:
        p, q = rp[u], rp[v]
        assert (abs(p[1]) < 1e-6 and abs(q[1]) < 1e-6) or (abs(p[1] - 200) < 1e-6 and abs(q[1] - 200) < 1e-6) or \
            (abs(p[0]) < 1e-6 and abs(q[0]) < 1e-6) or (abs(p[0] - 300) < 1e-6 and abs(q[0] - 300) < 1e-6), (p, q)
assert abs(S.triangle_area(rp, rt) - 60000.0) < 1e-3
print("refine irregular: %d triangles, conforming" % len(rt))

# budget: stops before exceeding it
rp, rt, reached = S.refine(pos, tris, 1.0, max_tris=500)
assert not reached and len(rt) <= 500
print("refine budget: OK (%d)" % len(rt))

# --- canvas: only faces that can hold snow, lifted off the surface, coarsened to the budget ------------------
top, ttop = quad(100.0, z=50.0)
wall = [(0, 0, 0), (100, 0, 0), (100, 0, 50), (0, 0, 50)]
under = [(0, 0, 0), (0, 100, 0), (100, 100, 0), (100, 0, 0)]            # faces down
mesh_p = top + wall + under
mesh_t = ttop + [(4, 5, 6), (4, 6, 7)] + [(8, 9, 10), (8, 10, 11)]
cp, ct, info = S.make_canvas(mesh_p, mesh_t, {"canvas_detail": 10.0})
assert ct and all(abs(p[2] - (50.0 + S.CONFIG["canvas_offset"])) < 1e-6 for p in cp), "only the top, lifted"
assert info["detail"] == 10.0 and info["reached"]
cp2, ct2, info2 = S.make_canvas(mesh_p, mesh_t, {"canvas_detail": 1.0, "canvas_max_tris": 2000})
assert len(ct2) <= 2000 and info2["detail"] > 1.0, "coarsened to stay under the budget"
assert S.make_canvas(wall, [(0, 1, 2), (0, 2, 3)])[1] == [], "a wall holds no snow"
print("canvas: OK (%d tris; budgeted %d at %.1f cm)" % (len(ct), len(ct2), info2["detail"]))

# --- snow ---------------------------------------------------------------------------------------------------------
gp, gt, _ = S.refine(*quad(400.0, z=0.0), max_edge=8.0)
center = (200.0, 200.0)


def disc(points, r):
    return [1.0 if math.hypot(p[0] - center[0], p[1] - center[1]) < r else 0.0 for p in points]


params = {"depth": 12.0, "softness": 3, "clumps": 0.0, "edge_sink": 1.5}
snow = S.build_snow(gp, gt, disc(gp, 80.0), params)
sp = snow["positions"]
assert snow["triangles"] and len(sp) == len(snow["normals"]) == len(snow["uvs"]) == len(snow["colors"])
inner = [p for p in sp if math.hypot(p[0] - 200, p[1] - 200) < 40]
assert inner and all(abs(p[2] - 12.0) < 1e-6 for p in inner), "full depth inside the painted area (no clumps)"
assert max(math.hypot(p[0] - 200, p[1] - 200) for p in sp) < 80.0 + 3 * 8.0 + 8.0 + 1e-6, "edges spread only a little"
rim = [p for p, c in zip(sp, snow["colors"]) if c[0] < 0.01]           # the outermost ring of the snow
assert rim and all(-1.5 - 1e-6 <= p[2] < -0.5 for p in rim), "the snow rim dips under the surface: no seam"
assert all(n[2] > 0 for n in snow["normals"]), "snow faces up"
assert all(S.face_normal(sp, t)[2] > 0 for t in snow["triangles"]), "winding faces up"
p0, uv0 = sp[0], snow["uvs"][0]
assert abs(uv0[0] - p0[0] / S.CONFIG["uv_scale"]) < 1e-9
print("snow disc: %d tris, depth %.1f, rim %.1f" % (len(snow["triangles"]), max(p[2] for p in sp), min(p[2] for p in sp)))

# clumps vary the thickness, deterministically; the seed changes it
c1 = S.build_snow(gp, gt, disc(gp, 80.0), dict(params, clumps=0.6))
c2 = S.build_snow(gp, gt, disc(gp, 80.0), dict(params, clumps=0.6))
c3 = S.build_snow(gp, gt, disc(gp, 80.0), dict(params, clumps=0.6, seed=99))
assert c1["positions"] == c2["positions"] and c1["positions"] != c3["positions"]
zs = [p[2] for p in c1["positions"] if math.hypot(p[0] - 200, p[1] - 200) < 40]
assert max(zs) - min(zs) > 1.0 and min(zs) >= 0.0
print("clumps: %.1f..%.1f cm" % (min(zs), max(zs)))

# slope: a 30 degree roof holds snow, a 70 degree one doesn't
for angle, expect in ((30.0, True), (70.0, False)):
    a = math.radians(angle)
    roof = [(x, y * math.cos(a), y * math.sin(a)) for x, y, _z in gp]
    out = S.build_snow(roof, gt, disc(gp, 80.0), params)
    assert bool(out["triangles"]) == expect, (angle, len(out["triangles"]))
print("slope limit: OK")

# split vertices (render data): same snow as the welded mesh, no cracks
split_p, split_t, split_w = [], [], []
w = disc(gp, 80.0)
for t in gt:
    base = len(split_p)
    for v in t:
        split_p.append(gp[v])
        split_w.append(w[v])
    split_t.append((base, base + 1, base + 2))
s_split = S.build_snow(split_p, split_t, split_w, params)
s_weld = S.build_snow(gp, gt, w, params)
assert sorted(s_split["positions"]) == sorted(s_weld["positions"]), "split render vertices must weld"
assert len(s_split["triangles"]) == len(s_weld["triangles"])
print("split vertices weld: OK")

# base offset: the canvas floats above the surface; the snow is built on the real surface
lifted = [(p[0], p[1], p[2] + 0.4) for p in gp]
s_off = S.build_snow(lifted, gt, w, params, base_offset=0.4)
assert sorted(s_off["positions"]) == sorted(s_weld["positions"])
# the topology cache gives the same result, and is refreshed when the surface changes
cache = {}
a1 = S.build_snow(gp, gt, w, params, cache=cache)
a2 = S.build_snow(gp, gt, disc(gp, 40.0), params, cache=cache)
assert a1["positions"] == s_weld["positions"] and a2["positions"] == S.build_snow(gp, gt, disc(gp, 40.0), params)["positions"]
a3 = S.build_snow(lifted, gt, w, params, base_offset=0.4, cache=cache)
assert sorted(a3["positions"]) == sorted(s_weld["positions"])
# nothing painted / below the threshold
assert S.build_snow(gp, gt, [0.0] * len(gp))["triangles"] == []
assert S.build_snow(gp, gt, [0.01] * len(gp))["triangles"] == []
assert S.build_snow([], [], [])["triangles"] == []
print("SNOW CORE OK")
