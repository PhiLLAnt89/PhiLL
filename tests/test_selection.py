"""Multi-select Fix Selected / Revert in the UI."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)
import unreal as U
# 10 8K textures used by one material, like the user's snow textures
texs = []
for i in range(10):
    t = U.Texture2D("T_Snow_mount_%d_BaseColor" % i); t.w = t.h = 8192; texs.append(t)
M = U.Material("M_Snow_Landscape"); M.textures = tuple(texs)
SM = U.StaticMesh("SM_Rock", static_materials=[U.StaticMaterial(material_interface=M)], nanite_settings=U.MeshNaniteSettings(enabled=True), body_setup=U.BodySetup("BS"))
a = U.StaticMeshActor("Rock", SM); a.comps[0].mats = (M,)
U.EditorActorSubsystem.actors = [a]
import world_perf_audit as W
from PySide6 import QtWidgets
win = W.show()
win.on_scan()
rows = [i for i in win.issues if i.check == "tex_oversized"]
print("8K issues:", len(rows))
win.tree.clearSelection()
for i in rows[:7]:
    win._rows[i.id][0].setSelected(True)
QtWidgets.QApplication.processEvents()
print("toolbar:", win.btn_fix_sel.text(), "| detail:", win.d_fix.text())
win.on_fix_selected()                      # toolbar button
st = [i.status for i in rows]
print("after Fix Selected:", st)
assert st[:7] == ["fixed"] * 7 and st[7:] == ["open"] * 3
assert all(win._rows[i.id][0].text(win.C_STATUS) == "Fixed" for i in rows[:7]), "row status text not updated"
assert all(t.get_editor_property("max_texture_size") == 4096 for t in texs[:7])
print("detail after:", win.d_revert.text())
win.d_revert.click()                       # detail panel: revert the 7 selected
st = [i.status for i in rows]
print("after Revert (detail panel):", st)
assert st[:7] == ["reverted"] * 7
assert all(t.get_editor_property("max_texture_size") == 0 for t in texs)
for i in rows: win._rows[i.id][0].setSelected(True)
QtWidgets.QApplication.processEvents()
win.d_fix.click()                          # detail panel: fix all 10 selected
assert [i.status for i in rows] == ["fixed"] * 10
print("row buttons:", {win._rows[i.id][1].text() for i in rows}, "| warn icons:", sum(1 for i in rows if win._warns[i.id].pixmap() is not None and not win._warns[i.id].pixmap().isNull()))
win.resize(1560, 760); QtWidgets.QApplication.processEvents()
win.grab().save(os.path.join(OUT, "ui3.png"))
print("SELECTION OK")
