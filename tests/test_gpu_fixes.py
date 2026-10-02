"""Fix / Revert on measured GPU findings (group fixes), Go To."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)
exec(open(os.path.join(HERE, "scene.py")).read())   # mock "unreal" module + demo level (U, M_snow, big, ...)
exec(open(os.path.join(HERE, "csv_fixture.py")).read())   # fake CSV profile
import world_perf_audit as W
import clock; clock.install(W)
from PySide6 import QtWidgets
win = W.show()
win.on_scan()
win.on_profile_gpu()
clock.run_ticks(U)
gpu = {i.title.split(":")[0]: i for i in win.issues if i.category == W.CAT_GPU}
for t, i in gpu.items():
    print("  %-40s %-7s children=%d %s" % (t[:40], "FIX" if i.fix else "manual", len(i.children), [c.check for c in i.children][:6]))
sh = gpu["Shadows"]
assert sh.fix and {c.check for c in sh.children} >= {"light_radius", "mesh_wpo_distance", "mesh_tiny_shadows"}
assert gpu["Lumen GI & reflections"].children and all("Lumen" in c.title for c in gpu["Lumen GI & reflections"].children)
assert [c.title for c in gpu["Post processing / TSR"].children] == ["Convolution (FFT) bloom"]
assert not gpu["Translucency / FX overdraw"].fix or gpu["Translucency / FX overdraw"].children
# partial: fix one child from its own row -> group stays open with a Fix button
child = [c for c in sh.children if c.check == "light_radius"][0]
win._row_action(child)
assert child.status == "fixed" and sh.status == "open" and sh.fixable, (sh.status, sh.message)
print("partial:", sh.message, "| row button:", win._rows[sh.id][1].text())
# group Fix applies the rest
win._row_action(sh)
assert sh.status == "fixed" and all(c.status == "fixed" for c in sh.children), [(c.title, c.status) for c in sh.children]
assert big.get_editor_property("attenuation_radius") == 2500 and SM_statue.get_editor_property("nanite_settings").enabled
print("group fixed:", sh.message, "| row button:", win._rows[sh.id][1].text(), "| child rows:", {win._rows[c.id][1].text() for c in sh.children})
# group Revert puts everything back
win._row_action(sh)
assert all(c.status == "reverted" for c in sh.children) and sh.status == "reverted", (sh.status, [c.status for c in sh.children])
assert big.get_editor_property("attenuation_radius") == 16000.0 and not SM_statue.get_editor_property("nanite_settings").enabled
print("group reverted:", sh.status)
# Fix All Shown in the GPU category: children deduped (Shadows + Direct lighting + draw calls share some)
win._category = W.CAT_GPU; win._apply_filter()
before = len(W._journal_load())
win.on_fix_all_shown()
assert all(not i.fixable for i in win.issues if i.category == W.CAT_GPU)
ids = [e["id"] for e in W._journal_load()][before:]
print("fix all shown (GPU): journal +%d entries, groups fixed:" % len(ids), sum(1 for i in win.issues if i.category == W.CAT_GPU and i.status == "fixed"))
win._category = W.CAT_GPU; win._apply_filter()
target = gpu["Shadows"]; win.tree.clearSelection(); win._rows[target.id][0].setSelected(True)
QtWidgets.QApplication.processEvents(); win.resize(1600, 820); QtWidgets.QApplication.processEvents()
win.grab().save(os.path.join(OUT, "ui_gpu_fix.png"))
print("GPU FIX OK")
U.EditorActorSubsystem.selected = []
W.go_to(gpu["Shadows"])
print("go_to selected:", sorted({a.get_actor_label() for a in U.EditorActorSubsystem.selected})[:6])
assert U.EditorActorSubsystem.selected
print("GOTO OK")
