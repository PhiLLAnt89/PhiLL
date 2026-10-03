"""Profile Sequence: shot-by-shot capture, worst shot, Go To, spawnable templates fixed in the sequence, Stop."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)
exec(open(os.path.join(HERE, "scene.py")).read())   # mock "unreal" module + demo level (U, M_snow, big, ...)

# a sequence with three shots; a spawnable (template lives in the sequence asset) with an oversized light
SEQ = U.LevelSequence("SEQ_Intro", path="/Game/Cine/SEQ_Intro", tracks=[
    U._Track(U.MovieSceneCinematicShotTrack, [U._Section("sh010", 0, 100), U._Section("sh020", 100, 250),
                                              U._Section("sh030", 250, 300)])])
tmpl = U.Actor("BP_Spotlight_Template", outer=SEQ)
tlight = tmpl.add(U.PointLightComponent("LightComponent0", attenuation_radius=12000.0))
SEQ.spawnables = [tmpl]
# what Sequencer spawned from it right now: transient, only the raw world iterator sees it
spawned = U.Actor("BP_Spotlight_Spawned")
slight = spawned.add(U.PointLightComponent("LightComponent0", attenuation_radius=12000.0))
U.EXTRA_WORLD_ACTORS.append(spawned)
SEQ_LIB = U.LevelSequenceEditorBlueprintLibrary
SEQ_LIB.time = 42

# each capture: frame time depends on the shot the playhead is in (sh020 is the heavy one)
cols = "FrameTime,GameThreadTime,RenderThreadTime,GPUTime,GPU/ShadowDepths,GPU/Translucency,GPU/BasePass"
captures = []
orig_exec = U.SystemLibrary.execute_console_command


def fake_exec(world, cmd):
    orig_exec(world, cmd)
    if cmd.startswith("csvprofile frames"):
        t = SEQ_LIB.time
        frame = 40.0 if 100 <= t < 250 else 18.0
        captures.append(t)
        rows = [cols] + ["%.2f,8,9,%.2f,%.2f,2.0,3.0" % (frame, frame - 1, frame / 3) for _ in range(30)]
        d = os.path.join(U._TMP, "Saved", "Profiling", "CSV")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "Shot_%d_%d.csv" % (len(captures), t)), "w") as f:
            f.write("\n".join(rows) + "\n[HasHeaderRowAtEnd],1\n")


U.SystemLibrary.execute_console_command = staticmethod(fake_exec)
import world_perf_audit as W
import clock; clock.install(W)
from PySide6 import QtWidgets

# --- spawnable templates are scanned and fixed on the template --------------------------------------------------
win = W.show()
win.on_profile_sequence()
assert "Open a Level Sequence" in win.lbl_status.text() and not W._PROFILE["busy"]
SEQ_LIB.current = SEQ
win.on_scan()
radius = [i for i in win.issues if i.check == "light_radius"]
assert [i for i in radius if i.targets[0] is tlight], "template light found"
assert not [i for i in radius if i.targets[0] is slight], "spawned copy: no actor-level fix (it would be lost)"
assert "spawnable template" in win.lbl_scanned.text(), win.lbl_scanned.text()
fix_t = [i for i in radius if i.targets[0] is tlight][0]
win._row_action(fix_t)
assert tlight.get_editor_property("attenuation_radius") == W.CONFIG["max_light_radius"]
assert fix_t.journal["changes"][0]["path"].startswith("/Game/Cine/SEQ_Intro")
win._row_action(fix_t)
assert tlight.get_editor_property("attenuation_radius") == 12000.0
print("spawnable template fix/revert: OK")

# --- shot by shot ---------------------------------------------------------------------------------------------------------
SEQ_LIB.locked = False
win.on_profile_sequence()
assert W._PROFILE["busy"] and win.btn_profile_seq.text() == "Stop" and not win.btn_profile.isEnabled()
clock.run_until_idle(U, W)
seq = [i for i in win.issues if i.category == W.CAT_SEQ]
for i in seq:
    print("  %-8s %-40s %s" % (i.severity_name, i.title, i.obj))
assert len(seq) == 3 and captures == [49, 174, 274], captures
worst = max(seq, key=lambda i: i.cost)
assert "sh020" in worst.title and worst.severity == W.HIGH and worst.fix, worst.title
assert SEQ_LIB.time == 174, "parked on the worst shot"
assert SEQ_LIB.locked is False, "camera-cut lock restored"
assert win._category == W.CAT_SEQ and "Worst" in win.lbl_status.text(), win.lbl_status.text()
assert U.SystemLibrary.CVARS.get("r.GPUCsvStatsEnabled", 0) == 0
assert win.btn_profile_seq.text() == "Profile Sequence" and win.btn_profile.isEnabled()
# Go To jumps to the shot
SEQ_LIB.time = 0
win._goto([seq[[i.title for i in seq].index([t for t in [i.title for i in seq] if "sh030" in t][0])]])
assert SEQ_LIB.time == 274 and SEQ_LIB.locked is True
SEQ_LIB.locked = False
# a re-scan keeps the shot findings, linked to the new scan's fixes
win.on_scan()
assert len([i for i in win.issues if i.category == W.CAT_SEQ]) == 3
# another sequence open: Go To says so instead of jumping to the wrong frames
other = U.LevelSequence("SEQ_Other")
SEQ_LIB.current = other
win._goto([[i for i in win.issues if i.category == W.CAT_SEQ][0]])
assert "SEQ_Intro" in win.lbl_status.text() and SEQ_LIB.time == 274
SEQ_LIB.current = SEQ
win._category = W.CAT_SEQ; win._apply_filter()
win.tree.clearSelection(); win._rows[worst.id][0].setSelected(True) if worst.id in win._rows else None
QtWidgets.QApplication.processEvents(); win.resize(1600, 820); QtWidgets.QApplication.processEvents()
win.grab().save(os.path.join(OUT, "ui_sequence.png"))
print("shot by shot: OK")

# --- Stop: capture stopped, settings and playhead restored --------------------------------------------------------
SEQ_LIB.time = 42
n_before = len(captures)
win.on_profile_sequence()
for _ in range(100):                           # until the capture of shot 2 is running
    if len(captures) >= n_before + 2:
        break
    clock.run_ticks(U, n=1)
assert W._PROFILE["busy"] and len(captures) == n_before + 2
win.on_profile_sequence()                      # the button says Stop
clock.run_ticks(U, n=2)
assert not W._PROFILE["busy"] and "stopped" in win.lbl_status.text(), win.lbl_status.text()
assert "csvprofile stop" in U.SystemLibrary.commands
assert SEQ_LIB.time == 42 and SEQ_LIB.locked is False and U.SystemLibrary.CVARS.get("r.GPUCsvStatsEnabled") == 0
assert len(captures) > n_before
assert win.btn_profile_seq.text() == "Profile Sequence"
print("stop: OK")
print("SEQUENCER OK")
