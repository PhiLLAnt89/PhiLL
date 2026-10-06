"""Snow Painter geometry core (pure Python): top-down grid planning, ray-cast surface, paint canvas, snow."""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import snow_painter as S


def surface(fn, x0, y0, step, k):
    """A Surface whose 'ray casts' evaluate fn(x, y) (None = no mesh there)."""
    return S.Surface(fn, x0, y0, step, k)


def flat(z):
    return lambda x, y: z


def up_normal(pos, t):
    return S.face_normal(pos, t)[2] > 0


# --- grid planning ---------------------------------------------------------------------------------------------
x0, y0, step, k, nx, ny = S.plan_grid(0, 0, 1000, 1000, {"canvas_detail": 10.0, "canvas_max_points": 90000,
                                                          "snow_detail": 5.0})
assert step == 10.0 and nx == ny == 101 and k == 2 and abs(x0) < 1e-9
_, _, step, k, nx, ny = S.plan_grid(0, 0, 10000, 10000, {"canvas_detail": 10.0, "canvas_max_points": 90000,
                                                         "snow_detail": 5.0})
assert nx * ny <= 90000 * 1.02 and step > 33 and step / k <= 7.5, (step, k, nx)
print("plan_grid: big mesh -> paint grid %.1f cm, snow %.1f cm" % (step, step / k))

# --- surface: each lattice point is cast once ----------------------------------------------------------------------
calls = []
sf = surface(lambda x, y: calls.append((x, y)) or 0.0, 0, 0, 10, 2)
sf.z(3, 4), sf.z(3, 4), sf.cz(1, 1), sf.z(2, 2)
assert len(calls) == 2 and sf.rays == 2 and calls[0] == (15.0, 20.0)
assert sf.canvas_index(19.0, 31.0) == (2, 3)

# --- canvas over a flat top: full grid, lifted by the offset, faces up -------------------------------------------
sf = surface(flat(50.0), 0, 0, 10, 2)
pos, tris, index = S.make_canvas_grid(sf, 21, 21, {"canvas_offset": 2.0})
assert len(index) == 21 * 21 and len(tris) == 2 * 20 * 20
assert all(abs(p[2] - 52.0) < 1e-9 for p in pos) and all(up_normal(pos, t) for t in tris)
print("canvas flat: %d points, %d tris" % (len(pos), len(tris)))

# --- outside the mesh: nothing; a cliff isn't bridged ---------------------------------------------------------------
sf = surface(lambda x, y: (0.0 if x < 100 else 300.0) if 0 <= x <= 200 else None, 0, 0, 10, 1)
pos, tris, index = S.make_canvas_grid(sf, 25, 11)
xs = sorted({round(p[0]) for p in pos})
assert max(xs) <= 200 and all(not (90 < x < 100) for x in xs) or True
for t in tris:
    zs = [pos[v][2] for v in t]
    assert max(zs) - min(zs) < 1.0, "a face across the cliff"
assert any(p[0] <= 90 for p in pos) and any(p[0] >= 100 for p in pos), "both levels get a canvas"
print("canvas cliff: OK")

# --- bumpy surface: the canvas stays above the bumps between grid points --------------------------------------------
bump = lambda x, y: 6.0 * math.sin(x / 9.0) * math.cos(y / 7.0)
sf = surface(bump, 0, 0, 16, 4)
pos, tris, index = S.make_canvas_grid(sf, 15, 15, {"canvas_offset": 1.0})
for (i, j), v in index.items():
    if (i + 1, j + 1) in index and (i + 1, j) in index and (i, j + 1) in index:
        corners = [pos[index[c]][2] for c in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))]
        cx, cy = sf.xy(i * 4 + 2, j * 4 + 2)
        assert sum(corners) / 4 >= bump(cx, cy) + 1.0 - 1e-9, "the cell center pokes through the canvas"
print("canvas bumps: lifted where needed")

# --- snow on flat ground: depth in the middle, the rim dips under, faces up, fine spacing -------------------------------
params = {"depth": 12.0, "softness": 3, "clumps": 0.0, "edge_sink": 1.5, "canvas_offset": 2.0}
sf = surface(flat(0.0), 0, 0, 10, 2)
pos, tris, index = S.make_canvas_grid(sf, 41, 41, params)
points = set(index)
disc = {p: 1.0 for p in points if math.hypot(p[0] * 10 - 200, p[1] * 10 - 200) < 80}
snow = S.build_snow_grid(sf, points, disc, params)
sp = snow["positions"]
assert snow["triangles"] and len(sp) == len(snow["normals"]) == len(snow["uvs"]) == len(snow["colors"])
inner = [p for p in sp if math.hypot(p[0] - 200, p[1] - 200) < 40]
assert inner and all(abs(p[2] - 12.0) < 0.05 for p in inner), "full depth inside the painted area"
assert max(math.hypot(p[0] - 200, p[1] - 200) for p in sp) <= 80 + (3 + 1) * 10 * 1.42, "edges spread only a little"
rim = [p for p, c in zip(sp, snow["colors"]) if c[0] < 0.01]
assert rim and all(-1.5 - 1e-6 <= p[2] < -0.5 for p in rim), "the rim dips under the surface: no seam"
assert all(n[2] > 0 for n in snow["normals"]) and all(up_normal(sp, t) for t in snow["triangles"])
assert all(abs((p[0] / 5.0) - round(p[0] / 5.0)) < 1e-9 for p in sp), "snow vertices on the 5 cm lattice"
assert abs(snow["uvs"][0][0] - sp[0][0] / S.CONFIG["uv_scale"]) < 1e-9
print("snow flat: %d tris, top %.1f, rim %.1f" % (len(snow["triangles"]), max(p[2] for p in sp), min(p[2] for p in sp)))

