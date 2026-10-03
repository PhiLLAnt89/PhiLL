"""One regression test per code-review finding."""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)
exec(open(os.path.join(HERE, "scene.py")).read())   # mock "unreal" module + demo level (U, M_snow, big, ...)
import world_perf_audit as W
import clock; clock.install(W)
CSV_DIR = os.path.join(U._TMP, "Saved", "Profiling", "CSV")
os.makedirs(CSV_DIR, exist_ok=True)

def csv_text(cols, base, n=60, end_header=None, finished=True):
    rows = [",".join(cols)] + [",".join("%.3f" % (v * random.uniform(0.99, 1.01)) for v in base) for _ in range(n)]
    if finished:
        rows.append("[HasHeaderRowAtEnd],1,[platform],Windows")
        rows.append(",".join(end_header or cols))
    return "\n".join(rows) + "\n"

# --- 9: complete header at the end of the file (late GPU columns) ---------------------------------
first = ["FrameTime", "GameThreadTime", "RenderThreadTime", "GPUTime"]
full = first + ["GPU/ShadowDepths", "GPU/VolumetricFog", "GPU/Fog"]
p = os.path.join(CSV_DIR, "late_header.csv")
open(p, "w").write(csv_text(first, [30, 8, 9, 29.5, 6.0, 2.5, 1.5], end_header=full))
r = W.analyse_csv(p)
assert "GPU/ShadowDepths" in r["means"] and abs(r["means"]["GPU/ShadowDepths"] - 6.0) < 0.2, r["means"]
assert r["frames"] == 60
print("9 late header: OK")

# --- 1: half-written capture is not analysed; finished one is ---------------------------------------
U.SystemLibrary.CSV_TEXT = None
issues = W.scan()
done = {}
W.profile_gpu(on_done=lambda iss, err: done.update(iss=iss, err=err), auto_scan=False)
cap = os.path.join(CSV_DIR, "Profile(capture).csv")
open(cap, "w").write(csv_text(full, [30, 8, 9, 29.5, 6.0, 2.5, 1.5], finished=False))
clock.run_ticks(U, n=10)
assert W._PROFILE["busy"] and not done, "must not analyse a capture without the closing metadata row"
open(cap, "w").write(csv_text(full, [30, 8, 9, 29.5, 6.0, 2.5, 1.5], end_header=full))
clock.run_ticks(U, n=10)
assert not W._PROFILE["busy"] and done.get("err") is None, done
print("1 wait for finished capture: OK (%d findings)" % len(done["iss"]))

# --- 5: one shared cvar child for two passes of the same rule --------------------------------------
U.SystemLibrary.CVARS.update({"r.VolumetricFog.GridPixelSize": 8, "r.VolumetricFog.GridSizeZ": 128})
gi = W.gpu_profile_issues(W.analyse_csv(cap), W._STATE["issues"])
fogs = [i for i in gi if i.title.startswith("Fog")]
assert len(fogs) == 2, [i.title for i in gi]
ids = [{c.id for c in f.children if c.check == "gpu_cvar"} for f in fogs]
assert ids[0] == ids[1] and ids[0], "cvar child must be shared"
W._STATE["issues"] = [i for i in W._STATE["issues"] if i.category != W.CAT_GPU] + gi
child = [c for c in fogs[0].children if c.obj == "r.VolumetricFog.GridPixelSize"][0]
assert "for High quality" in child.fix_label, child.fix_label     # Low: fog off, Medium: already 16
U.SystemLibrary.CVARS["sg.ShadowQuality"] = 2                    # editor at High: applied live too
W.apply_fixes(fogs)
assert U.SystemLibrary.CVARS["r.VolumetricFog.GridPixelSize"] == 16
scal = open(os.path.join(U._TMP, "Config", "DefaultScalability.ini")).read()
assert "[ShadowQuality@2]\nr.VolumetricFog.GridPixelSize=16\nr.VolumetricFog.GridSizeZ=64" in scal, scal
W.revert_issues(fogs)
assert U.SystemLibrary.CVARS["r.VolumetricFog.GridPixelSize"] == 8, U.SystemLibrary.CVARS
assert "GridPixelSize" not in open(os.path.join(U._TMP, "Config", "DefaultScalability.ini")).read()
U.SystemLibrary.CVARS["sg.ShadowQuality"] = 3
print("5 shared cvar child: OK")

