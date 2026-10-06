"""Snow Painter on a scan-like mesh (bumpy plateau + cliff + overhang), through the mock ray casts: the canvas is
draped over the top surface (continuous, never buried), and the snow follows the real surface."""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
import unreal as U  # noqa: E402  (mock)


def height(x, y):
    """Plateau at ~300 cm for x < 400, a cliff, valley floor at ~0; bumps everywhere."""
    base = 300.0 if x < 400 else 0.0
    return base + 8.0 * math.sin(x / 23.0) * math.cos(y / 17.0) + 3.0 * math.sin((x + y) / 7.0)


# a triangulated heightfield (4 cm cells: denser than the canvas) + an overhang shelf below the plateau edge
N, CELL = 200, 4.0
pos, tris = [], []
for i in range(N + 1):
    for j in range(N // 4 + 1):
        x, y = i * CELL, j * CELL * 4
        pos.append((x, y, height(x, y)))
W = N // 4 + 1
for i in range(N):
    for j in range(N // 4):
        a, b, c, d = i * W + j, (i + 1) * W + j, (i + 1) * W + j + 1, i * W + j + 1
        if (pos[a][0] < 400) != (pos[b][0] < 400):
            continue                              # the cliff face itself (vertical) adds nothing seen from above
        tris += [(a, b, c), (a, c, d)]
base = len(pos)
pos += [(300, 0, 150), (420, 0, 150), (420, 200, 150), (300, 200, 150)]   # a shelf under the plateau (hidden)
tris += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
mesh = U.StaticMesh("SM_Cliff_Scan")
mesh.geo = (pos, tris)
cliff = U.StaticMeshActor("CliffScan", mesh, loc=U.Vector(0.0, 0.0, 0.0))
U.EditorActorSubsystem.actors = [cliff]
U.EditorActorSubsystem.selected = [cliff]

# ground truth: the triangulated surface itself (what the rays see), not the smooth formula
_dm = U.DynamicMesh()
_dm.positions, _dm.tris = pos, tris
_bvh = U.GeometryScriptDynamicMeshBVH(_dm)


def surf(x, y):
    hit, oc = U.GeometryScript_MeshSpatial.find_nearest_ray_intersection_with_mesh(
        _dm, _bvh, U.Vector(x, y, 1000.0), U.Vector(0, 0, -1), None)
    return hit.hit_position.z if oc == U.GeometryScriptSearchOutcomePins.FOUND else None


import snow_painter as S
S.CONFIG.update(canvas_detail=10.0, snow_detail=5.0)
S.start()
t = S._S["targets"][0]
canvas = t.canvas
csm = canvas.get_component_by_class(U.StaticMeshComponent).get_editor_property("static_mesh")
cpos = [(p[0] + canvas.loc.x, p[1] + canvas.loc.y, p[2] + canvas.loc.z) for p in csm.geo[0]]
print("canvas: %d points, %d tris, %d rays" % (len(cpos), len(csm.geo[1]), U.GeometryScript_MeshSpatial.rays))

# continuous over the plateau and the valley (no islands), above the real surface at its own points
for p in cpos:
    assert p[2] >= surf(p[0], p[1]) + S.CONFIG["canvas_offset"] - 1e-6, "canvas below the surface"
    assert p[2] - surf(p[0], p[1]) < 15.0, "canvas floating far above the surface"
assert not [p for p in cpos if 300 < p[0] < 400 and p[2] < 200], "the hidden shelf isn't part of the canvas"
plateau = {(round(p[0]), round(p[1])) for p in cpos if p[0] < 390}
assert len(plateau) >= 0.9 * (39 * 21), "the plateau top is covered without gaps (%d)" % len(plateau)
for tri in csm.geo[1]:
    zs = [csm.geo[0][v][2] for v in tri]
    assert max(zs) - min(zs) < 60, "no canvas face down the cliff"

# paint a band across the cliff edge, like a brush stroke
comp = canvas.get_component_by_class(U.StaticMeshComponent)
comp.instance_colors = [(1.0, 1.0, 1.0, 1.0) if 250 <= p[0] <= 550 and 40 <= p[1] <= 160 else (0.0, 0.0, 0.0, 1.0)
                        for p in cpos]
S.set_params(pile_up=1.0)       # vertical growth: thickness = height above the surface at the same XY
S.update()
dm = t.snow.get_editor_property("dynamic_mesh_component").get_dynamic_mesh()
loc = t.snow.loc
snow = [(p[0] + loc.x, p[1] + loc.y, p[2] + loc.z) for p in dm.positions]
assert dm.tris, "snow built"
thick = [p[2] - surf(p[0], p[1]) for p, c in zip(snow, dm.colors)
         if c[0] >= 0.5 and (260 < p[0] < 380 or 420 < p[0] < 540) and 60 < p[1] < 140]
assert thick and min(thick) > 3.0 and max(thick) <= S.CONFIG["depth"] * (1 + S.CONFIG["clumps"]) + 0.5, \
    (min(thick), max(thick))
for tri in dm.tris:
    zs = [dm.positions[v][2] for v in tri]
    assert max(zs) - min(zs) < 40, "no snow sheet hanging down the cliff"
lip = [p[2] - surf(p[0], p[1]) for p in snow if 390 <= p[0] < 400 and 60 < p[1] < 140]
assert lip and min(lip) < 2.0, "the snow thins out at the cliff lip"
print("snow: %d tris, thickness %.1f..%.1f cm over the real surface" % (len(dm.tris), min(thick), max(thick)))
S.cancel()
print("SNOW TERRAIN OK")
