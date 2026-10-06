"""Snow Painter end to end against the mock engine: canvas, simulated Mesh Paint strokes, live rebuild, sliders,
clear, resume, bake, cancel, and the panel."""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)
import unreal as U  # noqa: E402  (mock)


def plane_mesh(name, size, z, extra_wall=True):
    """A flat top (holds snow) + a vertical wall + an underside (both can't)."""
    p = [(-size / 2, -size / 2, z), (size / 2, -size / 2, z), (size / 2, size / 2, z), (-size / 2, size / 2, z)]
    t = [(0, 1, 2), (0, 2, 3)]
    if extra_wall:
        b = len(p)
        p += [(-size / 2, -size / 2, 0), (size / 2, -size / 2, 0), (size / 2, -size / 2, z), (-size / 2, -size / 2, z)]
        t += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
        b = len(p)
        p += [(-size / 2, -size / 2, 0), (-size / 2, size / 2, 0), (size / 2, size / 2, 0), (size / 2, -size / 2, 0)]
        t += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
    m = U.StaticMesh(name)
    m.geo = (p, t)
    return m


rock = U.StaticMeshActor("Rock", plane_mesh("SM_Rock", 300.0, 50.0), loc=U.Vector(1000.0, 0.0, 0.0))
wall_mesh = U.StaticMesh("SM_Wall")
wall_mesh.geo = ([(0, 0, 0), (100, 0, 0), (100, 0, 100), (0, 0, 100)], [(0, 1, 2), (0, 2, 3)])
wall = U.StaticMeshActor("Wall", wall_mesh)
light = U.Actor("JustALight")
U.EditorActorSubsystem.actors = [rock, wall, light]

import snow_painter as S
import clock; clock.install(S)
from PySide6 import QtWidgets
S.CONFIG["canvas_detail"] = 10.0
win = S.show()
QtWidgets.QApplication.processEvents()
sub = U.get_editor_subsystem(U.EditorActorSubsystem)


def actors_tagged(tag):
    return [a for a in U.EditorActorSubsystem.actors if tag in [str(t) for t in a.get_editor_property("tags")]]


def paint(canvas, cx, cy, r, value=1.0, keep=True):
    """What a Mesh Paint stroke does: per-instance vertex colors on the canvas component."""
    comp = canvas.get_component_by_class(U.StaticMeshComponent)
    sm = comp.get_editor_property("static_mesh")
    pos = sm.geo[0]
    cols = list(comp.instance_colors) if (keep and comp.instance_colors) else list(sm.colors)
    o = canvas.loc
    for i, p in enumerate(pos):
        if math.hypot(p[0] + o.x - cx, p[1] + o.y - cy) < r:
            cols[i] = (value, value, value, 1.0)
    comp.instance_colors = cols


def ue_front_up(positions, tris):
    """Unreal's outward normal of a triangle (a, b, c) is (c - a) x (b - a): seen from above it must point up."""
    for a, b, c in tris:
        pa, pb, pc = positions[a], positions[b], positions[c]
        e1 = (pc[0] - pa[0], pc[1] - pa[1])
        e2 = (pb[0] - pa[0], pb[1] - pa[1])
        if e1[0] * e2[1] - e1[1] * e2[0] <= 0:
            return False
    return True


def snow_tris(actor):
    return len(actor.get_editor_property("dynamic_mesh_component").get_dynamic_mesh().tris)


# --- nothing selected / not a mesh --------------------------------------------------------------------------
U.EditorActorSubsystem.selected = [light]
win.on_start()
assert "Select one or more Static Mesh actors" in win.lbl_status.text() and not S.active()
U.EditorActorSubsystem.selected = [wall]
win.on_start()
assert not S.active() and "No paint canvas" in win.lbl_status.text(), win.lbl_status.text()
assert not actors_tagged(S.TAG_CANVAS) and not [o for o in U._ALL if isinstance(o, U.StaticMesh) and
                                                  "SnowCanvas" in o.get_name()], "a failed canvas leaves nothing behind"
print("guards: OK")

