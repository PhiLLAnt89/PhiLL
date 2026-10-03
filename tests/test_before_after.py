"""Before/after proof: profile comparison (+ revert of fixes with no measurable gain) and viewport screenshots."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)
exec(open(os.path.join(HERE, "scene.py")).read())   # mock "unreal" module + demo level (U, M_snow, big, ...)
exec(open(os.path.join(HERE, "csv_fixture.py")).read())   # fake CSV profile (cols, base)
import world_perf_audit as W
import clock; clock.install(W)
from PySide6 import QtCore, QtGui, QtWidgets

win = W.show()
win.on_scan()
win.on_profile_gpu()
clock.run_until_idle(U, W)
gpu = {i.title.split(":")[0]: i for i in win.issues if i.category == W.CAT_GPU}
assert not [i for i in win.issues if i.check == "gpu_compare"], "nothing to compare with yet"

# --- fix shadows + translucency, then profile again: shadows got faster, translucency didn't ------------------
U.SystemLibrary.CVARS.update({"sg.EffectsQuality": 1, "r.SeparateTranslucencyScreenPercentage": 100})
win.issues = W._STATE["issues"]
tr = gpu["Translucency / FX overdraw"]
win.fix_issues([gpu["Shadows"], tr])
assert U.SystemLibrary.CVARS["r.SeparateTranslucencyScreenPercentage"] == 50, "editor runs at Medium: live"
faster = list(base)
faster[cols.index("GPU/ShadowDepths")] = 3.9
faster[cols.index("FrameTime")] = 23.6
faster[cols.index("GPUTime")] = 23.5
rows = [",".join(cols)] + [",".join(["%.3f" % v for v in faster] + [""]) for _ in range(120)]
U.SystemLibrary.CSV_TEXT = "\n".join(rows + ["[HasHeaderRowAtEnd],1", ",".join(cols)]) + "\n"
win.on_profile_gpu()
clock.run_until_idle(U, W)
cmp_ = [i for i in win.issues if i.check == "gpu_compare"]
assert len(cmp_) == 1, [i.title for i in win.issues if i.category == W.CAT_GPU]
cmp_ = cmp_[0]
print(cmp_.title)
print(cmp_.detail)
assert cmp_.pinned and win.issues[0] is cmp_ and "27.4 -> 23.6" in cmp_.title
assert "Shadows: 7.80 -> 3.90" in cmp_.detail.replace("  ", " ") or "Shadows" in cmp_.detail
nogain = {c.obj for c in cmp_.children}
assert nogain == {"r.SeparateTranslucencyScreenPercentage"}, nogain
assert win._rows[cmp_.id][1].text() == "Revert" and "(pinned on top)" in win.lbl_status.text()
frame = [i for i in win.issues if i.check == "gpu_frame"][0]
assert "(-3.78)" in frame.metric, frame.metric
# the pinned row stays first whatever the sort
for order in (QtCore.Qt.SortOrder.AscendingOrder, QtCore.Qt.SortOrder.DescendingOrder):
    win.tree.sortByColumn(win.C_COST, order)
    assert int(win.tree.topLevelItem(0).data(0, QtCore.Qt.ItemDataRole.UserRole)) == cmp_.id
win.tree.sortByColumn(win.C_COST, QtCore.Qt.SortOrder.DescendingOrder)
win._category = W.CAT_GPU; win._apply_filter()
win.tree.clearSelection(); win._rows[cmp_.id][0].setSelected(True)
QtWidgets.QApplication.processEvents(); win.resize(1600, 820); QtWidgets.QApplication.processEvents()
assert win.d_revert.isEnabled()
win.grab().save(os.path.join(OUT, "ui_compare_profiles.png"))
# one click takes back only the fix that bought nothing
win._row_action(cmp_)
assert U.SystemLibrary.CVARS["r.SeparateTranslucencyScreenPercentage"] == 100
assert big.get_editor_property("attenuation_radius") == 2500, "the shadow fixes stay"
assert cmp_.status == "reverted" and not W._can_revert(cmp_)
# a re-scan between profiles doesn't lose the fixes made in between
win.on_scan()
assert [i for i in win.issues if i.check == "gpu_compare"][0].pinned
print("profile comparison: OK")

# --- before/after screenshots --------------------------------------------------------------------------------------
shot_no = [0]


def write_shots():
    while U.SystemLibrary.pending_shots:
        name = U.SystemLibrary.pending_shots.pop(0)
        shot_no[0] += 1
        img = QtGui.QImage(640, 360, QtGui.QImage.Format.Format_RGB32)
        img.fill(QtGui.QColor("#2b3a55"))
        p = QtGui.QPainter(img)
        p.fillRect(40, 200, 560, 120, QtGui.QColor("#4b5563"))
        p.setBrush(QtGui.QColor("#fde68a"))
        r = 140 if shot_no[0] % 2 == 1 else 70           # "after": the light reaches less far
        p.drawEllipse(QtCore.QPoint(320, 150), r, r)
        p.end()
        d = os.path.join(U._TMP, "Saved", "Screenshots", "WindowsEditor")
        os.makedirs(d, exist_ok=True)
        img.save(os.path.join(d, name or "HighresScreenshot%05d.png" % shot_no[0]))


U.flush_screenshots = write_shots
win.chk_shots.setChecked(True)
safe = [i for i in win.issues if i.fixable and i.impact == W.SAFE and not i.children][0]
win.fix_issues([safe])
assert safe.status == "fixed" and not W._PROFILE["busy"] and safe.shots is None, "Safe fixes need no screenshots"
looks = [i for i in win.issues if i.fixable and i.impact == W.LOOK and not i.children and i.category != W.CAT_GPU]
light = looks[0]
print("shots on:", light.title, "/", light.obj)
win.fix_issues([light])
assert W._PROFILE["busy"] and light.status == "open", "the before shot comes first"
clock.run_until_idle(U, W)
assert light.status == "fixed" and light.shots, light.message
assert all(os.path.isfile(light.shots[k]) and "PerfAudit" in light.shots[k] for k in ("before", "after"))
assert "Before / After" in win.lbl_status.text(), win.lbl_status.text()
win._category = None; win._apply_filter()
win.tree.clearSelection(); win._rows[light.id][0].setSelected(True)
QtWidgets.QApplication.processEvents()
assert win.d_compare.isEnabled() and "BEFORE / AFTER" in win.detail.toHtml().upper()
win.grab().save(os.path.join(OUT, "ui_shots_detail.png"))
win._no_modal = True
win.compare_shots(light)
dlg = win._compare_dialog
QtWidgets.QApplication.processEvents()
dlg.grab().save(os.path.join(OUT, "ui_compare_wipe.png"))
view = dlg.findChild(QtWidgets.QWidget, "") if False else [w for w in dlg.children() if w.__class__.__name__ == "_CompareView"][0]
view.set_mode("diff")
QtWidgets.QApplication.processEvents()
dlg.grab().save(os.path.join(OUT, "ui_compare_diff.png"))
info = [w.text() for w in dlg.findChildren(QtWidgets.QLabel) if "changed visibly" in w.text()][0]
print("compare dialog:", info)
assert not info.startswith("~0.0")
dlg.close()
# screenshots that never arrive: the fix still happens, the status says why there's no comparison
U.flush_screenshots = lambda: U.SystemLibrary.pending_shots.clear()
vis = looks[1]
win.fix_issues([vis])
clock.run_until_idle(U, W)
assert vis.status == "fixed" and vis.shots is None and "couldn't be taken" in win.lbl_status.text(), win.lbl_status.text()
print("before/after shots: OK")
print("BEFORE AFTER OK")