# --- 6: shared scan child reverted once ------------------------------------------------------------
radius = [i for i in W._STATE["issues"] if i.check == "light_radius"][0]
g1 = W.Issue("gpu_pass", W.CAT_GPU, W.HIGH, "A", "a", "", "", fix=W._group_fix, children=[radius])
g2 = W.Issue("gpu_pass", W.CAT_GPU, W.HIGH, "B", "b", "", "", fix=W._group_fix, children=[radius])
W.apply_fixes([g1, g2])
n, errs = W.revert_issues([g1, g2, radius])
assert n == 1, n
print("6 revert dedupe: OK")

# --- 7: revert_all also resets hidden cvar children ------------------------------------------------
U.SystemLibrary.CVARS["r.SeparateTranslucencyScreenPercentage"] = 100
cols = ["FrameTime", "GameThreadTime", "RenderThreadTime", "GPUTime", "GPU/Translucency"]
p2 = os.path.join(CSV_DIR, "tr.csv"); open(p2, "w").write(csv_text(cols, [30, 8, 9, 29, 5.0]))
gi = W.gpu_profile_issues(W.analyse_csv(p2), W._STATE["issues"])
tr = [i for i in gi if i.title.startswith("Translucency")][0]
W._STATE["issues"] = [i for i in W._STATE["issues"] if i.category != W.CAT_GPU] + gi
W.apply_fixes([tr])
assert tr.status == "fixed"
W.revert_all()
assert tr.children[0].status == "reverted" and tr.status == "reverted" and tr.fixable, (tr.children[0].status, tr.status)
print("7 revert_all resets cvar children: OK")

# --- 12: text-mode fix(id) updates groups ----------------------------------------------------------
radius = [i for i in W._STATE["issues"] if i.check == "light_radius"][0]
g = W.Issue("gpu_pass", W.CAT_GPU, W.HIGH, "G", "g", "", "", fix=W._group_fix, children=[radius])
W._STATE["issues"].append(g)
W.fix(radius.id)
assert g.status == "fixed", g.status
W.revert(radius.id)
assert g.status == "reverted", g.status
print("12 text-mode group status: OK")

# --- 11: go_to_many expands GPU findings ------------------------------------------------------------
U.EditorActorSubsystem.selected = []
W.go_to_many([g, W.Issue("gpu_pass", W.CAT_GPU, W.LOW, "H", "h", "", "", fix=W._group_fix, children=[radius])])
assert U.EditorActorSubsystem.selected, "go_to_many on GPU findings selected nothing"
print("11 go_to_many groups: OK")

# --- 3: timeout fires even while a file keeps changing ----------------------------------------------
done = {}
W.profile_gpu(frames=10, on_done=lambda iss, err: done.update(err=err), auto_scan=False)
grow = os.path.join(CSV_DIR, "Profile(growing).csv")
for k in range(400):
    with open(grow, "a") as fh:
        fh.write("1,2,3\n" * (k + 1))
    clock.run_ticks(U, n=1, step=0.3)
    if not W._PROFILE["busy"]:
        break
assert not W._PROFILE["busy"] and done.get("err") and "didn't finish" in done["err"], done
print("3 timeout while file changes: OK")

# --- 4: profile from another level is not re-attached ---------------------------------------------
W._STATE["gpu_profile"] = dict(W.analyse_csv(p2), level="Some_Other_Level", time="10:00:00")
iss = W.scan()
assert not [i for i in iss if i.category == W.CAT_GPU] and W._STATE["gpu_profile"] is None
W._STATE["gpu_profile"] = dict(W.analyse_csv(p2), level="L_MockLevel", time="10:00:00")
iss = W.scan()
assert [i for i in iss if i.category == W.CAT_GPU], "same level keeps its measured findings"
print("4 stale profile per level: OK")

# --- 2: duplicates only within the same level, never 'Safe' -----------------------------------------
dup = [i for i in iss if i.check == "mesh_stacked_duplicates"]
assert dup and all(i.impact == W.GAMEPLAY for i in dup)
print("2 duplicates impact: OK")

# --- 8: a failing on_done callback doesn't break finish() -------------------------------------------
open(os.path.join(CSV_DIR, "Profile(cb).csv"), "w")  # placeholder so the next new file is detected
def bad_cb(iss, err):
    raise RuntimeError("C++ object already deleted")
W.profile_gpu(frames=10, on_done=bad_cb, auto_scan=False)
open(os.path.join(CSV_DIR, "Profile(cb2).csv"), "w").write(csv_text(cols, [30, 8, 9, 29, 5.0]))
clock.run_ticks(U, n=10)
assert not W._PROFILE["busy"] and U.TICKS[-1] is None, "callback errors must not leave the profiler running"
assert U.SystemLibrary.commands[-1].startswith("r.GPUCsvStatsEnabled")
print("8 callback failure isolated: OK")
print("ALL REGRESSIONS OK")
