"""A capture shaped like a real UE 5.6 project (render-thread bound, real pass names), without a prior scan."""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)
exec(open(os.path.join(HERE, "scene.py")).read())   # mock "unreal" module + demo level (U, M_snow, big, ...)
for c in lights.comps[1:6]:
    c._p["contact_shadow_length"] = 0.1
U.SystemLibrary.CVARS.update({"r.SeparateTranslucencyScreenPercentage": 100, "r.VolumetricFog.GridPixelSize": 8,
                              "r.VolumetricFog.GridSizeZ": 128})
cols = ["FrameTime", "GameThreadTime", "RenderThreadTime", "GPUTime", "RHI/DrawCalls", "GPU/RenderDeferredLighting",
        "GPU/NaniteVisBuffer", "GPU/Translucency", "GPU/VolumetricFog", "GPU/TemporalSuperResolution",
        "GPU/ShadowProjection", "GPU/BasePass"]
base = [35.7, 12.0, 34.5, 22.1, 5200, 5.28, 3.66, 3.66, 2.88, 1.73, 1.46, 1.41]
random.seed(2)
rows = [",".join(cols)] + [",".join("%.3f" % (v * random.uniform(0.98, 1.02)) for v in base) for _ in range(120)]
U.SystemLibrary.CSV_TEXT = "\n".join(rows) + "\n[HasHeaderRowAtEnd],1\n"
import world_perf_audit as W
import clock; clock.install(W)
from PySide6 import QtWidgets
win = W.show()
assert not win.issues
win.on_profile_gpu()                       # no scan yet -> scans automatically
assert any(i.category != W.CAT_GPU for i in win.issues), "auto-scan did not run"
clock.run_ticks(U)
gpu = {i.title.split(":")[0]: i for i in win.issues if i.category == W.CAT_GPU}
for t, i in gpu.items():
    print("  %-34s %-6s %s" % (t[:34], "FIX" if i.fix else "manual", [c.check if c.check != "gpu_cvar" else c.obj for c in i.children][:7]))
assert gpu["Render thread-bound"].fix, "render-thread bound should link draw-call fixes"
dl = gpu["Direct lighting"]
assert dl.fix and {"light_radius", "light_contact_shadows"} <= {c.check for c in dl.children}
assert gpu["Geometry & materials (base pass)"].fix
tr = gpu["Translucency / FX overdraw"]
assert tr.fix and tr.children[0].obj == "r.SeparateTranslucencyScreenPercentage"
fog = gpu["Fog / volumetric fog"]
assert {c.obj for c in fog.children} >= {"r.VolumetricFog.GridPixelSize", "r.VolumetricFog.GridSizeZ"}
# apply translucency (cvar) fix -> runtime + ini; revert -> both restored
ini_path = os.path.join(U._TMP, "Config", "DefaultEngine.ini")
ini_before = open(ini_path).read()
win._row_action(tr)
assert U.SystemLibrary.CVARS["r.SeparateTranslucencyScreenPercentage"] == 50
assert "[SystemSettings]\nr.SeparateTranslucencyScreenPercentage=50" in open(ini_path).read()
print("translucency fix:", tr.status, tr.message, "| row:", win._rows[tr.id][1].text())
win._row_action(tr)
assert U.SystemLibrary.CVARS["r.SeparateTranslucencyScreenPercentage"] == 100, U.SystemLibrary.CVARS
assert "SeparateTranslucencyScreenPercentage" not in open(ini_path).read(), open(ini_path).read()
print("translucency revert:", tr.status)
# rescan keeps the GPU findings (re-linked), no duplicates
n_gpu = len([i for i in win.issues if i.category == W.CAT_GPU])
win.on_scan()
gpu2 = [i for i in win.issues if i.category == W.CAT_GPU]
assert len(gpu2) == n_gpu and any(i.fix for i in gpu2), (len(gpu2), n_gpu)
print("after rescan: %d GPU findings, %d with Fix" % (len(gpu2), sum(1 for i in gpu2 if i.fix)))
manual = [i for i in gpu2 if not i.fix]
for i in manual:
    print("  manual:", i.title, "->", i.solution.split("\n\n")[-1][:90])
win._category = W.CAT_GPU; win._apply_filter()
sel = [i for i in gpu2 if i.title.startswith("Direct lighting")][0]
win.tree.clearSelection(); win._rows[sel.id][0].setSelected(True)
QtWidgets.QApplication.processEvents(); win.resize(1600, 820); QtWidgets.QApplication.processEvents()
win.grab().save(os.path.join(OUT, "ui_gpu_real.png"))
print("REAL CAPTURE OK")
