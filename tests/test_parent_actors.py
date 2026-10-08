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
assert win.list.item(0).text() == "(deleted)"
win.on_attach()
assert cup.get_attach_parent_actor() is table and "1 not: (deleted) - it was deleted" in win.lbl_status.text(), \
    win.lbl_status.text()
plate.destroyed = False
print("refusals: OK")

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

# --- pasted into the Output Log: becomes the module "parent_actors", keeps the panel's state -------------------------
src = open(os.path.join(os.path.dirname(HERE), "parent_actors" + ".py"), encoding="utf-8").read()
g = {"__name__": "__main__"}
exec(compile(src, "<pasted>", "exec"), g)
mod = sys.modules["parent_actors"]
assert mod is not P and mod.STATE["parent"] is table and callable(mod.attach_selected)
tops = [w for w in QtWidgets.QApplication.instance().topLevelWidgets()
        if w.objectName() == P.WINDOW_OBJECT_NAME and w.isVisible()]
assert len(tops) == 1, "the old panel was replaced"
print("PARENT ACTORS OK")