# --- start: canvas over the top only, live snow actor, canvas selected ----------------------------------------
U.EditorActorSubsystem.selected = [rock]
win.on_start()
assert S.active() and "Mesh Paint" in win.lbl_status.text(), win.lbl_status.text()
canvas = actors_tagged(S.TAG_CANVAS)[0]
snow = actors_tagged(S.TAG_SNOW)[0]
assert canvas.get_actor_label() == "SnowCanvas_Rock" and snow.get_actor_label() == "Snow_Rock"
assert S.TAG_TARGET + rock.get_path_name() in [str(t) for t in canvas.get_editor_property("tags")]
assert canvas.folder == "SnowPainter" and canvas.hidden_in_game
assert U.EditorActorSubsystem.selected == [canvas], "the canvas is selected so Mesh Paint paints it"
csm = canvas.get_component_by_class(U.StaticMeshComponent).get_editor_property("static_mesh")
assert csm.get_path_name().startswith("/Game/SnowPainter/Canvas/SM_SnowCanvas_Rock")
assert csm.materials[0].get_name() == "M_SnowPainter_Canvas3" and csm.materials[0].blend_mode == U.BlendMode.BLEND_TRANSLUCENT
assert all(c == (0.0, 0.0, 0.0, 1.0) for c in csm.colors), "the canvas starts unpainted (black)"
world_z = {round(p[2] + canvas.loc.z, 3) for p in csm.geo[0]}
assert world_z == {50.0 + S.CONFIG["canvas_offset"]}, "only the top, floating just above it"
assert max(math.dist(csm.geo[0][a], csm.geo[0][b]) for t in csm.geo[1] for a, b in ((t[0], t[1]), (t[1], t[2]))) <= 10.0 * 1.4143
xs = sorted({round(p[0] + canvas.loc.x, 4) for p in csm.geo[0]})
assert all(abs((b - a) - 10.0) < 1e-6 for a, b in zip(xs, xs[1:])), "a regular 10 cm paint grid"
assert min(xs) >= 1000 - 150 - 1e-6 and max(xs) <= 1000 + 150 + 1e-6, "draped over the rock, not elsewhere"
assert canvas.get_component_by_class(U.StaticMeshComponent).override_materials[0].get_name() == "M_SnowPainter_Canvas3"
assert any(str(t).startswith(S.TAG_GRID) for t in canvas.get_editor_property("tags"))
assert snow_tris(snow) == 0
assert "Painting:" in win.lbl_targets.text() and win.btn_start.text() == "Add selected meshes" and win.btn_bake.isEnabled()
print("start: canvas %d tris" % len(csm.geo[1]))

# --- a stroke: no rebuild while painting, rebuild once it stops ------------------------------------------------
paint(canvas, 1000.0, 0.0, 60.0)
clock.run_ticks(U, n=1, step=0.6)
assert snow_tris(snow) == 0, "still painting: wait for the stroke to end"
paint(canvas, 1030.0, 0.0, 60.0)
clock.run_ticks(U, n=1, step=0.6)
assert snow_tris(snow) == 0
clock.run_ticks(U, n=2, step=0.6)
n1 = snow_tris(snow)
assert n1 > 0 and "snow rebuilt" in win.lbl_status.text(), win.lbl_status.text()
mesh = snow.get_editor_property("dynamic_mesh_component").get_dynamic_mesh()
top = max(p[2] for p in mesh.positions) + snow.loc.z
assert ue_front_up(mesh.positions, mesh.tris), "snow front faces must face up in Unreal's winding"
assert ue_front_up(csm.geo[0], csm.geo[1]), "canvas front faces must face up in Unreal's winding"
assert 50.0 + 5.0 < top <= 50.0 + S.CONFIG["depth"] * (1 + S.CONFIG["clumps"]) + 1e-6, top
assert mesh.normals and mesh.uvs and mesh.colors
assert snow.get_editor_property("dynamic_mesh_component").override_materials[0].get_name() == "M_SnowPainter_Snow2"
copies = len(U.GeometryScript_SceneUtils.copies)
clock.run_ticks(U, n=4, step=0.6)
assert snow_tris(snow) == n1 and len(U.GeometryScript_SceneUtils.copies) > copies, "idle: polled, not rebuilt"
print("stroke -> snow: %d tris, top %.1f" % (n1, top))

# --- sliders rebuild from the paint already read ------------------------------------------------------------
copies = len(U.GeometryScript_SceneUtils.copies)
win._slider("depth", 30.0)
win._apply_params()
top2 = max(p[2] for p in mesh.positions) + snow.loc.z
assert top2 > top + 10 and len(U.GeometryScript_SceneUtils.copies) == copies, "no re-read for a slider"
win._slider("max_slope", 10.0)
win._apply_params()
assert snow_tris(snow) > 0, "a flat top holds snow even at 10 degrees"
assert "slope_scale" in win._sliders
win._slider("slope_scale", 60.0)
win._apply_params()
assert S.CONFIG["slope_scale"] == 60.0 and snow_tris(snow) > 0
S.set_params(max_slope=55.0, depth=12.0, slope_scale=30.0)
U.EditorUtilityLibrary.selected_assets = [U.Material("M_MySnow", path="/Game/FX/M_MySnow")]
win.on_use_material()
win._apply_params()
assert win.txt_mat.text() == "/Game/FX/M_MySnow"
assert snow.get_editor_property("dynamic_mesh_component").override_materials[0].get_name() == "M_MySnow"
print("sliders + material: OK")