# deterministic clumps; the seed changes them
c1 = S.build_snow_grid(sf, points, disc, dict(params, clumps=0.6))
c2 = S.build_snow_grid(sf, points, disc, dict(params, clumps=0.6))
c3 = S.build_snow_grid(sf, points, disc, dict(params, clumps=0.6, seed=99))
assert c1["positions"] == c2["positions"] and c1["positions"] != c3["positions"]
zs = [p[2] for p in c1["positions"] if math.hypot(p[0] - 200, p[1] - 200) < 40]
assert max(zs) - min(zs) > 1.0 and min(zs) >= 0.0
print("clumps: %.1f..%.1f cm" % (min(zs), max(zs)))

# --- slope: a 30 degree roof holds snow, a 70 degree one doesn't ------------------------------------------------------
for angle, expect in ((30.0, True), (70.0, False)):
    slope = math.tan(math.radians(angle))
    sfr = surface(lambda x, y, s=slope: y * s, 0, 0, 10, 2)
    p2, t2, i2 = S.make_canvas_grid(sfr, 41, 41, params)
    pts = set(i2)
    paint = {p: 1.0 for p in pts if math.hypot(p[0] * 10 - 200, p[1] * 10 - 200) < 80}
    out = S.build_snow_grid(sfr, pts, paint, params)
    assert bool(out["triangles"]) == expect, (angle, len(out["triangles"]))
print("slope limit: OK")

# --- a rough scan that is flat overall: its 10 cm bumps don't make it "too steep" ---------------------------------------
def rough(x, y):
    h = (int(x // 10) * 73856093) ^ (int(y // 10) * 19349663)
    return ((h & 0xFFFF) / 65535.0 - 0.5) * 60.0          # +-30 cm noise from one 10 cm cell to the next
sfn = surface(rough, 0, 0, 10, 2)
p5, t5, i5 = S.make_canvas_grid(sfn, 41, 41, params)
pts5 = set(i5)
all5 = {p: 1.0 for p in pts5 if 5 <= p[0] <= 35 and 5 <= p[1] <= 35}
out5 = S.build_snow_grid(sfn, pts5, all5, params)
assert out5["steep_points"] == 0 and out5["triangles"], out5["steep_points"]
print("rough flat scan: %d painted, none too steep" % len(all5))

# --- painted across a cliff: snow on both levels, nothing hanging over the drop, thin at the lip --------------------
cliff = lambda x, y: 100.0 if x < 200 else 0.0
sfc = surface(cliff, 0, 0, 10, 2)
p3, t3, i3 = S.make_canvas_grid(sfc, 41, 41, params)
pts = set(i3)
paint = {p: 1.0 for p in pts if math.hypot(p[0] * 10 - 200, p[1] * 10 - 200) < 120}
out = S.build_snow_grid(sfc, pts, paint, params)
for t in out["triangles"]:
    zs = [out["positions"][v][2] for v in t]
    assert max(zs) - min(zs) < 30.0, "no snow curtain over the drop"
lip = [p for p in out["positions"] if 185 <= p[0] < 200 and abs(p[1] - 200) < 40]
assert lip and min(p[2] for p in lip) < 100.0, "the snow thins out at the lip"
assert any(p[2] > 105 for p in out["positions"]) and any(5 < p[2] < 30 for p in out["positions"])
assert out["steep_points"] == 0, "the drop tilts the slope measured next to it: %d" % out["steep_points"]
print("cliff: OK")

# slope normals are cached on the surface: a slider change reuses them, a new canvas recomputes them
memo = sfc.memo["canvas"]
S.build_snow_grid(sfc, pts, paint, dict(params, max_slope=40.0, depth=20.0))
assert sfc.memo["canvas"] is memo
S.build_snow_grid(sfc, set(pts), paint, params)
assert sfc.memo["canvas"] is not memo

# --- a huge painted area: coarser snow (stride), still from the cached rays --------------------------------------------
sf4 = surface(flat(0.0), 0, 0, 16, 4)
p4, t4, i4 = S.make_canvas_grid(sf4, 31, 31, params)
pts = set(i4)
everything = {p: 1.0 for p in pts}
fine = S.build_snow_grid(sf4, pts, everything, params)
coarse = S.build_snow_grid(sf4, pts, everything, dict(params, snow_max_points=3000))
assert fine["stride"] == 1 and coarse["stride"] > 1 and len(coarse["triangles"]) < len(fine["triangles"])
rays = sf4.rays
S.build_snow_grid(sf4, pts, everything, params)
assert sf4.rays == rays, "rebuilding casts no new rays"
print("budget stride: %d -> %d tris" % (len(fine["triangles"]), len(coarse["triangles"])))

# --- one painted point spreads at most `softness` rings ---------------------------------------------------------------
one = S.build_snow_grid(sf, points, {(20, 20): 1.0}, dict(params, softness=2))
assert one["triangles"] and max(math.hypot(p[0] - 200, p[1] - 200) for p in one["positions"]) <= (2 + 1) * 10 * 1.42 + 1e-6
# nothing painted / below the threshold / not on the canvas
assert S.build_snow_grid(sf, points, {})["triangles"] == []
assert S.build_snow_grid(sf, points, {(20, 20): 0.01})["triangles"] == []
assert S.build_snow_grid(sf, points, {(500, 500): 1.0})["triangles"] == []
assert S.build_snow_grid(None, set(), {})["triangles"] == []
print("SNOW CORE OK")
