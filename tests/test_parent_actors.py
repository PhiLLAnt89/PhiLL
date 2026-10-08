"""Parent Actors against the mock engine: the panel (parent slot, children list, attach, detach, quick attach),
the engine's refusals (static under movable, loops, no root, other level), undo transactions, and paste mode."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)
import unreal as U  # noqa: E402  (mock)

M = U.ComponentMobility


def mesh_actor(name, x, mobility=M.STATIC, sockets=()):
    a = U.StaticMeshActor(name, U.StaticMesh("SM_" + name), loc=U.Vector(x, 0.0, 0.0))
    a.comps[0].set_editor_property("mobility", mobility)
    a.comps[0].sockets = tuple(sockets)
    return a


table = mesh_actor("Table", 0.0, sockets=("Top", "Drawer"))
cup = mesh_actor("Cup", 100.0)
plate = mesh_actor("Plate", 200.0)
cart = mesh_actor("Cart", 300.0, M.MOVABLE)
lamp = U.Actor("Lamp", loc=U.Vector(400.0, 0.0, 0.0))
lamp.add(U.SceneComponent("Root"))                    # movable scene root
empty = U.Actor("NoRoot")
U.EditorActorSubsystem.actors = [table, cup, plate, cart, lamp, empty]
sub = U.get_editor_subsystem(U.EditorActorSubsystem)

import parent_actors as P
from PySide6 import QtWidgets
win = P.show()
QtWidgets.QApplication.processEvents()


def select(*actors):
    sub.set_selected_level_actors(list(actors))


def reset():
    for a in U.EditorActorSubsystem.actors:
        a._attach = None
    P.STATE["parent"], P.STATE["children"] = None, []
    win.refresh()


# --- nothing set yet: buttons that need a parent / children are off ---------------------------------------------
assert not win.btn_attach.isEnabled() and not win.btn_select_parent.isEnabled() and not win.btn_remove.isEnabled()
select()
win.on_set_parent()
assert P.STATE["parent"] is None and "Select the parent" in win.lbl_status.text()

# --- 1 parent, 2 children, attach: they keep their place, one undo step -----------------------------------------
select(table)
win.on_set_parent()
assert P.STATE["parent"] is table and "Table" in win.lbl_parent.text() and "Static" in win.lbl_parent.text()
assert [win.cmb_socket.itemText(i) for i in range(win.cmb_socket.count())] == [P._NO_SOCKET, "Top", "Drawer"]
select(cup, plate, table)
win.on_add()
assert P.STATE["children"] == [cup, plate] and win.list.count() == 2, "the parent is never a child"
assert "1 skipped" in win.lbl_status.text()
win.on_add()                                                     # again: no duplicates
assert win.list.count() == 2
assert win.btn_attach.isEnabled()
U.ScopedEditorTransaction.titles[:] = []
win.on_attach()
assert cup.get_attach_parent_actor() is table and plate.get_attach_parent_actor() is table
assert cup.loc.x == 100.0 and plate.loc.x == 200.0, "Keep where they are"
assert U.ScopedEditorTransaction.titles == ["Attach 2 actors to Table"], U.ScopedEditorTransaction.titles
assert cup.modified and table.modified, "modify() before the change: Ctrl+Z works"
assert win.lbl_status.text() == "2 attached.", win.lbl_status.text()
assert "under Table" in win.list.item(0).text()
win.on_attach()                                                  # already there
assert win.lbl_status.text() == "0 attached, 2 skipped.", win.lbl_status.text()
print("attach: OK")

# --- socket + snap -------------------------------------------------------------------------------------------------
win.cmb_socket.setCurrentIndex(win.cmb_socket.findText("Top"))
win.cmb_mode.setCurrentIndex(1)
win.on_attach()
assert cup._attach == (table, "Top") and cup.loc.x == 0.0 and plate.loc.x == 0.0, "snapped onto the socket"
assert win.lbl_status.text() == "2 attached.", "a socket change re-attaches"
win.cmb_mode.setCurrentIndex(0)
win.cmb_socket.setCurrentIndex(0)
cup.loc.x, plate.loc.x = 100.0, 200.0
print("socket + snap: OK")

# --- detach: from whatever they're under, they stay put -------------------------------------------------------------
win.on_detach()
assert cup.get_attach_parent_actor() is None and plate.get_attach_parent_actor() is None
assert win.lbl_status.text() == "2 detached." and U.ScopedEditorTransaction.titles[-1] == "Detach 2 actors"
win.on_detach()
assert win.lbl_status.text() == "0 detached, 2 skipped."
print("detach: OK")

# --- static under movable: Unreal refuses; Match mobility makes the child movable ------------------------------------
reset()
P.set_parent(cart)
P.add_children([cup])
win.refresh()
win.chk_mobility.setChecked(False)
win.on_attach()
assert cup.get_attach_parent_actor() is None and "Match mobility" in win.lbl_status.text(), win.lbl_status.text()
win.chk_mobility.setChecked(True)
win.on_attach()
assert cup.get_attach_parent_actor() is cart and cup.comps[0].get_editor_property("mobility") == M.MOVABLE
assert "1 attached" in win.lbl_status.text()
print("mobility: OK")

# --- loops, no root, deleted, other level ----------------------------------------------------------------------------
P.set_parent(cup)                      # cup is under cart: cart can't go under cup
P.STATE["children"] = [cart, empty]
win.refresh()
win.on_attach()
assert cart.get_attach_parent_actor() is None
res = P.attach([cart, empty], cup)
msgs = dict((r[0].get_actor_label(), r[2]) for r in res)
assert "loop" in msgs["Cart"] and "root component" in msgs["NoRoot"], msgs
reset()
lvl, main = U._Level("PersistentLevel"), U._Level("PersistentLevel")
lvl._path, main._path = "/Game/Maps/Cave", "/Game/Maps/Main"
plate._outer, table._outer, cup._outer = lvl, main, main
res = P.attach([plate, cup], table)
assert res[0][1] == "error" and "different level" in res[0][2] and "(Cave vs Main)" in res[0][2], res
assert res[1][1] == "attached", "same level: fine"
plate._outer = table._outer = cup._outer = None
cup._attach = None
plate.destroyed = True
P.set_parent(table)
P.add_children([plate, cup])
win.refresh()
assert win.list.item(0).text().startswith("(missing")
win.on_attach()
assert cup.get_attach_parent_actor() is table and "1 not: (missing) - it no longer exists" in win.lbl_status.text(), \
    win.lbl_status.text()
plate.destroyed = False

# what the Outliner refuses but the attach call alone wouldn't: BSP brushes, landscape, Child Actor Component actors
reset()
bsp = U.Brush("BSP_Box")
bsp.add(U.SceneComponent("BrushComponent0", mobility=M.STATIC))
vol = U.Volume("BlockingVolume")
vol.add(U.SceneComponent("BrushComponent0", mobility=M.STATIC))
land = U.LandscapeProxy("Landscape")
land.add(U.SceneComponent("RootComponent", mobility=M.STATIC))
spawned = mesh_actor("BP_Door_Child", 50.0)
spawned._cac = cart
spawned._attach = (cart, "")
U.EditorActorSubsystem.actors += [bsp, vol, land, spawned]
res = dict((r[0].get_actor_label(), r) for r in P.attach([bsp, vol, land, spawned], table))
assert res["BSP_Box"][1] == "error" and "BSP brush" in res["BSP_Box"][2]
assert res["BlockingVolume"][1] == "attached", "volumes are brushes the Outliner does attach"
assert res["Landscape"][1] == "error" and "landscape" in res["Landscape"][2]
assert res["BP_Door_Child"][1] == "error" and "Child Actor Component of Cart" in res["BP_Door_Child"][2]
assert "BSP brush" in P.attach([cup], bsp)[0][2], "a BSP brush can't be the parent either"
r = P.detach([spawned])[0]
assert r[1] == "error" and spawned.get_attach_parent_actor() is cart, "detaching it would be undone by Unreal"
for a in (bsp, vol, land, spawned):
    U.EditorActorSubsystem.actors.remove(a)
print("refusals: OK")

# --- Match mobility covers what's attached under the child, for undo, and is rolled back if the attach fails ------
reset()
for a in (table, cup, plate):
    a.comps[0].set_editor_property("mobility", M.STATIC)
assert P.attach([cup, plate], table)[0][1] == "attached"           # cup and plate sit on the table (all Static)
for a in (table, cup, plate):
    a.modified = 0
    a.comps[0].modified = 0
res = P.attach([table], cart)
assert res[0][1] == "attached" and "with 2 components attached under it" in res[0][2], res
assert all(a.comps[0].get_editor_property("mobility") == M.MOVABLE for a in (table, cup, plate))
assert cup.comps[0].modified and plate.comps[0].modified and cup.modified, "recorded: one Ctrl+Z puts them back"
table._attach = None
lamp.comps[0].set_editor_property("mobility", M.STATIONARY)       # Unreal doesn't spread Stationary by itself
for a in (table, cup, plate):
    a.comps[0].set_editor_property("mobility", M.STATIC)
P.attach([table], lamp)
assert all(a.comps[0].get_editor_property("mobility") == M.STATIONARY for a in (table, cup, plate))
lamp.comps[0].set_editor_property("mobility", M.MOVABLE)
table._attach = None
for a in (table, cup, plate):
    a.comps[0].set_editor_property("mobility", M.STATIC)
real_attach = U.Actor.attach_to_actor
U.Actor.attach_to_actor = lambda self, *a: False                   # Unreal refuses after all
res = P.attach([table], cart)
U.Actor.attach_to_actor = real_attach
assert res[0][1] == "error" and all(a.comps[0].get_editor_property("mobility") == M.STATIC for a in (table, cup, plate))
print("mobility under the child: OK")

# --- Snap on children that are already attached: they snap now (Unreal ignores a same-place attach) ---------------
reset()
cup.loc.x = 100.0
P.attach([cup], table)
assert cup.loc.x == 100.0
r = P.attach([cup], table, keep_world=False)[0]
assert r[1] == "attached" and r[2].startswith("snapped onto Table") and cup.loc.x == 0.0 and cup._attach == (table, "")
assert P.attach([cup], table, keep_world=True)[0][1] == "skip"
cup.loc.x = 100.0
# already attached, but now Static under a Stationary parent: Match mobility still applies, and it stays attached
table.comps[0].set_editor_property("mobility", M.STATIONARY)
cup.comps[0].set_editor_property("mobility", M.STATIC)
r = P.attach([cup], table, keep_world=False, match_mobility=False)[0]
assert r[1] == "error" and "Match mobility" in r[2] and cup.get_attach_parent_actor() is table and cup.loc.x == 100.0
r = P.attach([cup], table, keep_world=False, match_mobility=True)[0]
assert r[1] == "attached" and cup.comps[0].get_editor_property("mobility") == M.STATIONARY and cup.loc.x == 0.0
table.comps[0].set_editor_property("mobility", M.STATIC)
cup.comps[0].set_editor_property("mobility", M.STATIC)
# without the relative-transform call: detach + attach; if Unreal refuses, the child goes back where it was
cup.loc.x = 100.0
saved_call = U.ActorComponent.set_relative_location_and_rotation
del U.ActorComponent.set_relative_location_and_rotation
r = P.attach([cup], table, keep_world=False)[0]
assert r[1] == "attached" and cup.loc.x == 0.0 and cup.get_attach_parent_actor() is table
cup.loc.x = 100.0
real_attach = U.Actor.attach_to_actor
U.Actor.attach_to_actor = lambda self, p, s, lr, *a: False if lr == U.AttachmentRule.SNAP_TO_TARGET else \
    real_attach(self, p, s, lr, *a)
r = P.attach([cup], table, keep_world=False)[0]
U.Actor.attach_to_actor = real_attach
U.ActorComponent.set_relative_location_and_rotation = saved_call
assert r[1] == "error" and cup.get_attach_parent_actor() is table and cup.loc.x == 100.0, "left where it was"
print("re-snap: OK")

# --- a camera-like parent: Unreal attaches to its CameraComponent, not the root (Python can't see which) ----------
reset()
cam = U.CameraActor("CineCam", loc=U.Vector(500.0, 0.0, 0.0))
cam.add(U.SceneComponent("SceneComponent", mobility=M.MOVABLE))
cam.add(U.SceneComponent("CameraComponent", mobility=M.MOVABLE))
U.EditorActorSubsystem.actors.append(cam)
assert P.attach([plate], cam)[0][1] == "attached" and plate.get_attach_parent_actor() is cam
assert P.attach([plate], cam)[0][2] == "already attached to it"
r = P.attach([plate], cam, keep_world=False)[0]
assert r[2].startswith("snapped onto CineCam") and plate.loc.x == 500.0
U.EditorActorSubsystem.actors.remove(cam)
plate.loc.x = 200.0
plate.comps[0].set_editor_property("mobility", M.STATIC)
print("camera parent: OK")

# --- only what really changes is marked as changed (One File Per Actor: no needless re-saves of the parents) ------
reset()
cup._attach = (cart, "")
cup.comps[0].set_editor_property("mobility", M.MOVABLE)
for a in (table, cart, cup):
    a.dirtied = 0
    a.comps[0].dirtied = 0
P.attach([cup], table)
assert cup.get_attach_parent_actor() is table and cup.dirtied and cup.comps[0].dirtied
assert table.dirtied == table.comps[0].dirtied == cart.dirtied == 0, "the new and old parents aren't re-saved"
cup.comps[0].set_editor_property("mobility", M.STATIC)
print("dirty packages: OK")

# --- remove / clear / select ----------------------------------------------------------------------------------------
reset()
P.set_parent(table)
P.add_children([cup, plate, lamp])
win.refresh()
win.list.item(1).setSelected(True)
win.on_remove()
assert P.STATE["children"] == [cup, lamp]
win.on_select_children()
assert sub.get_selected_level_actors() == [cup, lamp]
win.on_row_double_clicked(win.list.item(1))
assert sub.get_selected_level_actors() == [lamp]
win.on_select_parent()
assert sub.get_selected_level_actors() == [table]
win.on_clear_children()
assert P.STATE["children"] == [] and not win.btn_attach.isEnabled()
win.on_clear_parent()
assert P.STATE["parent"] is None
P.add_children([cup, plate, lamp])                     # the highlight follows the actor, not the row number
win.refresh()
win.list.item(1).setSelected(True)
P.set_parent(cup)                                       # cup leaves the list: plate is now row 0
win.refresh()
assert [i.row() for i in win.list.selectedIndexes()] == [0] and P.STATE["children"] == [plate, lamp]
win.on_remove()
assert P.STATE["children"] == [lamp] and not win.list.selectedIndexes()
print("list: OK")

# --- quick: two selected, the first goes under the second (a movable parent: the static cup is matched) --------------
reset()
select(cup, lamp)
win.on_quick()
assert cup.get_attach_parent_actor() is lamp and win.lbl_status.text().startswith("Under Lamp: 1 attached")
select(plate, cup, table)                      # several: all under the last selected
win.on_quick()
assert plate.get_attach_parent_actor() is table and cup.get_attach_parent_actor() is table
select(plate, cup)
win.on_quick_detach()
assert plate.get_attach_parent_actor() is None and cup.get_attach_parent_actor() is None
select(cup)
win.on_quick()
assert "at least 2" in win.lbl_status.text()
print("quick: OK")

# --- text mode --------------------------------------------------------------------------------------------------------
reset()
select(cup)
assert P.attach_selected() == []
select(plate, cup, table)
res = P.attach_selected(keep_world=False)
assert [r[1] for r in res] == ["attached", "attached"] and plate.loc.x == 0.0
select(plate)
assert P.detach_selected()[0][1] == "detached"
print("text mode: OK")

# --- screenshot of the panel --------------------------------------------------------------------------------------
reset()
P.set_parent(table)
P.add_children([cup, plate, lamp])
P.attach([cup], table)
win.refresh()
win.status("1 attached.")
QtWidgets.QApplication.processEvents()
win.grab().save(os.path.join(OUT, "parent_actors.png"))

# --- closed and reopened: the Qt tick runs again (Linux/macOS need it) ------------------------------------------------
win.close()
assert P._TICK["handle"] is None
again = P.show()
assert again is win and P._TICK["handle"] is not None and win.isVisible()


# --- pasted into the Output Log: becomes the module "parent_actors", keeps the panel's state; the console's shared
# namespace (other pasted tools live there too) is left as it was ---------------------------------------------------
def live_ticks():
    return sum(1 for t in U.TICKS if t is not None)


src = open(os.path.join(os.path.dirname(HERE), "parent_actors" + ".py"), encoding="utf-8").read()
def other_tools_check(key, category, name): return "theirs"
console = {"__name__": "__main__", "__doc__": None, "check": other_tools_check, "CONFIG": {"poll_seconds": 0.5},
           "user_var": 7}
before = dict(console)
for n in range(3):
    exec(compile(src, "<pasted>", "exec"), console)
    mod = sys.modules["parent_actors"]
    assert console["parent_actors"] is mod and mod is not P and mod.STATE["parent"] is table
    assert set(console) == set(before) | {"parent_actors", "__builtins__"}, sorted(set(console) - set(before))
    assert console["check"] is other_tools_check and console["CONFIG"] == {"poll_seconds": 0.5}
assert mod.attach.__globals__ is mod.__dict__
tops = [w for w in QtWidgets.QApplication.instance().topLevelWidgets() if w.objectName() == P.WINDOW_OBJECT_NAME]
assert len(tops) == 1 and tops[0].isVisible(), "old panels were replaced, not left hidden"
assert live_ticks() == 1, "re-pasting doesn't pile up per-frame callbacks: %d" % live_ticks()
# another tool pasted later redefines names in the console: this one keeps working
exec("def check(key, category, name): return None\nCONFIG = {}\ndef label(a): return 'wrong'", console)
reset()
mod.STATE["parent"], mod.STATE["children"] = None, []
select(plate, table)
res = mod.attach_selected()
assert res and res[0][1] == "attached" and res[0][2] == "under Table", res
assert mod.show() is tops[0]

# --- a renamed copy imported from Content/Python keeps its own names ------------------------------------------------
import shutil, tempfile  # noqa: E401,E402
tmp = tempfile.mkdtemp()
shutil.copy(os.path.join(os.path.dirname(HERE), "parent_actors" + ".py"), os.path.join(tmp, "parent_actors_v2" + ".py"))
sys.path.insert(0, tmp)
import parent_actors_v2 as R  # noqa: E402
assert callable(R.show) and callable(R.attach_selected) and R.STATE is sys.modules["parent_actors"].STATE
print("PARENT ACTORS OK")