# --- erase all -> snow gone; live update off -> nothing happens ----------------------------------------------------
paint(canvas, 1000.0, 0.0, 500.0, value=0.0)
clock.run_ticks(U, n=4, step=0.6)
assert snow_tris(snow) == 0
win.chk_live.setChecked(False)
paint(canvas, 1000.0, 0.0, 60.0)
clock.run_ticks(U, n=4, step=0.6)
assert snow_tris(snow) == 0, "live update off"
win.on_update()
assert snow_tris(snow) > 0, "Update now still works"
assert "canvas points painted" in win.lbl_status.text() and "brightest red 1.00" in win.lbl_status.text(), \
    win.lbl_status.text()
assert "-> snow:" in win.lbl_status.text() and "Snow_Rock" in win.lbl_status.text(), win.lbl_status.text()
real_write = S.write_mesh
S.write_mesh = lambda *a, **k: (_ for _ in ()).throw(AttributeError("no such method"))
win.on_update()
assert "ERROR AttributeError: no such method" in win.lbl_status.text(), win.lbl_status.text()
S.write_mesh = real_write
win.chk_live.setChecked(True)
print("erase / live off / update now: OK")

# --- a failing read pauses live update once instead of logging every poll ----------------------------------------
real = U.GeometryScript_VertexColors.get_mesh_per_vertex_colors
U.GeometryScript_VertexColors.get_mesh_per_vertex_colors = staticmethod(lambda m, b=True: (_ for _ in ()).throw(RuntimeError("boom")))
n_warn = len([x for x in U._LOG if x[0] == "warn"])
clock.run_ticks(U, n=6, step=0.6)
assert not S._S["live"] and not win.chk_live.isChecked() and "Live update paused" in win.lbl_status.text()
assert len([x for x in U._LOG if x[0] == "warn"]) - n_warn == 1, "one warning, not one per poll"
U.GeometryScript_VertexColors.get_mesh_per_vertex_colors = real
win.on_update()
assert S._S["live"] and win.chk_live.isChecked(), "Update now retries and resumes live updates"
print("read errors pause live update: OK")

# --- clear paint: a fresh canvas, the old one is removed --------------------------------------------------------
old_canvas, old_asset = canvas, csm
win.on_clear()
canvas = actors_tagged(S.TAG_CANVAS)[0]
assert canvas is not old_canvas and old_canvas.destroyed and old_asset not in U._ALL, "old canvas + asset removed"
assert snow_tris(snow) == 0 and U.EditorActorSubsystem.selected == [canvas]
print("clear paint: OK")

# --- resume after reopening the tool -----------------------------------------------------------------------------
paint(canvas, 1000.0, 0.0, 80.0)
win.close()
S._S["targets"] = []                       # a new Python session / editor restart
S._stop_tick()
win = S.show(reuse=False)
assert S.active() and "Resumed" in win.lbl_status.text() and snow_tris(snow) > 0
assert len(actors_tagged(S.TAG_SNOW)) == 1, "the existing snow actor is reused"
assert "older version" not in win.lbl_status.text()
# a canvas made by 1.1.x (old winding): resumed, with a hint to rebuild it
c0 = actors_tagged(S.TAG_CANVAS)[0]
c0.set_editor_property("tags", [t for t in c0.get_editor_property("tags") if str(t) != S.TAG_WINDING])
win.close()
S._S["targets"] = []
S._stop_tick()
win = S.show(reuse=False)
assert S.active() and "older version" in win.lbl_status.text() and "Clear paint" in win.lbl_status.text()
print("resume: OK")

# --- a canvas deleted by hand: dropped cleanly --------------------------------------------------------------------
QtWidgets.QApplication.processEvents()
win.resize(470, 900)
QtWidgets.QApplication.processEvents()
win.grab().save(os.path.join(OUT, "ui_snow.png"))

