"""Profile GPU: capture -> analysis -> findings, re-profile replaces findings."""
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
n_scan = len(win.issues)
win.on_profile_gpu()
print("busy:", W._PROFILE["busy"], "| status:", win.lbl_status.text()[:80])
clock.run_ticks(U)
assert not W._PROFILE["busy"], "profile should be finished"
gpu = [i for i in win.issues if i.category == W.CAT_GPU]
for i in gpu:
    print("  %-7s %-48s %s" % (i.severity_name, i.title, i.metric))
assert gpu[0].check == "gpu_frame" or any(i.check == "gpu_frame" for i in gpu)
frame = [i for i in gpu if i.check == "gpu_frame"][0]
assert frame.title.startswith("GPU-bound") and frame.severity == W.HIGH
sh = [i for i in gpu if i.title.startswith("Shadows")][0]
assert "Lighting & Shadows" in sh.solution, sh.solution
assert any(i.check == "gpu_drawcalls" for i in gpu)
assert not [i for i in gpu if "HZB" in i.obj], "tiny passes are filtered"
assert "r.GPUCsvStatsEnabled 1" in U.SystemLibrary.commands and U.SystemLibrary.commands[-1].startswith("r.GPUCsvStatsEnabled")
assert len(win.issues) == n_scan + len(gpu) and win._category == W.CAT_GPU
print("status:", win.lbl_status.text())
QtWidgets.QApplication.processEvents()
sel = [i for i in gpu if i.title.startswith("Shadows")][0]
win._rows[sel.id][0].setSelected(True)
QtWidgets.QApplication.processEvents()
win.resize(1600, 820); QtWidgets.QApplication.processEvents()
win.grab().save(os.path.join(OUT, "ui_gpu.png"))
# re-profile replaces old GPU findings instead of duplicating them
import time as _t; _t.sleep(1.1)        # new capture written a moment later (same name)
win.on_profile_gpu()
clock.run_ticks(U)
assert not W._PROFILE["busy"], "second capture not detected"
assert len([i for i in win.issues if i.category == W.CAT_GPU]) == len(gpu)
print("GPU PROFILE OK")