# --- add another mesh to the running session ------------------------------------------------------------------------
assert win.btn_start.text() == "Add selected meshes" and win.btn_start.isEnabled()
rock2 = U.StaticMeshActor("Rock2", plane_mesh("SM_Rock2", 200.0, 20.0), loc=U.Vector(-800.0, 0.0, 0.0))
U.EditorActorSubsystem.actors.append(rock2)
U.EditorActorSubsystem.selected = [rock2, rock]          # rock is already being painted: skipped
win.on_start()
assert len(S._S["targets"]) == 2 and [t.label for t in S._S["targets"]] == ["Rock", "Rock2"]
assert len(actors_tagged(S.TAG_CANVAS)) == 2 and set(U.EditorActorSubsystem.selected) == set(actors_tagged(S.TAG_CANVAS))
U.EditorActorSubsystem.selected = [rock]
win.on_start()
assert "not already being painted" in win.lbl_status.text() and len(S._S["targets"]) == 2
print("add meshes: OK")

# --- bake: static mesh (Nanite), actor, canvas + live snow removed -----------------------------------------------
win.chk_nanite.setChecked(True)
win.on_bake()
assert not S.active() and win.btn_start.isEnabled() and not win.btn_bake.isEnabled()
baked = [a for a in U.EditorActorSubsystem.actors if a.get_actor_label() == "Snow_Rock" and isinstance(a, U.StaticMeshActor)]
assert len(baked) == 1, [a.get_actor_label() for a in U.EditorActorSubsystem.actors]
assert ue_front_up(*baked[0].get_component_by_class(U.StaticMeshComponent).get_editor_property("static_mesh").geo)
bsm = baked[0].get_component_by_class(U.StaticMeshComponent).get_editor_property("static_mesh")
assert bsm.get_path_name().startswith("/Game/SnowPainter/Baked/SM_Snow_Rock")
assert bsm.get_editor_property("nanite_settings").enabled and bsm.collision
assert bsm.materials[0].get_name() == "M_MySnow" and len(bsm.geo[1]) > 0
assert not actors_tagged(S.TAG_CANVAS) and not actors_tagged(S.TAG_SNOW)
assert not [o for o in U._ALL if isinstance(o, U.StaticMesh) and "SnowCanvas" in o.get_name()], "canvas assets deleted"
assert set(U.EditorActorSubsystem.selected) == set(baked)
assert "Baked 1" in win.lbl_status.text()
print("bake: %d tris -> %s" % (len(bsm.geo[1]), bsm.get_path_name()))

# --- cancel; a hand-deleted canvas; a dense source gets simplified first ------------------------------------------
U.EditorActorSubsystem.selected = [rock]
win.on_start()
canvas = actors_tagged(S.TAG_CANVAS)[0]
sub.destroy_actor(canvas)
clock.run_ticks(U, n=2, step=0.6)
assert not S.active() and "dropped" in win.lbl_status.text() and not actors_tagged(S.TAG_SNOW)
kept = [a for a in U.EditorActorSubsystem.actors if isinstance(a, U.DynamicMeshActor)]
assert len(kept) == 1 and not kept[0].destroyed, "the live snow is kept (untagged), nothing is lost"
sub.destroy_actor(kept[0])
S.CONFIG["surface_max_tris"] = 4
U.EditorActorSubsystem.selected = [rock]
win.on_start()
assert U.GeometryScript_MeshSimplification.calls == [4]
win.on_cancel()
assert not S.active() and not actors_tagged(S.TAG_CANVAS) and not actors_tagged(S.TAG_SNOW)
assert "cancelled" in win.lbl_status.text()
print("cancel / deleted canvas / simplify: OK")

# --- regression: Unreal asserts (editor crash) when a Static Mesh is built without UVs --------------------------------
U.EditorActorSubsystem.selected = [rock]
S.CONFIG["surface_max_tris"] = 3000000
win.on_start()
c = actors_tagged(S.TAG_CANVAS)[0].get_component_by_class(U.StaticMeshComponent).get_editor_property("static_mesh")
assert c.geo and S.CONFIG  # canvas built
win.on_cancel()
bare = U.DynamicMesh()
bare.positions, bare.tris = [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)]
real_uvs = U.GeometryScript_UVs.set_num_uv_sets
U.GeometryScript_UVs.set_num_uv_sets = staticmethod(lambda m, n: m)      # can't add one either
try:
    S._new_static_mesh(bare, "Canvas", "SM_NoUVs")
    raise AssertionError("must refuse")
except RuntimeError as e:
    assert "no UV set" in str(e)
U.GeometryScript_UVs.set_num_uv_sets = real_uvs
fixed = S._new_static_mesh(bare, "Canvas", "SM_NoUVs")                  # adds a UV set instead of crashing
assert fixed is not None
dm = S.write_mesh(U.DynamicMesh(), {"positions": bare.positions, "triangles": bare.tris})
assert len(dm.uvs) == 3, "write_mesh always writes UVs"
print("no-UV crash guard: OK")
print("SNOW SESSION OK")
